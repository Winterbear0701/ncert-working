import os
import logging
from datetime import timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from .models import ChatHistory
import openai
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Initialize OpenAI and Gemini
openai.api_key = os.getenv("OPENAI_API_KEY")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize ChromaDB with persistent storage (same as in tasks.py)
chroma_persist_dir = getattr(settings, 'CHROMA_PERSIST_DIRECTORY', 'chromadb_data')
chroma_client = chromadb.Client(ChromaSettings(
    persist_directory=chroma_persist_dir,
    anonymized_telemetry=False
))

# Initialize embedding model (same as in tasks.py)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embedding(text):
    """Generate embedding for a single text"""
    return embedding_model.encode(text).tolist()

# Get or create collection
collection = chroma_client.get_or_create_collection(
    name="ncert_books",
    metadata={"description": "NCERT textbook embeddings by standard, subject, and chapter"}
)

@login_required
def ask_chatbot(request):
    """
    AI Chatbot with RAG - retrieves context from ChromaDB and generates answer using OpenAI or Gemini
    """
    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        model_choice = request.POST.get("model", "openai")
        
        if not question:
            return JsonResponse({"error": "Question cannot be empty"}, status=400)
        
        try:
            # Get student's standard for filtering
            student_standard = getattr(request.user, 'standard', None)
            
            # Generate query embedding
            query_embedding = get_embedding(question)
            
            # Build metadata filter if standard is available
            where_filter = {}
            if student_standard:
                where_filter = {"standard": str(student_standard)}
            
            # Retrieve relevant chunks from ChromaDB
            logger.info(f"Querying ChromaDB for: {question[:50]}...")
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=5,  # Get top 5 most relevant chunks
                where=where_filter if where_filter else None
            )
            
            # Extract context from results
            rag_context = ""
            if results and results.get("documents") and results["documents"][0]:
                # Format context with metadata
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                
                context_parts = []
                for i, doc in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    source = f"[Std {meta.get('standard', '?')}, {meta.get('subject', '?')}, Ch {meta.get('chapter', '?')}]"
                    context_parts.append(f"{source}\n{doc}")
                
                rag_context = "\n\n".join(context_parts)
            
            # Fallback message if no context found
            if not rag_context:
                rag_context = "No specific NCERT content found. Providing general knowledge answer."
            
            # Build system prompt
            age = getattr(request.user, 'age', 12)
            standard = getattr(request.user, 'standard', 'middle school')
            
            system_prompt = (
                f"You are an expert NCERT tutor helping a {age}-year-old student in standard {standard}. "
                f"Explain concepts clearly and simply, suitable for their age and grade level. "
                f"Use the provided NCERT context to give accurate, curriculum-aligned answers. "
                f"If the context doesn't fully answer the question, supplement with your knowledge but stay accurate."
            )
            
            user_prompt = f"Question: {question}\n\nNCERT Context:\n{rag_context}"
            
            # Generate answer using selected model
            answer = ""
            
            if model_choice == "openai":
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-4o-mini",
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
                    logger.error(f"OpenAI error: {str(openai_error)}")
                    # Fallback to Gemini
                    model_choice = "gemini"
            
            # Use Gemini if selected or as fallback
            if model_choice == "gemini" or not answer:
                try:
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    full_prompt = f"{system_prompt}\n\n{user_prompt}"
                    response = model.generate_content(full_prompt)
                    answer = response.text
                    logger.info(f"Gemini response generated for: {question[:30]}")
                
                except Exception as gemini_error:
                    logger.error(f"Gemini error: {str(gemini_error)}")
                    answer = "Sorry, I'm having trouble generating a response right now. Please try again later."
            
            # Save to chat history
            ChatHistory.objects.create(
                student=request.user,
                question=question,
                answer=answer
            )
            
            return JsonResponse({
                "status": "success",
                "answer": answer,
                "model_used": model_choice,
                "context_found": bool(rag_context and "No specific NCERT content" not in rag_context)
            })
        
        except Exception as e:
            logger.error(f"Error in ask_chatbot: {str(e)}", exc_info=True)
            return JsonResponse({
                "status": "error",
                "error": "An error occurred while processing your question"
            }, status=500)
    
    return JsonResponse({"error": "Invalid request method"}, status=405)


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
