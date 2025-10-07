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
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from .models import ChatHistory
import openai
import google.generativeai as genai

logger = logging.getLogger(__name__)

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
        chroma_client = chromadb.Client(ChromaSettings(
            persist_directory=chroma_persist_dir,
            anonymized_telemetry=False
        ))
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
    AI Chatbot with RAG - retrieves context from ChromaDB and generates answer using OpenAI or Gemini
    """
    # 1. Input Validation and Retrieval
    question = request.POST.get("question", "").strip()
    model_choice = request.POST.get("model", "openai").lower()
    
    if not question:
        return JsonResponse({"status": "error", "error": "Question cannot be empty"}, status=400)
    
    # 2. ChromaDB RAG Retrieval
    rag_context = ""
    where_filter = {}
    context_found = False

    try:
        collection = RAG_SYSTEM["collection"]
        if collection is None:
            raise RuntimeError("ChromaDB collection is not available.")
            
        # Get student's standard for filtering (using defaults if user object is missing attributes)
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
                source = (f"[Std {meta.get('standard', '?')}, {meta.get('subject', '?')}, "
                          f"Ch {meta.get('chapter', '?')}]")
                context_parts.append(f"{source}\n{doc}")
            
            rag_context = "\n\n".join(context_parts)
            context_found = True
            
    except RuntimeError as e:
        logger.error(f"RAG System Unavailable: {e}")
        # Allow system to continue with general knowledge if RAG fails
    except Exception as e:
        logger.error(f"Error during RAG retrieval: {e}")
        # Allow system to continue with general knowledge if RAG fails

    # Fallback message if no context found
    if not rag_context:
        rag_context = "No specific NCERT content found. Providing general knowledge answer."
    
    
    # 3. Build Prompts - Make chatbot more versatile
    # Use defaults if user object is missing attributes
    age = getattr(request.user, 'age', 12)
    standard = getattr(request.user, 'standard', 'middle school')
    
    # Check if this is a general question or NCERT-specific
    is_general_question = not context_found or "No specific NCERT content found" in rag_context
    
    if is_general_question:
        # For general questions, be a friendly helpful assistant
        system_prompt = (
            f"You are a helpful, friendly AI tutor for a {age}-year-old student in standard {standard}. "
            f"Answer questions clearly and engagingly. You can discuss any topic - from homework help to "
            f"general knowledge, science, math, history, or even casual conversation. "
            f"Be encouraging and make learning fun. If you don't know something, admit it honestly."
        )
        user_prompt = f"Question: {question}"
    else:
        # For NCERT-specific questions, use the context
        system_prompt = (
            f"You are an expert NCERT tutor helping a {age}-year-old student in standard {standard}. "
            f"Explain concepts clearly and simply, suitable for their age and grade level. "
            f"Use the provided NCERT context to give accurate, curriculum-aligned answers. "
            f"If needed, supplement with additional knowledge but stay accurate."
        )
        user_prompt = f"Question: {question}\n\nNCERT Context:\n{rag_context}"
    
    
    # 4. Generate Answer using LLMs
    answer = ""
    
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
                max_tokens=500
            )
            answer = response.choices[0].message.content
            logger.info(f"OpenAI response generated for: {question[:30]}")
            
        except Exception as openai_error:
            logger.error(f"OpenAI error (falling back to Gemini if configured): {str(openai_error)}")
            # Fallback to Gemini by changing model_choice
            model_choice = "gemini" 
    
    # Use Gemini if selected, or as fallback
    if model_choice == "gemini" and os.getenv("GEMINI_API_KEY"):
        try:
            model = genai.GenerativeModel(RAG_SYSTEM["gemini_model"])
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = model.generate_content(full_prompt)
            answer = response.text
            logger.info(f"Gemini response generated for: {question[:30]}")
            
        except Exception as gemini_error:
            logger.error(f"Gemini error: {str(gemini_error)}")
            answer = "Sorry, I'm having trouble generating a response right now. Please try again later (Error: LLM issue)."
    
    # Final check if both failed
    if not answer or "Error: LLM issue" in answer:
        return JsonResponse({
            "status": "error", 
            "error": answer if answer else "Both LLMs failed to produce a response."
        }, status=500)


    # 5. Save and Respond
    try:
        ChatHistory.objects.create(
            student=request.user,
            question=question,
            answer=answer,
            model_used=model_choice # Save which model was used
        )
    except Exception as db_error:
        logger.error(f"Failed to save chat history: {db_error}")

    
    return JsonResponse({
        "status": "success",
        "answer": answer,
        "model_used": model_choice,
        "context_found": context_found
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