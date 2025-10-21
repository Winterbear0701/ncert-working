import os
import logging
from datetime import timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.views.decorators.http import require_POST # Use this decorator
import chromadb
from sentence_transformers import SentenceTransformer
from .models import ChatHistory, ChatCache, PermanentMemory, PDFImage
from .web_scraper import (
    is_educational_query, scrape_multiple_sources, 
    get_query_hash, search_educational_images
)
from .adaptive_difficulty import (
    determine_difficulty_level, adjust_prompt_for_difficulty,
    format_response_by_difficulty, generate_simplification_prompt
)
import openai
import google.generativeai as genai
import re

logger = logging.getLogger('students')

# --- Initialization: Load models/clients once on startup ---

# Use a dictionary to store clients/models initialized globally
RAG_SYSTEM = {
    "chroma_client": None,
    "embedding_model": None,
    "collection": None,
    "openai_model": "gpt-4o-mini",
    "gemini_model": "gemini-2.0-flash-exp",  # Updated to Gemini 2.0 Flash experimental
}

def initialize_rag_system():
    """Initializes ChromaDB, the embedding model, and API keys."""
    global RAG_SYSTEM
    
    # 1. API Key Configuration
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
             logger.warning("OPENAI_API_KEY is not set.")
             # Continue to allow Gemini fallback
        
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            logger.warning("GEMINI_API_KEY is not set.")

    except Exception as e:
        logger.error(f"Error configuring API keys: {e}")

    # 2. Initialize ChromaDB
    try:
        chroma_persist_dir = getattr(settings, 'CHROMA_PERSIST_DIRECTORY', 'chromadb_data')
        chroma_client = chromadb.PersistentClient(path=chroma_persist_dir)
        RAG_SYSTEM["chroma_client"] = chroma_client
    except Exception as e:
        logger.error(f"Error initializing ChromaDB client: {e}")
        return # Stop if database fails

    # 3. Initialize Embedding Model (can be slow, only do once)
    try:
        RAG_SYSTEM["embedding_model"] = SentenceTransformer('all-MiniLM-L6-v2')
    except Exception as e:
        logger.error(f"Error loading SentenceTransformer model: {e}")
        return

    # 4. Get or create collection
    try:
        RAG_SYSTEM["collection"] = RAG_SYSTEM["chroma_client"].get_or_create_collection(
            name="ncert_books",
            metadata={"description": "NCERT textbook embeddings by standard, subject, and chapter"}
        )
        logger.info("RAG system initialization complete.")
    except Exception as e:
        logger.error(f"Error accessing ChromaDB collection: {e}")

# Run initialization (In a production Django environment, it's safer to call this
# from an AppConfig.ready() method to ensure it runs exactly once after Django is ready.)
initialize_rag_system() 


def get_embedding(text):
    """Generate embedding for a single text using the initialized model."""
    if RAG_SYSTEM["embedding_model"] is None:
        logger.error("Embedding model is not loaded.")
        raise RuntimeError("Embedding model unavailable.")
    return RAG_SYSTEM["embedding_model"].encode(text).tolist()


@login_required
@require_POST # Ensure only POST requests are allowed for cleaner code
def ask_chatbot(request):
    """
    Enhanced AI Chatbot with:
    - Multi-tier caching (permanent memory → 10-day cache)
    - RAG from ChromaDB
    - Web scraping for additional context
    - Image support
    - Adaptive difficulty
    - Memory management commands
    """
    # 1. Input Validation and Retrieval
    question = request.POST.get("question", "").strip()
    model_choice = request.POST.get("model", "openai").lower()
    
    if not question:
        return JsonResponse({"status": "error", "error": "Question cannot be empty"}, status=400)
    
    # 2. Check for Memory Management Commands
    question_lower = question.lower()
    
    # FORGET/REMOVE command
    if any(phrase in question_lower for phrase in ['forget this', 'remove from memory', 'delete this']):
        try:
            # Get last chat to remove from permanent memory
            last_chat = ChatHistory.objects.filter(student=request.user).order_by('-created_at').first()
            if last_chat:
                deleted = PermanentMemory.objects.filter(
                    student=request.user,
                    question=last_chat.question
                ).delete()[0]
                
                if deleted > 0:
                    return JsonResponse({
                        "status": "success",
                        "answer": "✅ I've removed that from my permanent memory.",
                        "special_command": "forget"
                    })
                else:
                    return JsonResponse({
                        "status": "success",
                        "answer": "That wasn't in my permanent memory, but I understand you want me to forget it.",
                        "special_command": "forget"
                    })
        except Exception as e:
            logger.error(f"Error removing memory: {e}")
    
    # SAVE/REMEMBER command (handle after getting answer)
    save_to_memory = any(phrase in question_lower for phrase in ['save this', 'remember this', 'save in memory', 'keep this'])
    
    # Remove memory command from question if present
    if save_to_memory:
        question = re.sub(r'\b(save|remember|keep)\s+(this|it|that)(\s+in\s+(your\s+)?memory)?\b', '', question, flags=re.IGNORECASE).strip()
        if not question:
            question = "Acknowledge saving to memory"
    
    # 3. Determine Difficulty Level
    recent_questions = list(ChatHistory.objects.filter(student=request.user).order_by('-created_at')[:5].values_list('question', flat=True))
    difficulty_level = determine_difficulty_level(question, recent_questions)
    logger.info(f"Difficulty level: {difficulty_level}")
    
    # 4. Multi-Tier Retrieval System
    answer = ""
    images = []
    sources = []
    used_cache = False
    
    # Get student's standard early for use throughout
    standard = getattr(request.user, 'standard', None)
    
    # ALWAYS search RAG first - no direct AI responses to prevent hallucination
    # Educational query - check caches first
    query_hash = get_query_hash(question)
    
    # TIER 1: Check Permanent Memory (user-specific)
    try:
        perm_memory = PermanentMemory.objects.filter(
            student=request.user,
            keywords__icontains=question[:50]
        ).first()
        
        if perm_memory:
            answer = perm_memory.answer
            images = perm_memory.images or []
            sources = perm_memory.sources or []
            perm_memory.access_count += 1
            perm_memory.save()
            used_cache = True
            logger.info("✅ Answer from permanent memory")
    except Exception as e:
        logger.error(f"Error checking permanent memory: {e}")
    
    # TIER 2: Check 10-day Cache (global)
    if not answer:
        try:
            cache_entry = ChatCache.get_active_cache(query_hash)
            if cache_entry:
                answer = cache_entry.answer
                images = cache_entry.images or []
                sources = cache_entry.sources or []
                used_cache = True
                logger.info(f"✅ Answer from cache (hit count: {cache_entry.hit_count})")
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
    
    # TIER 3: If no cache hit, ALWAYS perform RAG search (prevent hallucination)
    rag_context = ""
    context_found = False
    web_context = ""
    
    if not used_cache:
        # 3a. ChromaDB RAG Retrieval (PRIMARY SOURCE - ALWAYS SEARCH FIRST!)
        try:
            from ncert_project.chromadb_utils import get_chromadb_manager
            chroma_manager = get_chromadb_manager()
            
            # Query ChromaDB with MAXIMUM results to get comprehensive content
            logger.info(f"🔍 Querying ChromaDB (RAG) for: {question[:50]}...")
            results = chroma_manager.query_by_class_subject_chapter(
                query_text=question,
                class_num=str(standard) if standard else None,
                n_results=20  # Get maximum relevant chunks for comprehensive answer
            )
            
            # Extract and format context from ChromaDB
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                context_parts = []
                
                for i, doc in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    similarity = 1 - distances[i] if i < len(distances) else 0
                    
                    # Format source reference with proper labels
                    source_ref = (f"[{meta.get('class', 'Class ?')}, "
                                 f"{meta.get('subject', 'Unknown Subject')}, "
                                 f"{meta.get('chapter', 'Chapter ?')}, "
                                 f"Page {meta.get('page', '?')}] "
                                 f"(Relevance: {similarity:.2f})")
                    context_parts.append(f"{source_ref}\n{doc}")
                    
                    # Add source to sources list for display
                    sources.append({
                        'name': f"{meta.get('subject', 'NCERT')} - {meta.get('chapter', 'Chapter')}",
                        'type': 'ncert_textbook',
                        'class': meta.get('class'),
                        'chapter': meta.get('chapter'),
                        'page': meta.get('page'),
                        'relevance': f"{similarity:.0%}"
                    })
                
                rag_context = "\n\n".join(context_parts)
                context_found = True
                logger.info(f"✅ Found {len(documents)} relevant chunks from NCERT textbooks (ChromaDB)")
            else:
                logger.info("⚠️  No relevant content found in ChromaDB")
                
        except Exception as e:
            logger.error(f"❌ Error during ChromaDB RAG retrieval: {e}")
            import traceback
            traceback.print_exc()
        
        # 3b. Web Scraping for Images ONLY (no text content)
        # Only scrape images to supplement RAG content
        if rag_context:
            try:
                logger.info("🌐 Web scraping for images only...")
                web_data = scrape_multiple_sources(question, include_images=True)
                
                if web_data['success'] and web_data.get('images'):
                    # Add ONLY images, NOT text content (prevent hallucination)
                    images.extend(web_data['images'])
                    logger.info(f"✅ Web scraping added {len(web_data['images'])} images")
                        
            except Exception as e:
                logger.error(f"⚠️  Web scraping error: {e}")
        else:
            # NO RAG CONTENT FOUND - Return "no content" message instead of hallucinating
            logger.warning("❌ No RAG content found - returning 'no content' message")
            return JsonResponse({
                "status": "success",
                "answer": ("I apologize, but I couldn't find relevant content about this topic in the NCERT textbooks. "
                          "This question might be outside the current curriculum, or the content hasn't been added to my database yet. "
                          "\n\n**Suggestions:**\n"
                          "- Try rephrasing your question\n"
                          "- Ask about topics from your NCERT textbooks\n"
                          "- Contact your teacher for topics outside the textbook"),
                "images": [],
                "sources": [],
                "difficulty_level": "unknown",
                "used_cache": False,
                "rag_used": False,
                "web_used": False,
                "context_found": False,
                "student_class": str(standard) if standard else None,
                "content_source": "no_content_found"
            })
    
    
    # 5. Generate Answer with AI (if not from cache)
    if not answer:
        # Build prompts with age-appropriate formatting
        age = getattr(request.user, 'age', 12)
        # Use standard defined earlier, fallback to 'middle school' if None
        if not standard:
            standard = 'middle school'
        
        # Age-appropriate system prompt
        if age <= 10:  # Class 5-6
            base_system = (
                f"You are a friendly, patient teacher for a {age}-year-old student in Class {standard}. "
                f"Explain things in very simple language with fun examples. Use short sentences. "
                f"Make learning exciting! Use emojis when appropriate. Break complex ideas into simple steps."
            )
        elif age <= 13:  # Class 7-8
            base_system = (
                f"You are a helpful tutor for a {age}-year-old student in Class {standard}. "
                f"Explain clearly with relevant examples. Use simple but proper language. "
                f"Make connections to everyday life. Be encouraging and supportive."
            )
        else:  # Class 9-10
            base_system = (
                f"You are an experienced teacher for a {age}-year-old student in Class {standard}. "
                f"Provide detailed explanations with examples and applications. "
                f"Use proper academic language while keeping it engaging."
            )
        
        # Build context string - PRIORITIZE NCERT CONTENT!
        full_context = ""
        if rag_context:
            full_context += f"\n\n📚 **FROM YOUR NCERT TEXTBOOK:**\n{rag_context}\n\n"
            full_context += "⚠️ **IMPORTANT:** Base your answer primarily on the NCERT textbook content above. "
            full_context += "This is the official curriculum content the student is learning."
        if web_context:
            full_context += f"\n\n**Additional Reference:**\n{web_context}"
        
        # User prompt with clear instructions
        if full_context:
            user_prompt = (
                f"Student's Question: {question}\n\n"
                f"{full_context}\n\n"
                f"Instructions:\n"
                f"1. Answer based MAINLY on the NCERT textbook content\n"
                f"2. Make it appropriate for Class {standard}\n"
                f"3. Use simple, clear language\n"
                f"4. Include examples from the textbook if available\n"
                f"5. Keep it engaging and encouraging"
            )
        else:
            user_prompt = f"Question: {question}"
        
        # Adjust for difficulty level
        system_prompt = adjust_prompt_for_difficulty(base_system, difficulty_level, user_context=user_prompt[:500])
        
        # Get conversation history for multi-turn context (last 5 messages)
        conversation_history = []
        try:
            recent_chats = ChatHistory.objects.filter(student=request.user).order_by('-created_at')[:5]
            # Reverse to get chronological order (oldest first)
            for chat in reversed(list(recent_chats)):
                conversation_history.append({
                    "question": chat.question,
                    "answer": chat.answer
                })
            if conversation_history:
                logger.info(f"📜 Including {len(conversation_history)} previous messages for context")
        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
        
        # Generate with AI
        model_used = model_choice
        
        # Try OpenAI
        if model_choice == "openai" or (model_choice != "gemini" and openai.api_key):
            try:
                # Build messages with conversation history
                messages = [{"role": "system", "content": system_prompt}]
                
                # Add conversation history
                for hist in conversation_history:
                    messages.append({"role": "user", "content": hist["question"]})
                    messages.append({"role": "assistant", "content": hist["answer"]})
                
                # Add current question
                messages.append({"role": "user", "content": user_prompt})
                
                response = openai.chat.completions.create(
                    model=RAG_SYSTEM["openai_model"],
                    messages=messages,
                    temperature=0.7,
                    max_tokens=800  # Increased for detailed answers
                )
                answer = response.choices[0].message.content
                logger.info(f"OpenAI response generated with conversation context")
                
            except Exception as openai_error:
                logger.error(f"OpenAI error: {str(openai_error)}")
                model_choice = "gemini"  # Fallback
        
        # Use Gemini if selected or as fallback
        if (model_choice == "gemini" or not answer) and os.getenv("GEMINI_API_KEY"):
            try:
                model = genai.GenerativeModel(RAG_SYSTEM["gemini_model"])
                
                # Build conversation context for Gemini
                conversation_context = ""
                if conversation_history:
                    conversation_context = "\n\n**Previous Conversation:**\n"
                    for hist in conversation_history:
                        conversation_context += f"Student: {hist['question']}\nYou: {hist['answer']}\n\n"
                    conversation_context += "**Current Question:**\n"
                
                full_prompt = f"{system_prompt}\n\n{conversation_context}{user_prompt}"
                response = model.generate_content(full_prompt)
                answer = response.text
                model_used = "gemini"
                logger.info(f"Gemini response generated with conversation context")
                
            except Exception as gemini_error:
                logger.error(f"Gemini error: {str(gemini_error)}")
                answer = "Sorry, I'm having trouble right now. Please try again."
        
        if not answer:
            return JsonResponse({
                "status": "error",
                "error": "Both AI models failed. Please try again later."
            }, status=500)
        
        # Format response based on difficulty
        answer = format_response_by_difficulty(answer, difficulty_level)
        
        # 5b. Generate Image if no images found and it's an educational query
        if not images and is_educational_query(question):
            try:
                logger.info("🎨 No images found, generating image with AI...")
                
                # Create image generation prompt based on the question
                if age <= 10:
                    image_prompt = f"Create a colorful, child-friendly illustration for: {question}. Make it fun and educational for a {age}-year-old."
                else:
                    image_prompt = f"Create an educational diagram or illustration explaining: {question}. Make it clear and informative for a Class {standard} student."
                
                # Try to generate image with DALL-E (OpenAI)
                if openai.api_key:
                    try:
                        response = openai.images.generate(
                            model="dall-e-3",
                            prompt=image_prompt[:1000],  # Limit prompt length
                            size="1024x1024",
                            quality="standard",
                            n=1
                        )
                        generated_image_url = response.data[0].url
                        images.append({
                            'url': generated_image_url,
                            'type': 'ai_generated',
                            'source': 'DALL-E 3'
                        })
                        logger.info("✅ Successfully generated image with DALL-E")
                        
                    except Exception as dalle_error:
                        logger.error(f"DALL-E image generation failed: {str(dalle_error)}")
                        
                        # Note: Gemini image generation not yet supported in this API
                        # Add a note to the answer instead
                        answer += "\n\n💡 *Image could not be generated. Try searching for '{question}' images online for visual reference.*"
                        
            except Exception as e:
                logger.error(f"Image generation error: {e}")
        
        # Cache the answer (10-day cache)
        if is_educational_query(question):
            try:
                ChatCache.objects.create(
                    question_hash=get_query_hash(question),
                    question=question,
                    answer=answer,
                    images=images if images else None,
                    sources=sources if sources else None,
                    difficulty_level=difficulty_level
                )
                logger.info("✅ Answer cached for future use")
            except Exception as e:
                logger.error(f"Failed to cache answer: {e}")

    
    # 6. Save to Permanent Memory if requested
    if save_to_memory:
        try:
            PermanentMemory.objects.create(
                student=request.user,
                question=question,
                answer=answer,
                images=images if images else None,
                sources=sources if sources else None,
                keywords=question[:200]
            )
            answer += "\n\n✅ **Saved to permanent memory!** I'll remember this for you."
            logger.info("Saved to permanent memory")
        except Exception as e:
            logger.error(f"Failed to save to permanent memory: {e}")
    
    # 7. Save to Chat History
    try:
        ChatHistory.objects.create(
            student=request.user,
            question=question,
            answer=answer,
            model_used=model_used if 'model_used' in locals() else model_choice,
            has_images=len(images) > 0,
            sources=sources if sources else None,
            difficulty_level=difficulty_level
        )
    except Exception as db_error:
        logger.error(f"Failed to save chat history: {db_error}")
    
    # 8. Return Enhanced Response with metadata
    return JsonResponse({
        "status": "success",
        "answer": answer,
        "images": images[:5] if images else [],  # Limit to 5 images
        "sources": sources[:10] if sources else [],  # Limit to 10 sources
        "difficulty_level": difficulty_level,
        "used_cache": used_cache,
        "rag_used": bool(rag_context),  # Did we use NCERT textbook content?
        "web_used": bool(web_context),  # Did we use web scraping?
        "context_found": context_found or bool(rag_context or web_context),
        "student_class": str(standard) if standard else None,
        "content_source": "ncert_textbook" if rag_context else ("web" if web_context else "ai_only")
    })

# --- Utility and Standard Views ---

@login_required
def student_dashboard(request):
    """
    Student dashboard showing recent chats and stats
    """
    recent_chats = ChatHistory.objects.filter(student=request.user).order_by('-created_at')[:10]
    total_chats = ChatHistory.objects.filter(student=request.user).count()
    
    context = {
        'recent_chats': recent_chats,
        'total_chats': total_chats,
        'user': request.user
    }
    
    return render(request, 'students/dashboard.html', context)


@login_required
def chatbot_page(request):
    """
    Main chatbot interface page
    """
    return render(request, 'students/chatbot.html', {'user': request.user})


def clean_old_chats():
    """
    Utility function to clean up old chat history (can be called via management command)
    """
    cutoff = timezone.now() - timedelta(days=30)
    deleted_count = ChatHistory.objects.filter(created_at__lt=cutoff).delete()[0]
    logger.info(f"Cleaned {deleted_count} old chat records")
    return deleted_count


# ==================== UNIT TEST VIEWS ====================

@login_required
def unit_test_list(request):
    """
    List available unit tests for students
    """
    from .models import UnitTest, UnitTestAttempt
    
    # Get all active unit tests
    tests = UnitTest.objects.filter(is_active=True).prefetch_related('chapters').order_by('-created_at')
    
    # Get student's attempts for each test
    test_data = []
    for test in tests:
        attempts = UnitTestAttempt.objects.filter(
            unit_test=test,
            student=request.user
        ).order_by('-started_at')
        
        best_score = 0
        if attempts.exists():
            best_attempt = attempts.filter(status='evaluated').order_by('-overall_score').first()
            if best_attempt:
                best_score = best_attempt.overall_score
        
        test_data.append({
            'test': test,
            'attempts_count': attempts.count(),
            'best_score': best_score,
            'latest_attempt': attempts.first()
        })
    
    context = {
        'test_data': test_data,
    }
    
    return render(request, 'students/unit_test_list.html', context)


@login_required
def unit_test_start(request, test_id):
    """
    Start a new unit test attempt
    """
    from .models import UnitTest, UnitTestAttempt
    from django.shortcuts import get_object_or_404, redirect
    
    test = get_object_or_404(UnitTest, id=test_id, is_active=True)
    
    # Check if there's an in-progress attempt
    existing_attempt = UnitTestAttempt.objects.filter(
        unit_test=test,
        student=request.user,
        status='in_progress'
    ).first()
    
    if existing_attempt:
        # Resume existing attempt
        return redirect('students:unit_test_take', attempt_id=existing_attempt.id)
    
    # Get next attempt number
    last_attempt = UnitTestAttempt.objects.filter(
        unit_test=test,
        student=request.user
    ).order_by('-attempt_number').first()
    
    attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
    
    # Create new attempt
    attempt = UnitTestAttempt.objects.create(
        unit_test=test,
        student=request.user,
        attempt_number=attempt_number,
        status='in_progress'
    )
    
    return redirect('students:unit_test_take', attempt_id=attempt.id)


@login_required
def unit_test_take(request, attempt_id):
    """
    Take/continue a unit test
    """
    from .models import UnitTestAttempt, UnitTestAnswer
    from django.shortcuts import get_object_or_404
    
    attempt = get_object_or_404(UnitTestAttempt, id=attempt_id, student=request.user, status='in_progress')
    questions = attempt.unit_test.questions.all().order_by('question_number')
    
    # Get existing answers
    existing_answers = {}
    for answer in UnitTestAnswer.objects.filter(attempt=attempt):
        existing_answers[answer.question.id] = answer.answer_text
    
    # Calculate time remaining
    elapsed_seconds = (timezone.now() - attempt.started_at).total_seconds()
    total_seconds = attempt.unit_test.duration_minutes * 60
    remaining_seconds = max(0, total_seconds - elapsed_seconds)
    
    context = {
        'attempt': attempt,
        'questions': questions,
        'existing_answers': existing_answers,
        'remaining_seconds': int(remaining_seconds),
    }
    
    return render(request, 'students/unit_test_take.html', context)


@login_required
@require_POST
def unit_test_submit(request, attempt_id):
    """
    Submit unit test for evaluation
    """
    from .models import UnitTestAttempt, UnitTestAnswer
    from .unit_test_evaluator import evaluator
    from django.shortcuts import get_object_or_404, redirect
    import json
    
    attempt = get_object_or_404(UnitTestAttempt, id=attempt_id, student=request.user, status='in_progress')
    
    # Save all answers
    questions = attempt.unit_test.questions.all()
    
    for question in questions:
        answer_text = request.POST.get(f'answer_{question.id}', '').strip()
        
        if answer_text:
            # Create or update answer
            UnitTestAnswer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={'answer_text': answer_text}
            )
    
    # Update attempt status
    attempt.status = 'submitted'
    attempt.submitted_at = timezone.now()
    attempt.time_taken_seconds = int((timezone.now() - attempt.started_at).total_seconds())
    attempt.save()
    
    # Evaluate the test asynchronously (or synchronously for now)
    try:
        evaluation_result = evaluator.evaluate_full_test(attempt.id)
        logger.info(f"Unit test {attempt.id} evaluated: {evaluation_result}")
    except Exception as e:
        logger.error(f"Error evaluating unit test {attempt.id}: {str(e)}")
        attempt.overall_feedback = "Evaluation in progress. Please check back in a few moments."
        attempt.save()
    
    return redirect('students:unit_test_results', attempt_id=attempt.id)


@login_required
def unit_test_results(request, attempt_id):
    """
    View unit test results with scores and heatmap
    """
    from .models import UnitTestAttempt, UnitTestAnswer
    from django.shortcuts import get_object_or_404
    
    attempt = get_object_or_404(UnitTestAttempt, id=attempt_id, student=request.user)
    
    # Get all answers with evaluations
    answers = UnitTestAnswer.objects.filter(attempt=attempt).select_related('question').order_by('question__question_number')
    
    # Calculate percentage
    if attempt.unit_test.total_marks > 0:
        percentage = (attempt.total_marks_obtained / attempt.unit_test.total_marks) * 100
    else:
        percentage = 0
    
    # Determine pass/fail
    passed = attempt.total_marks_obtained >= attempt.unit_test.passing_marks
    
    context = {
        'attempt': attempt,
        'answers': answers,
        'percentage': round(percentage, 2),
        'passed': passed,
    }
    
    return render(request, 'students/unit_test_results.html', context)