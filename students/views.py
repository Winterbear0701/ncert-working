import os
import logging
import json
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
    """
    Initializes Vector DB (Pinecone/ChromaDB), embedding model, and API keys.
    NOTE: ChromaDB folder creation is disabled - using vector_db_utils instead
    """
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

    # 2. Initialize Vector DB Manager (Pinecone in production, ChromaDB for local)
    # NOTE: No longer creating ChromaDB client here - using vector_db_utils
    # The vector_db_utils automatically handles Pinecone/ChromaDB based on VECTOR_DB env
    try:
        from ncert_project.vector_db_utils import get_vector_db_manager
        vector_manager = get_vector_db_manager()
        RAG_SYSTEM["vector_manager"] = vector_manager
        db_type = "Pinecone" if hasattr(vector_manager, 'index_name') else "ChromaDB"
        logger.info(f"[OK] Vector DB initialized: {db_type}")
    except Exception as e:
        logger.error(f"Error initializing Vector DB manager: {e}")
        return # Stop if database fails

    # 3. Initialize Embedding Model (can be slow, only do once)
    try:
        RAG_SYSTEM["embedding_model"] = SentenceTransformer('all-MiniLM-L6-v2')
    except Exception as e:
        logger.error(f"Error loading SentenceTransformer model: {e}")
        return

    # 4. Log successful initialization
    try:
        logger.info("RAG system initialization complete.")
    except Exception as e:
        logger.error(f"Error in RAG system initialization: {e}")

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
    
    # 2. Check for Simple Greetings/Social Responses (skip RAG for these)
    question_lower = question.lower().strip()
    
    # Define simple greeting patterns
    simple_greetings = [
        'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
        'bye', 'goodbye', 'see you', 'thanks', 'thank you', 'thx', 'ty',
        'ok', 'okay', 'cool', 'nice', 'great', 'awesome', 'got it',
        'yes', 'no', 'yup', 'nope', 'sure', 'alright'
    ]
    
    # Check if question is just a simple greeting (no RAG needed)
    is_simple_greeting = (
        len(question.split()) <= 3 and  # Short message
        any(greeting in question_lower for greeting in simple_greetings)
    )
    
    if is_simple_greeting:
        # Direct friendly responses without RAG/web scraping
        greeting_responses = {
            'hi': "Hello! 👋 I'm your NCERT AI tutor. Ask me anything about your textbooks!",
            'hello': "Hi there! 😊 Ready to learn something new today?",
            'hey': "Hey! 🌟 What would you like to learn about?",
            'good morning': "Good morning! ☀️ Let's make today a great learning day!",
            'good afternoon': "Good afternoon! 📚 How can I help you with your studies?",
            'good evening': "Good evening! 🌙 Ready for some learning?",
            'bye': "Goodbye! 👋 Keep learning and see you soon!",
            'goodbye': "Bye! 📚 Remember to review what you learned today!",
            'see you': "See you later! 🌟 Happy studying!",
            'thanks': "You're welcome! 😊 Anytime you need help, I'm here!",
            'thank you': "You're very welcome! 🌟 Happy to help you learn!",
            'thx': "No problem! 👍 Keep up the great work!",
            'ty': "Anytime! 😊 That's what I'm here for!",
            'ok': "Great! 👍 Let me know if you have any questions!",
            'okay': "Awesome! 🌟 Feel free to ask anything!",
            'cool': "Glad you think so! 😎 What else can I help with?",
            'nice': "Thank you! 😊 Ready for the next question?",
            'great': "Wonderful! 🎉 Keep that enthusiasm going!",
            'awesome': "You're awesome too! 🌟 Let's keep learning!",
            'got it': "Perfect! 👍 Let me know if you need more help!",
            'yes': "Alright! [OK] What would you like to know?",
            'no': "No worries! 😊 Feel free to ask if you change your mind!",
        }
        
        # Find matching response
        response = "I'm here to help! 😊 Ask me anything about your NCERT textbooks!"
        for keyword, resp in greeting_responses.items():
            if keyword in question_lower:
                response = resp
                break
        
        # Save to chat history and return
        try:
            chat_obj = ChatHistory.objects.create(
                student=request.user,
                question=question,
                answer=response,
                model_used="greeting_response",
                difficulty_level="casual"
            )
            # Sync to MongoDB
            try:
                from ncert_project.mongodb_utils import save_chat_to_mongo
                save_chat_to_mongo(
                    student_id=request.user.id,
                    question=question,
                    answer=response,
                    model_used="greeting_response",
                    created_at=chat_obj.created_at,
                    difficulty_level="casual"
                )
            except Exception as mongo_err:
                logger.warning(f"[WARNING]  Failed to sync chat to MongoDB: {mongo_err}")
        except Exception as e:
            logger.error(f"Error saving greeting to history: {e}")
        
        return JsonResponse({
            "status": "success",
            "answer": response,
            "images": [],
            "sources": [],
            "difficulty_level": "casual",
            "used_cache": False,
            "rag_used": False,
            "web_used": False,
            "is_greeting": True
        })
    
    # 3. Check for Memory Management Commands
    
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
                        "answer": "[OK] I've removed that from my permanent memory.",
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
            logger.info("[OK] Answer from permanent memory")
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
                logger.info(f"[OK] Answer from cache (hit count: {cache_entry.hit_count})")
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
    
    # TIER 3: If no cache hit, ALWAYS perform RAG search (prevent hallucination)
    rag_context = ""
    context_found = False
    web_context = ""
    
    if not used_cache:
        # 3a. Vector DB RAG Retrieval (PRIMARY SOURCE - ALWAYS SEARCH FIRST!)
        # Uses Pinecone in production, ChromaDB for local
        try:
            from ncert_project.vector_db_utils import get_vector_db_manager
            vector_manager = get_vector_db_manager()
            db_type = "Pinecone" if hasattr(vector_manager, 'index_name') else "ChromaDB"
            
            # Query vector DB ACROSS ALL CHAPTERS in student's class
            # This allows finding answers even if student doesn't know which chapter contains the info
            # Example: "What is dune?" → Searches all Class 5 chapters, finds Geography chapter
            logger.info(f"[SEARCH] Querying {db_type} (RAG) across ALL chapters for Class {standard}: {question[:50]}...")
            results = vector_manager.query_by_class_subject_chapter(
                query_text=question,
                class_num=str(standard) if standard else None,
                subject=None,  # Don't filter by subject - let semantic search find it
                chapter=None,  # IMPORTANT: Don't filter by chapter - search ALL chapters!
                n_results=20  # Get maximum relevant chunks for comprehensive answer
            )
            
            # Extract and format context from Vector DB results
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                context_parts = []
                
                # Track which chapters were found (for logging cross-chapter search)
                chapters_found = set()
                subjects_found = set()
                
                for i, doc in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    similarity = 1 - distances[i] if i < len(distances) else 0
                    
                    # Track chapters and subjects
                    if meta.get('chapter'):
                        chapters_found.add(meta.get('chapter'))
                    if meta.get('subject'):
                        subjects_found.add(meta.get('subject'))
                    
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
                
                # Log cross-chapter search results
                logger.info(f"[OK] Found {len(documents)} relevant chunks from NCERT textbooks ({db_type})")
                logger.info(f"   [BOOK] Subjects found: {', '.join(subjects_found)}")
                logger.info(f"   [BOOK] Chapters found: {', '.join(sorted(chapters_found))}")
                if len(chapters_found) > 1:
                    logger.info(f"   [SUCCESS] Cross-chapter search successful! Found content from {len(chapters_found)} different chapters")
            else:
                logger.info(f"[WARNING]  No relevant content found in {db_type}")
                
        except Exception as e:
            logger.error(f"[ERROR] Error during Vector DB RAG retrieval: {e}")
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
                    logger.info(f"[OK] Web scraping added {len(web_data['images'])} images")
                        
            except Exception as e:
                logger.error(f"[WARNING]  Web scraping error: {e}")
        else:
            # NO RAG CONTENT FOUND - Return "no content" message instead of hallucinating
            logger.warning("[ERROR] No RAG content found - returning 'no content' message")
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
        
        # Build context string - CRITICAL: ONLY USE NCERT CONTENT!
        full_context = ""
        if rag_context:
            full_context += f"\n\n📚 **FROM YOUR NCERT TEXTBOOK:**\n{rag_context}\n\n"
            full_context += ("ℹ️ **NOTE:** This content includes:\n"
                           "- Regular text from the textbook\n"
                           "- OCR-extracted text from diagrams, maps, charts, and images\n"
                           "- Labels and annotations from visual elements\n"
                           "- Questions from 'Let us reflect', 'Activity', 'Discuss', and 'Do you know' sections\n\n")
            full_context += ("[WARNING] **CRITICAL INSTRUCTION - DO NOT HALLUCINATE:**\n"
                           "- Answer ONLY using the NCERT textbook content provided above\n"
                           "- When referring to diagrams/images, mention 'Based on the textbook diagram/map...'\n"
                           "- If the question cannot be answered with the given content, say so clearly\n"
                           "- DO NOT make up information or use knowledge outside this textbook content\n"
                           "- This is the official curriculum - accuracy is more important than completeness\n")
        if web_context:
            full_context += f"\n\n**Additional Reference (use sparingly):**\n{web_context}"
        
        # User prompt with STRICT instructions
        if full_context:
            user_prompt = (
                f"Student's Question: {question}\n\n"
                f"{full_context}\n\n"
                f"STRICT Answer Instructions:\n"
                f"1. Answer ONLY using the NCERT textbook content shown above (includes text AND OCR-extracted image content)\n"
                f"2. If question asks about diagrams/maps/charts, use the OCR-extracted labels and descriptions\n"
                f"3. If the textbook content doesn't answer the question, say: 'I couldn't find this specific information in your textbook'\n"
                f"4. DO NOT add information from general knowledge\n"
                f"5. Make it appropriate for Class {standard}\n"
                f"6. Use simple, clear language from the textbook\n"
                f"7. Quote or reference the textbook content directly\n"
                f"8. For visual elements, say 'According to the textbook diagram/map...' or 'As shown in the chart...'\n"
                f"9. Keep it engaging but ACCURATE to the textbook ONLY"
            )
        else:
            # This shouldn't happen due to check above, but just in case
            user_prompt = (
                f"Question: {question}\n\n"
                f"I couldn't find relevant content in the NCERT textbooks for this question. "
                f"Please ask about topics from your NCERT textbooks."
            )
        
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
                        logger.info("[OK] Successfully generated image with DALL-E")
                        
                    except Exception as dalle_error:
                        logger.error(f"DALL-E image generation failed: {str(dalle_error)}")
                        
                        # Note: Gemini image generation not yet supported in this API
                        # Add a note to the answer instead
                        answer += "\n\n💡 *Image could not be generated. Try searching for '{question}' images online for visual reference.*"
                        
            except Exception as e:
                logger.error(f"Image generation error: {e}")
        
        # Cache the answer with quality control (adaptive expiry based on quality)
        if is_educational_query(question):
            try:
                # Calculate quality score based on RAG relevance
                quality_score = 1.0  # Default high quality
                avg_relevance = 0.0
                
                if rag_context and results and results.get("distances"):
                    # Calculate average relevance from RAG results
                    distances = results["distances"][0] if results["distances"] else []
                    if distances:
                        relevances = [1 - d for d in distances]  # Convert distance to similarity
                        avg_relevance = sum(relevances) / len(relevances)
                        
                        # Quality score based on RAG relevance
                        if avg_relevance >= 0.7:
                            quality_score = 1.0  # Excellent
                        elif avg_relevance >= 0.5:
                            quality_score = 0.8  # Good
                        elif avg_relevance >= 0.3:
                            quality_score = 0.6  # Fair
                        else:
                            quality_score = 0.4  # Low quality
                else:
                    # No RAG context = lower quality (AI-only answer)
                    quality_score = 0.5
                    avg_relevance = 0.0
                
                ChatCache.objects.create(
                    question_hash=get_query_hash(question),
                    question=question,
                    answer=answer,
                    images=images if images else None,
                    sources=sources if sources else None,
                    difficulty_level=difficulty_level,
                    quality_score=quality_score,
                    has_rag_context=bool(rag_context),
                    rag_relevance=avg_relevance
                )
                
                # Log cache duration based on quality
                cache_days = 10 if quality_score >= 0.7 else (3 if quality_score >= 0.5 else 1)
                logger.info(f"[OK] Answer cached for {cache_days} days (quality: {quality_score:.2f}, RAG: {avg_relevance:.2f})")
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
            answer += "\n\n[OK] **Saved to permanent memory!** I'll remember this for you."
            logger.info("Saved to permanent memory")
        except Exception as e:
            logger.error(f"Failed to save to permanent memory: {e}")
    
    # 7. Save to Chat History
    try:
        chat_obj = ChatHistory.objects.create(
            student=request.user,
            question=question,
            answer=answer,
            model_used=model_used if 'model_used' in locals() else model_choice,
            has_images=len(images) > 0,
            sources=sources if sources else None,
            difficulty_level=difficulty_level
        )
        # Sync to MongoDB
        try:
            from ncert_project.mongodb_utils import save_chat_to_mongo
            save_chat_to_mongo(
                student_id=request.user.id,
                question=question,
                answer=answer,
                model_used=chat_obj.model_used,
                created_at=chat_obj.created_at,
                has_images=len(images) > 0,
                sources=sources if sources else [],
                difficulty_level=difficulty_level
            )
        except Exception as mongo_err:
            logger.warning(f"[WARNING]  Failed to sync chat to MongoDB: {mongo_err}")
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


@login_required
def report_wrong_answer(request):
    """
    Report a wrong/bad chatbot answer - invalidates cache
    Allows students to flag incorrect answers to prevent caching
    """
    if request.method != 'POST':
        return JsonResponse({"status": "error", "error": "POST required"}, status=405)
    
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        reason = data.get('reason', 'Wrong answer')  # Optional: why it's wrong
        
        if not question:
            return JsonResponse({
                "status": "error",
                "error": "Question is required"
            }, status=400)
        
        # Get the cache entry for this question
        query_hash = get_query_hash(question)
        cache_entry = ChatCache.objects.filter(question_hash=query_hash).first()
        
        if cache_entry:
            # Report negative feedback and potentially invalidate
            cache_entry.report_negative_feedback()
            
            logger.warning(f"[WARNING]  Wrong answer reported by user {request.user.id}: {question[:50]}... "
                         f"(Feedback count: {cache_entry.negative_feedback_count}, Reason: {reason})")
            
            # Return status
            if cache_entry.is_invalidated:
                return JsonResponse({
                    "status": "success",
                    "message": "[OK] Thanks for reporting! This answer has been removed from cache and won't be shown again.",
                    "invalidated": True
                })
            else:
                return JsonResponse({
                    "status": "success",
                    "message": "[OK] Thanks for the feedback! We're tracking this answer's quality.",
                    "invalidated": False,
                    "feedback_count": cache_entry.negative_feedback_count
                })
        else:
            # No cache entry found (might already be cleared or never cached)
            return JsonResponse({
                "status": "success",
                "message": "[OK] Thanks for reporting! This question will be re-evaluated next time.",
                "cache_found": False
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON"
        }, status=400)
    except Exception as e:
        logger.error(f"Error reporting wrong answer: {e}")
        return JsonResponse({
            "status": "error",
            "error": "Failed to report feedback"
        }, status=500)


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
def unit_test_save_draft(request, attempt_id):
    """
    Save draft answers without submitting
    """
    from .models import UnitTestAttempt, UnitTestAnswer
    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    
    try:
        attempt = get_object_or_404(UnitTestAttempt, id=attempt_id, student=request.user, status='in_progress')
        
        # Save all answers
        questions = attempt.unit_test.questions.all()
        saved_count = 0
        
        for question in questions:
            answer_text = request.POST.get(f'answer_{question.id}', '').strip()
            
            if answer_text:
                # Create or update answer
                UnitTestAnswer.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={'answer_text': answer_text}
                )
                saved_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Draft saved successfully! {saved_count} answers saved.',
            'saved_count': saved_count
        })
    
    except Exception as e:
        logger.error(f"Error saving draft for attempt {attempt_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Error saving draft. Please try again.'
        }, status=500)


@login_required
@require_POST
def unit_test_submit(request, attempt_id):
    """
    Submit unit test for evaluation
    Supports optional AI model selection (Gemini or OpenAI)
    """
    from .models import UnitTestAttempt, UnitTestAnswer
    from .unit_test_evaluator import evaluator
    from django.shortcuts import get_object_or_404, redirect
    import json
    import os
    
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
    
    # Get AI model preference (from POST, settings, or default to gemini)
    ai_model = request.POST.get('ai_model', os.environ.get('DEFAULT_EVAL_AI', 'gemini'))
    
    # Evaluate the test with selected AI model
    try:
        evaluation_result = evaluator.evaluate_full_test(attempt.id, ai_model=ai_model)
        logger.info(f"Unit test {attempt.id} evaluated with {ai_model.upper()}: {evaluation_result}")
    except Exception as e:
        logger.error(f"Error evaluating unit test {attempt.id}: {str(e)}")
        attempt.overall_feedback = "⏳ Evaluation in progress. Please check back in a few moments."
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


@login_required
def unit_test_analytics(request, test_id):
    """
    View detailed analytics for a specific unit test
    """
    from .models import UnitTest, UnitTestAttempt, UnitTestAnswer
    from django.shortcuts import get_object_or_404
    from django.db.models import Avg, Max, Min, Count
    
    unit_test = get_object_or_404(UnitTest, id=test_id)
    
    # Get all attempts by this student for this test
    attempts = UnitTestAttempt.objects.filter(
        unit_test=unit_test,
        student=request.user,
        status='evaluated'
    ).order_by('created_at')
    
    if not attempts.exists():
        context = {
            'unit_test': unit_test,
            'attempts': None,
        }
        return render(request, 'students/unit_test_analytics.html', context)
    
    # Calculate statistics
    scores = [attempt.total_marks_obtained for attempt in attempts]
    percentages = [(score / unit_test.total_marks * 100) if unit_test.total_marks > 0 else 0 for score in scores]
    
    best_score = max(percentages)
    average_score = sum(percentages) / len(percentages)
    latest_score = percentages[-1] if percentages else 0
    
    # Calculate improvement
    if len(percentages) >= 2:
        improvement = percentages[-1] - percentages[0]
    else:
        improvement = 0
    
    # Get question-wise performance from best attempt
    best_attempt = max(attempts, key=lambda a: a.total_marks_obtained)
    answers = UnitTestAnswer.objects.filter(attempt=best_attempt).select_related('question')
    
    # Question-wise analysis
    question_performance = []
    for answer in answers:
        question = answer.question
        percentage_scored = (answer.awarded_marks / question.marks * 100) if question.marks > 0 else 0
        
        question_performance.append({
            'question_number': question.question_number,
            'question_text': question.question_text[:100] + '...' if len(question.question_text) > 100 else question.question_text,
            'marks': question.marks,
            'awarded_marks': answer.awarded_marks,
            'percentage': round(percentage_scored, 1),
            'content_score': answer.content_score * 100 if answer.content_score else 0,
            'grammar_score': answer.grammar_score * 100 if answer.grammar_score else 0,
            'feedback': answer.ai_feedback,
        })
    
    # Calculate average content and grammar scores
    content_scores = [q['content_score'] for q in question_performance]
    grammar_scores = [q['grammar_score'] for q in question_performance]
    
    avg_content = sum(content_scores) / len(content_scores) if content_scores else 0
    avg_grammar = sum(grammar_scores) / len(grammar_scores) if grammar_scores else 0
    
    # Prepare chart data
    attempt_labels = [f"Attempt {i+1}" for i in range(len(percentages))]
    
    context = {
        'unit_test': unit_test,
        'attempts': attempts,
        'total_attempts': len(attempts),
        'best_score': round(best_score, 1),
        'average_score': round(average_score, 1),
        'latest_score': round(latest_score, 1),
        'improvement': round(improvement, 1),
        'question_performance': question_performance,
        'avg_content': round(avg_content, 1),
        'avg_grammar': round(avg_grammar, 1),
        'attempt_labels': attempt_labels,
        'percentages': percentages,
        'best_attempt': best_attempt,
    }
    
    return render(request, 'students/unit_test_analytics.html', context)


@login_required
def smart_test_analysis(request):
    """
    Smart probability-based test analysis
    Analyzes previous test papers and identifies important chapters/topics
    Fast computation without chatbot format
    """
    from .test_analyzer import get_student_analysis
    import json
    
    logger.info(f"[STATS] Smart Analysis requested by: {request.user.email}")
    
    try:
        # Get comprehensive analysis
        analysis_data = get_student_analysis(request.user)
        
        context = {
            'analysis': analysis_data,
            'analysis_json': json.dumps(analysis_data, default=str),  # For JS processing
        }
        
        return render(request, 'students/smart_analysis.html', context)
        
    except Exception as e:
        logger.error(f"Error in smart analysis: {str(e)}", exc_info=True)
        context = {
            'error': str(e),
            'analysis': None,
        }
        return render(request, 'students/smart_analysis.html', context)


@login_required
def previous_papers_upload(request):
    """
    Upload previous year question papers (PDFs)
    """
    from .models import PreviousYearPaper
    
    if request.method == 'POST':
        from django.core.files.storage import default_storage
        import json
        
        try:
            # Get form data
            title = request.POST.get('title')
            standard = request.POST.get('standard')
            subject = request.POST.get('subject')
            exam_type = request.POST.get('exam_type', 'Final Exam')
            year = request.POST.get('year')
            
            # Get uploaded file
            pdf_file = request.FILES.get('pdf_file')
            
            if not pdf_file:
                return JsonResponse({'error': 'No file uploaded'}, status=400)
            
            # Validate PDF
            if not pdf_file.name.endswith('.pdf'):
                return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            
            # Create paper record
            paper = PreviousYearPaper.objects.create(
                student=request.user,
                title=title,
                standard=standard,
                subject=subject,
                exam_type=exam_type,
                year=year,
                pdf_file=pdf_file,
                status='uploaded'
            )
            
            logger.info(f"[DOC] Paper uploaded: {title} by {request.user.email}")
            
            return JsonResponse({
                'success': True,
                'paper_id': paper.id,
                'message': 'Paper uploaded successfully'
            })
            
        except Exception as e:
            logger.error(f"Error uploading paper: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    # GET request - show upload form
    papers = PreviousYearPaper.objects.filter(student=request.user).order_by('-uploaded_at')
    
    context = {
        'papers': papers,
        'standards': ['10', '11', '12'],
        'subjects': ['Mathematics', 'Science', 'Physics', 'Chemistry', 'Biology', 'English', 'Hindi'],
    }
    
    return render(request, 'students/paper_upload.html', context)


@login_required
def analyze_papers(request):
    """
    Analyze uploaded papers using RAG
    """
    from .models import PreviousYearPaper, PaperAnalysis
    from .paper_analyzer import PaperAnalyzer
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        paper_ids = request.POST.getlist('paper_ids[]')
        available_days = int(request.POST.get('available_days', 30))
        
        if not paper_ids:
            return JsonResponse({'error': 'No papers selected'}, status=400)
        
        logger.info(f"[SEARCH] Analyzing {len(paper_ids)} papers for {request.user.email}")
        
        # Get papers
        papers = PreviousYearPaper.objects.filter(
            id__in=paper_ids,
            student=request.user
        )
        
        if not papers.exists():
            return JsonResponse({'error': 'No valid papers found'}, status=404)
        
        # Initialize analyzer
        analyzer = PaperAnalyzer()
        
        # Process each paper
        all_questions = []
        combined_chapter_scores = {}
        
        for paper in papers:
            # Update status
            paper.status = 'processing'
            paper.save()
            
            # Get paper path
            paper_path = paper.pdf_file.path
            
            # Process paper
            result = analyzer.process_paper(
                paper_path,
                paper.standard,
                paper.subject,
                available_days
            )
            
            if 'error' not in result:
                # Update paper with extraction results
                paper.extracted_text = result.get('extracted_text', '')
                paper.total_questions = result.get('total_questions', 0)
                paper.questions_list = result.get('questions_list', [])
                paper.status = 'analyzed'
                paper.processed_at = timezone.now()
                paper.save()
                
                all_questions.extend(result.get('questions_list', []))
                
                # Merge chapter scores
                for chapter, data in result.get('chapter_importance', {}).items():
                    if chapter not in combined_chapter_scores:
                        combined_chapter_scores[chapter] = {
                            'frequency': 0,
                            'total_marks': 0,
                            'questions': [],
                            'topics': set()
                        }
                    combined_chapter_scores[chapter]['frequency'] += data.get('frequency', 0)
                    combined_chapter_scores[chapter]['total_marks'] += data.get('total_marks', 0)
                    combined_chapter_scores[chapter]['questions'].extend(data.get('questions', []))
                    combined_chapter_scores[chapter]['topics'].update(data.get('topics', []))
            else:
                paper.status = 'failed'
                paper.save()
                logger.error(f"Failed to process paper {paper.id}: {result.get('error')}")
        
        # Recalculate combined scores
        analyzer._calculate_importance_scores(combined_chapter_scores, len(all_questions))
        
        # Sort chapters
        sorted_chapters = sorted(
            combined_chapter_scores.items(),
            key=lambda x: x[1]['importance_score'],
            reverse=True
        )
        
        # Convert sets to lists for JSON
        for chapter_data in combined_chapter_scores.values():
            chapter_data['topics'] = list(chapter_data['topics'])
        
        # Generate study strategy
        analysis_data = {
            'chapter_importance': dict(sorted_chapters),
            'total_questions': len(all_questions),
            'priority_chapters': analyzer._get_priority_list(sorted_chapters, 10),
        }
        
        strategy = analyzer.generate_study_strategy(analysis_data, available_days)
        
        # Create or update analysis record
        analysis, created = PaperAnalysis.objects.update_or_create(
            student=request.user,
            standard=papers.first().standard,
            subject=papers.first().subject,
            defaults={
                'chapter_importance': dict(sorted_chapters),
                'topic_importance': {},
                'priority_chapters': analysis_data['priority_chapters'],
                'priority_topics': [],
                'study_strategy': strategy,
                'estimated_study_hours': strategy.get('daily_hours_needed', 0) * available_days,
                'analysis_completed_at': timezone.now()
            }
        )
        
        # Add papers to analysis
        analysis.papers.set(papers)
        
        logger.info(f"[OK] Analysis complete for {request.user.email}")
        
        return JsonResponse({
            'success': True,
            'analysis_id': analysis.id,
            'redirect_url': f'/students/papers/results/{analysis.id}/'
        })
        
    except Exception as e:
        logger.error(f"Error analyzing papers: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def paper_analysis_results(request, analysis_id):
    """
    Display analysis results
    """
    from .models import PaperAnalysis
    import json
    
    try:
        analysis = PaperAnalysis.objects.get(
            id=analysis_id,
            student=request.user
        )
        
        context = {
            'analysis': analysis,
            'papers': analysis.papers.all(),
            'chapter_importance': analysis.chapter_importance,
            'priority_chapters': analysis.priority_chapters,
            'study_strategy': analysis.study_strategy,
            'analysis_json': json.dumps({
                'chapter_importance': analysis.chapter_importance,
                'priority_chapters': analysis.priority_chapters,
                'study_strategy': analysis.study_strategy,
            }, default=str)
        }
        
        return render(request, 'students/paper_analysis_results.html', context)
        
    except PaperAnalysis.DoesNotExist:
        logger.error(f"Analysis {analysis_id} not found for {request.user.email}")
        return render(request, 'students/paper_analysis_results.html', {
            'error': 'Analysis not found'
        })
    except Exception as e:
        logger.error(f"Error displaying results: {str(e)}", exc_info=True)
        return render(request, 'students/paper_analysis_results.html', {
            'error': str(e)
        })