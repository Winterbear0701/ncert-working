"""
Celery tasks for processing uploaded PDF documents
Handles extraction, chunking, and ChromaDB ingestion
"""
from celery import shared_task
from .models import UploadedBook
from django.conf import settings
import pdfplumber
import os
import logging
from datetime import datetime
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import openai

logger = logging.getLogger('superadmin')

# Initialize OpenAI
openai.api_key = settings.OPENAI_API_KEY

# Initialize ChromaDB with persistent storage
chroma_client = chromadb.Client(ChromaSettings(
    persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
    anonymized_telemetry=False
))

# Use sentence transformers for embeddings (faster and free)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embeddings(texts):
    """Generate embeddings using sentence transformers"""
    return embedding_model.encode(texts).tolist()

# Get or create collection
collection = chroma_client.get_or_create_collection(
    name=settings.CHROMA_COLLECTION_NAME,
    metadata={"description": "NCERT textbook content for RAG"}
)

def extract_text_from_pdf(pdf_path):
    """
    Extract text from PDF using pdfplumber
    Returns list of (page_num, text) tuples
    """
    pages_data = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                
                # Clean up the text
                text = text.strip()
                
                if text:  # Only add pages with content
                    pages_data.append((i, text))
                    logger.info(f"Extracted page {i}: {len(text)} characters")
                else:
                    logger.warning(f"Page {i} has no extractable text")
                    
    except Exception as e:
        logger.error(f"Error extracting PDF: {str(e)}")
        raise
        
    return pages_data


def chunk_text_with_metadata(pages_data, book_obj):
    """
    Chunk pages into smaller pieces with metadata
    Returns list of dicts with text and metadata
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = []
    
    for page_num, page_text in pages_data:
        # Split page into chunks
        text_chunks = splitter.split_text(page_text)
        
        for chunk_idx, chunk_text in enumerate(text_chunks):
            metadata = {
                "standard": str(book_obj.standard),
                "subject": str(book_obj.subject),
                "chapter": str(book_obj.chapter),
                "page": page_num,
                "chunk_index": chunk_idx,
                "source_file": book_obj.original_filename,
                "upload_id": str(book_obj.id),
                "uploaded_at": book_obj.uploaded_at.isoformat(),
                "char_count": len(chunk_text),
            }
            
            chunks.append({
                "id": f"upload_{book_obj.id}_page_{page_num}_chunk_{chunk_idx}",
                "text": chunk_text,
                "metadata": metadata
            })
    
    logger.info(f"Created {len(chunks)} chunks from {len(pages_data)} pages")
    return chunks

@shared_task(bind=True, max_retries=3)
def process_uploaded_book(self, uploaded_book_id):
    """
    Process uploaded PDF: extract, chunk, and store in ChromaDB
    """
    logger.info(f"Processing upload ID: {uploaded_book_id}")
    
    try:
        # Get the uploaded book object
        book_obj = UploadedBook.objects.get(id=uploaded_book_id)
        book_obj.status = 'processing'
        book_obj.save()
        
        # Extract text from PDF
        logger.info(f"Extracting text from: {book_obj.file.path}")
        pages_data = extract_text_from_pdf(book_obj.file.path)
        
        if not pages_data:
            raise ValueError("No text could be extracted from PDF")
        
        # Chunk the text with metadata
        chunks = chunk_text_with_metadata(pages_data, book_obj)
        
        if not chunks:
            raise ValueError("No chunks created from PDF")
        
        # Store in ChromaDB in batches
        batch_size = 100
        total_added = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            ids = [c["id"] for c in batch]
            documents = [c["text"] for c in batch]
            metadatas = [c["metadata"] for c in batch]
            
            # Generate embeddings
            embeddings = get_embeddings(documents)
            
            # Add to ChromaDB
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            total_added += len(batch)
            logger.info(f"Added batch {i//batch_size + 1}: {len(batch)} chunks")
            
            # Update progress
            progress = int((total_added / len(chunks)) * 100)
            self.update_state(
                state='PROGRESS',
                meta={'current': total_added, 'total': len(chunks), 'percent': progress}
            )
        
        # Mark as complete
        book_obj.status = 'done'
        book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages"
        book_obj.save()
        
        logger.info(f"Successfully processed upload {uploaded_book_id}: {total_added} chunks")
        
        return {
            "status": "success",
            "upload_id": uploaded_book_id,
            "pages_processed": len(pages_data),
            "chunks_created": total_added
        }
        
    except Exception as e:
        logger.error(f"Error processing upload {uploaded_book_id}: {str(e)}", exc_info=True)
        
        # Update status to failed
        try:
            book_obj = UploadedBook.objects.get(id=uploaded_book_id)
            book_obj.status = 'failed'
            book_obj.notes = f"Error: {str(e)}"
            book_obj.save()
        except:
            pass
        
        raise self.retry(exc=e, countdown=60)  # Retry after 1 minute
