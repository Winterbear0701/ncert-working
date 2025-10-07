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
    "gemini_model": "gemini-2.5-flash",  # Updated to latest Gemini 2.5 Flash model
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
    
    # Check if this is a simple greeting/response (no need for RAG)
    if not is_educational_query(question):
        # Simple response - use AI directly
        logger.info("Simple query detected, responding directly")
        pass  # Will generate answer below
    else:
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
    
    # TIER 3: If no cache hit, perform full RAG + Web Scraping
    rag_context = ""
    context_found = False
    web_context = ""
    
    if not used_cache and is_educational_query(question):
        # 3a. ChromaDB RAG Retrieval
        where_filter = {}
        try:
            collection = RAG_SYSTEM["collection"]
            if collection is None:
                raise RuntimeError("ChromaDB collection is not available.")
                
            # Get student's standard for filtering
            student_standard = getattr(request.user, 'standard', None)
            if student_standard:
                where_filter = {"standard": str(student_standard)}
            
            # Generate query embedding
            query_embedding = get_embedding(question)
            
            # Retrieve relevant chunks from ChromaDB
            logger.info(f"Querying ChromaDB for: {question[:50]}...")
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=5,  # Get top 5 most relevant chunks
                where=where_filter if where_filter else None
            )
            
            # Extract and format context
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                context_parts = []
                
                for i, doc in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    source_ref = (f"[Std {meta.get('standard', '?')}, {meta.get('subject', '?')}, "
                                 f"Ch {meta.get('chapter', '?')}, Page {meta.get('page', '?')}]")
                    context_parts.append(f"{source_ref}\n{doc}")
                    
                    # Add source to sources list
                    sources.append({
                        'name': f"{meta.get('subject', 'NCERT')} - Chapter {meta.get('chapter', '?')}",
                        'type': 'pdf',
                        'page': meta.get('page')
                    })
                
                rag_context = "\n\n".join(context_parts)
                context_found = True
                logger.info(f"Found {len(documents)} relevant chunks from ChromaDB")
                
        except RuntimeError as e:
            logger.error(f"RAG System Unavailable: {e}")
        except Exception as e:
            logger.error(f"Error during RAG retrieval: {e}")
        
        # 3b. Web Scraping for Additional Context
        try:
            logger.info("Performing web scraping...")
            web_data = scrape_multiple_sources(question, include_images=True)
            
            if web_data['success']:
                web_context = web_data['content']
                images.extend(web_data['images'])
                sources.extend(web_data['sources'])
                logger.info(f"Web scraping added {len(web_data['images'])} images, {len(web_data['sources'])} sources")
        except Exception as e:
            logger.error(f"Web scraping error: {e}")
    
    
    # 5. Generate Answer with AI (if not from cache)
    if not answer:
        # Build prompts with difficulty adaptation
        age = getattr(request.user, 'age', 12)
        standard = getattr(request.user, 'standard', 'middle school')
        
        # Base system prompt
        base_system = (
            f"You are a helpful, friendly AI tutor for a {age}-year-old student in standard {standard}. "
            f"Answer questions clearly and engagingly. Be encouraging and make learning fun."
        )
        
        # Build context string
        full_context = ""
        if rag_context:
            full_context += f"\n\n**NCERT Textbook Context:**\n{rag_context}"
        if web_context:
            full_context += f"\n\n**Additional Educational Content:**\n{web_context}"
        
        # User prompt
        if full_context:
            user_prompt = f"Question: {question}{full_context}\n\nPlease provide a comprehensive answer using the above context."
        else:
            user_prompt = f"Question: {question}"
        
        # Adjust for difficulty level
        system_prompt = adjust_prompt_for_difficulty(base_system, difficulty_level, user_context=user_prompt[:500])
        
        # Generate with AI
        model_used = model_choice
        
        # Try OpenAI
        if model_choice == "openai" or (model_choice != "gemini" and openai.api_key):
            try:
                response = openai.chat.completions.create(
                    model=RAG_SYSTEM["openai_model"],
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=800  # Increased for detailed answers
                )
                answer = response.choices[0].message.content
                logger.info(f"OpenAI response generated")
                
            except Exception as openai_error:
                logger.error(f"OpenAI error: {str(openai_error)}")
                model_choice = "gemini"  # Fallback
        
        # Use Gemini if selected or as fallback
        if (model_choice == "gemini" or not answer) and os.getenv("GEMINI_API_KEY"):
            try:
                model = genai.GenerativeModel(RAG_SYSTEM["gemini_model"])
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                response = model.generate_content(full_prompt)
                answer = response.text
                model_used = "gemini"
                logger.info(f"Gemini response generated")
                
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
                logger.info("Answer cached for future use")
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
    
    # 8. Return Enhanced Response
    return JsonResponse({
        "status": "success",
        "answer": answer,
        "images": images[:5] if images else [],  # Limit to 5 images
        "sources": sources[:10] if sources else [],  # Limit to 10 sources
        "difficulty_level": difficulty_level,
        "used_cache": used_cache,
        "context_found": context_found or bool(rag_context or web_context)
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