"""
Celery tasks for processing uploaded PDF documents
Handles extraction, chunking, and vector database ingestion with proper labeling
Format: Class X, Subject: Y, Chapter: Z
Includes OCR for extracting text from images (like definitions in diagrams)
"""
from celery import shared_task
from .models import UploadedBook
from django.conf import settings
import pdfplumber
import os
import logging
from datetime import datetime
from langchain.text_splitter import RecursiveCharacterTextSplitter
import openai
import pytesseract
from PIL import Image
import io

# Import unified vector database manager (Pinecone/ChromaDB)
from ncert_project.vector_db_utils import get_vector_db_manager

logger = logging.getLogger('superadmin')

# Initialize OpenAI
openai.api_key = settings.OPENAI_API_KEY

# Get vector database manager instance (auto-switches based on VECTOR_DB env)
vector_db_manager = get_vector_db_manager()

def is_math_heavy_subject(subject):
    """Check if subject needs special OCR for equations"""
    math_subjects = ['mathematics', 'math', 'physics', 'chemistry', 'science']
    return any(subj in subject.lower() for subj in math_subjects)


def extract_text_from_images_ocr(page):
    """
    Extract text from images on a PDF page using OCR
    This captures definitions and terms that appear in images/diagrams
    Returns: extracted image text
    """
    image_text = []
    try:
        # Get images from the page
        images = page.images
        if images:
            for img in images:
                try:
                    # Get image object
                    image_obj = page.within_bbox((img['x0'], img['top'], img['x1'], img['bottom']))
                    # Convert to PIL Image
                    im = image_obj.to_image(resolution=300)
                    pil_img = im.original
                    
                    # Perform OCR
                    ocr_text = pytesseract.image_to_string(pil_img, lang='eng')
                    if ocr_text.strip():
                        image_text.append(ocr_text.strip())
                        logger.info(f"   📸 Extracted text from image: {ocr_text[:100]}...")
                except Exception as img_error:
                    logger.debug(f"   Could not OCR image: {str(img_error)}")
                    continue
    except Exception as e:
        logger.debug(f"   OCR extraction error: {str(e)}")
    
    return "\n\n[IMAGE TEXT]\n" + "\n".join(image_text) + "\n[/IMAGE TEXT]\n" if image_text else ""


def extract_text_from_pdf(pdf_path, subject=""):
    """
    Extract text from PDF with enhanced handling for math/science content
    AND extract text from images using OCR (for terms like 'dune', 'plateau' etc)
    Returns list of (page_num, text, has_equations) tuples
    """
    pages_data = []
    use_enhanced_extraction = is_math_heavy_subject(subject)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Processing {total_pages} pages from PDF (Enhanced: {use_enhanced_extraction})")
            
            for i, page in enumerate(pdf.pages, start=1):
                # Extract regular text
                text = page.extract_text() or ""
                
                # Extract text from images (IMPORTANT: for definitions in diagrams)
                image_text = extract_text_from_images_ocr(page)
                if image_text:
                    text += "\n\n" + image_text
                
                # Clean up the text
                text = text.strip()
                
                # Detect if page has mathematical symbols
                math_symbols = ['=', '+', '-', '×', '÷', '∫', '∑', '√', '∞', '≤', '≥', 'π']
                has_equations = any(symbol in text for symbol in math_symbols)
                
                if text:
                    # Additional cleaning for better chunking
                    # Remove excessive whitespace
                    text = ' '.join(text.split())
                    
                    # Preserve line breaks for better structure
                    text = text.replace('. ', '.\n')
                    
                    pages_data.append((i, text, has_equations))
                    
                    symbol_count = sum(text.count(s) for s in math_symbols)
                    logger.info(f"Extracted page {i}/{total_pages}: {len(text)} chars, "
                               f"math symbols: {symbol_count}")
                else:
                    logger.warning(f"Page {i}/{total_pages} has no extractable text")
                    
    except Exception as e:
        logger.error(f"Error extracting PDF: {str(e)}")
        raise
    
    logger.info(f"✅ Extracted {len(pages_data)} pages with content")
    return pages_data


def chunk_text_with_metadata(pages_data, book_obj):
    """
    Enhanced chunking with better handling for equations and structured content
    Returns list of dicts with text and metadata ready for ChromaDB
    """
    # Adjust chunk size based on subject
    is_math_heavy = is_math_heavy_subject(book_obj.subject)
    
    if is_math_heavy:
        # Smaller chunks for math/science to keep equations intact
        chunk_size = 800
        chunk_overlap = 150
    else:
        # Larger chunks for text-heavy subjects
        chunk_size = 1200
        chunk_overlap = 200
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = []
    total_equations = 0
    
    for page_num, page_text, has_equations in pages_data:
        # Split page into chunks
        text_chunks = splitter.split_text(page_text)
        
        for chunk_idx, chunk_text in enumerate(text_chunks):
            # Count math symbols in chunk
            math_symbols = ['=', '+', '-', '×', '÷', '∫', '∑', '√', '∞', '≤', '≥']
            equation_count = sum(chunk_text.count(s) for s in math_symbols)
            
            if equation_count > 0:
                total_equations += 1
            
            # Create chunk with metadata in the format expected by ChromaDB manager
            chunks.append({
                "text": chunk_text,
                "page": page_num,
                "chunk_index": chunk_idx,
                "chapter_num": book_obj.chapter,
                "has_equations": has_equations,
                "equation_count": equation_count,
                "content_type": "math_heavy" if is_math_heavy else "text_heavy",
                "uploaded_at": book_obj.uploaded_at.isoformat(),
                "upload_id": str(book_obj.id)
            })
    
    logger.info(f"✅ Created {len(chunks)} chunks from {len(pages_data)} pages "
               f"({total_equations} chunks with equations)")
    return chunks

def process_uploaded_book_sync(uploaded_book_id):
    """
    Synchronous version: Process uploaded PDF immediately without Celery
    Enhanced with subject-aware extraction and ChromaDB with proper labeling
    Storage format: Class X, Subject: Y, Chapter: Z
    AUTOMATICALLY GENERATES MCQs after successful upload
    """
    logger.info(f"Processing upload ID: {uploaded_book_id} (SYNC)")
    
    try:
        # Get the uploaded book object
        book_obj = UploadedBook.objects.get(id=uploaded_book_id)
        book_obj.status = 'processing'
        book_obj.save()
        
        # Extract text from PDF with subject-aware processing
        logger.info(f"Extracting text from: {book_obj.file.path}")
        logger.info(f"📚 Class: {book_obj.standard}, Subject: {book_obj.subject}, Chapter: {book_obj.chapter}")
        pages_data = extract_text_from_pdf(book_obj.file.path, subject=book_obj.subject)
        
        if not pages_data:
            raise ValueError("No text could be extracted from PDF")
        
        # Chunk the text with metadata
        chunks = chunk_text_with_metadata(pages_data, book_obj)
        
        if not chunks:
            raise ValueError("No chunks created from PDF")
        
        # Store in vector database (Pinecone/ChromaDB based on VECTOR_DB env)
        db_type = "Pinecone" if hasattr(vector_db_manager, 'index_name') else "ChromaDB"
        logger.info(f"📝 Storing {len(chunks)} chunks in {db_type} with labels:")
        logger.info(f"   Class: {book_obj.standard}")
        logger.info(f"   Subject: {book_obj.subject}")
        logger.info(f"   Chapter: {book_obj.chapter}")
        
        total_added = vector_db_manager.add_document_chunks(
            chunks=chunks,
            standard=book_obj.standard,
            subject=book_obj.subject,
            chapter=book_obj.chapter,
            source_file=book_obj.original_filename,
            batch_size=100
        )
        
        # ==================== SAVE CHAPTER METADATA TO MONGODB ====================
        # Save chapter info to MongoDB for unit test chapter selection
        logger.info(f"💾 Saving chapter metadata to MongoDB...")
        try:
            from ncert_project.mongodb_utils import get_mongo_db
            db = get_mongo_db()
            
            # Normalize class format
            class_number_normalized = f"Class {book_obj.standard}" if not str(book_obj.standard).lower().startswith('class') else str(book_obj.standard)
            
            # Extract chapter number from chapter name
            chapter_num = book_obj.chapter.replace('Chapter', '').replace('chapter', '').strip()
            if ':' in chapter_num:
                chapter_num = chapter_num.split(':')[0].strip()
            
            # Create chapter_id in format: class_X_subject_chapter_Y
            chapter_id = f"class_{book_obj.standard}_{book_obj.subject.lower().replace(' ', '_')}_chapter_{chapter_num}"
            
            # Save to book_chapters collection (separate from quiz_chapters)
            db.book_chapters.update_one(
                {'chapter_id': chapter_id},
                {'$set': {
                    'chapter_id': chapter_id,
                    'class_number': class_number_normalized,
                    'subject': book_obj.subject,
                    'chapter_number': chapter_num,
                    'chapter_name': book_obj.chapter,
                    'source_file': book_obj.original_filename,
                    'uploaded_at': datetime.utcnow(),
                    'total_chunks': total_added
                }},
                upsert=True
            )
            
            logger.info(f"✅ Chapter metadata saved: {class_number_normalized} - {book_obj.subject} - {book_obj.chapter}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save chapter metadata to MongoDB: {e}")
            # Don't fail the entire upload if metadata save fails
        
        # ==================== AUTO-GENERATE MCQs ====================
        logger.info(f"🎯 Auto-generating MCQs for uploaded chapter...")
        
        # IMPORTANT: Pinecone has indexing latency - wait and verify vectors are queryable
        if hasattr(vector_db_manager, 'index_name'):
            import time
            logger.info("⏳ Waiting for Pinecone indexing to complete...")
            
            # Wait with verification - check if vectors are queryable
            max_wait_time = 30  # Maximum 30 seconds
            wait_interval = 3   # Check every 3 seconds
            elapsed_time = 0
            vectors_ready = False
            
            while elapsed_time < max_wait_time:
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                
                # Quick test query to see if vectors are indexed
                try:
                    test_results = vector_db_manager.query_by_class_subject_chapter(
                        query_text=f"{book_obj.subject} {book_obj.chapter}",
                        class_num=str(book_obj.standard),
                        subject=book_obj.subject,
                        chapter=book_obj.chapter,
                        n_results=1
                    )
                    if test_results and test_results.get('documents') and len(test_results['documents'][0]) > 0:
                        vectors_ready = True
                        logger.info(f"✅ Pinecone indexing complete after {elapsed_time}s - {len(test_results['documents'][0])} vectors ready")
                        break
                    else:
                        logger.info(f"⏳ Indexing in progress... ({elapsed_time}s elapsed)")
                except Exception as e:
                    logger.warning(f"⚠️  Test query failed: {e}")
            
            if not vectors_ready:
                logger.warning(f"⚠️  Pinecone indexing may not be complete after {elapsed_time}s - proceeding anyway")
        
        try:
            from students.improved_quiz_generator import generate_quiz_with_textbook_questions
            
            # Create chapter_id in format: class_X_subject_chapter_Y
            chapter_num = book_obj.chapter.replace('Chapter', '').replace('chapter', '').strip()
            chapter_id = f"class_{book_obj.standard}_{book_obj.subject.lower().replace(' ', '_')}_chapter_{chapter_num}"
            
            # Normalize class format for querying
            class_number_normalized = f"Class {book_obj.standard}" if not str(book_obj.standard).lower().startswith('class') else str(book_obj.standard)
            
            # Get chapter order based on SAME class AND subject
            from students.models import QuizChapter
            existing_chapters = QuizChapter.objects.filter(
                class_number=class_number_normalized,  # Use normalized format
                subject=book_obj.subject
            ).count()
            chapter_order = existing_chapters + 1
            
            logger.info(f"📊 Chapter order calculation: {existing_chapters} existing chapters for {class_number_normalized}/{book_obj.subject}, new chapter_order={chapter_order}")
            
            # Generate quiz
            quiz_result = generate_quiz_with_textbook_questions(
                chapter_id=chapter_id,
                class_num=book_obj.standard,
                subject=book_obj.subject,
                chapter_name=book_obj.chapter,
                chapter_order=chapter_order
            )
            
            if quiz_result.get('status') == 'success':
                logger.info(f"✅ Successfully auto-generated {quiz_result.get('questions_generated', 0)} MCQs!")
                book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Auto-generated {quiz_result.get('questions_generated', 0)} MCQs."
            else:
                logger.warning(f"⚠️ Quiz generation completed with warnings: {quiz_result.get('message', 'Unknown')}")
                book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Quiz generation: {quiz_result.get('message', 'Partial success')}"
                
        except Exception as quiz_error:
            logger.error(f"❌ Error generating MCQs (upload still successful): {str(quiz_error)}")
            book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Note: MCQ auto-generation failed - run 'python manage.py generate_quizzes' manually."
        
        # Mark as complete
        book_obj.status = 'done'
        book_obj.save()
        
        logger.info(f"✅ Successfully processed upload {uploaded_book_id}: {total_added} chunks")
        
        # Log vector database stats
        try:
            if hasattr(vector_db_manager, 'get_stats'):
                stats = vector_db_manager.get_stats()
                logger.info(f"📊 Vector DB Stats: {stats.get('total_documents', 0)} total documents, "
                           f"{stats.get('total_classes', 0)} classes")
            else:
                # Pinecone stats
                index_stats = vector_db_manager.index.describe_index_stats()
                logger.info(f"📊 Pinecone Stats: {index_stats.get('total_vector_count', 0)} total vectors")
        except Exception as e:
            logger.warning(f"⚠️  Could not get vector DB stats: {e}")
        
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
        
        raise


@shared_task(bind=True, max_retries=3)
def process_uploaded_book(self, uploaded_book_id):
    """
    Celery async version: Process uploaded PDF in background
    Enhanced with subject-aware extraction and ChromaDB with proper labeling
    Storage format: Class X, Subject: Y, Chapter: Z
    AUTOMATICALLY GENERATES MCQs after successful upload
    (Use this when Celery is running, otherwise use process_uploaded_book_sync)
    """
    logger.info(f"Processing upload ID: {uploaded_book_id} (ASYNC)")
    
    try:
        # Get the uploaded book object
        book_obj = UploadedBook.objects.get(id=uploaded_book_id)
        book_obj.status = 'processing'
        book_obj.save()
        
        # Extract text from PDF with subject-aware processing
        logger.info(f"Extracting text from: {book_obj.file.path}")
        logger.info(f"📚 Class: {book_obj.standard}, Subject: {book_obj.subject}, Chapter: {book_obj.chapter}")
        pages_data = extract_text_from_pdf(book_obj.file.path, subject=book_obj.subject)
        
        if not pages_data:
            raise ValueError("No text could be extracted from PDF")
        
        # Chunk the text with metadata
        chunks = chunk_text_with_metadata(pages_data, book_obj)
        
        if not chunks:
            raise ValueError("No chunks created from PDF")
        
        # Store in vector database (Pinecone/ChromaDB based on VECTOR_DB env)
        db_type = "Pinecone" if hasattr(vector_db_manager, 'index_name') else "ChromaDB"
        logger.info(f"📝 Storing {len(chunks)} chunks in {db_type} with labels:")
        logger.info(f"   Class: {book_obj.standard}")
        logger.info(f"   Subject: {book_obj.subject}")
        logger.info(f"   Chapter: {book_obj.chapter}")
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': len(chunks), 'percent': 0, 'status': f'Storing in {db_type}'}
        )
        
        total_added = vector_db_manager.add_document_chunks(
            chunks=chunks,
            standard=book_obj.standard,
            subject=book_obj.subject,
            chapter=book_obj.chapter,
            source_file=book_obj.original_filename,
            batch_size=100
        )
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': total_added, 'total': len(chunks), 'percent': 75, 'status': 'Saving chapter metadata'}
        )
        
        # ==================== SAVE CHAPTER METADATA TO MONGODB ====================
        # Save chapter info to MongoDB for unit test chapter selection
        logger.info(f"💾 Saving chapter metadata to MongoDB...")
        try:
            from ncert_project.mongodb_utils import get_mongo_db
            db = get_mongo_db()
            
            # Normalize class format
            class_number_normalized = f"Class {book_obj.standard}" if not str(book_obj.standard).lower().startswith('class') else str(book_obj.standard)
            
            # Extract chapter number from chapter name
            chapter_num = book_obj.chapter.replace('Chapter', '').replace('chapter', '').strip()
            if ':' in chapter_num:
                chapter_num = chapter_num.split(':')[0].strip()
            
            # Create chapter_id in format: class_X_subject_chapter_Y
            chapter_id = f"class_{book_obj.standard}_{book_obj.subject.lower().replace(' ', '_')}_chapter_{chapter_num}"
            
            # Save to book_chapters collection (separate from quiz_chapters)
            db.book_chapters.update_one(
                {'chapter_id': chapter_id},
                {'$set': {
                    'chapter_id': chapter_id,
                    'class_number': class_number_normalized,
                    'subject': book_obj.subject,
                    'chapter_number': chapter_num,
                    'chapter_name': book_obj.chapter,
                    'source_file': book_obj.original_filename,
                    'uploaded_at': datetime.utcnow(),
                    'total_chunks': total_added
                }},
                upsert=True
            )
            
            logger.info(f"✅ Chapter metadata saved: {class_number_normalized} - {book_obj.subject} - {book_obj.chapter}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save chapter metadata to MongoDB: {e}")
            # Don't fail the entire upload if metadata save fails
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': total_added, 'total': len(chunks), 'percent': 80, 'status': 'Indexing vectors'}
        )
        
        # IMPORTANT: Pinecone has indexing latency - wait and verify vectors are queryable
        if hasattr(vector_db_manager, 'index_name'):
            import time
            logger.info("⏳ Waiting for Pinecone indexing to complete...")
            
            # Wait with verification - check if vectors are queryable
            max_wait_time = 30  # Maximum 30 seconds
            wait_interval = 3   # Check every 3 seconds
            elapsed_time = 0
            vectors_ready = False
            
            while elapsed_time < max_wait_time:
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                
                # Quick test query to see if vectors are indexed
                try:
                    test_results = vector_db_manager.query_by_class_subject_chapter(
                        query_text=f"{book_obj.subject} {book_obj.chapter}",
                        class_num=str(book_obj.standard),
                        subject=book_obj.subject,
                        chapter=book_obj.chapter,
                        n_results=1
                    )
                    if test_results and test_results.get('documents') and len(test_results['documents'][0]) > 0:
                        vectors_ready = True
                        logger.info(f"✅ Pinecone indexing complete after {elapsed_time}s - {len(test_results['documents'][0])} vectors ready")
                        break
                    else:
                        logger.info(f"⏳ Indexing in progress... ({elapsed_time}s elapsed)")
                        # Update progress
                        self.update_state(
                            state='PROGRESS',
                            meta={'current': total_added, 'total': len(chunks), 'percent': 80 + (elapsed_time * 5 // max_wait_time), 'status': f'Waiting for indexing ({elapsed_time}s)'}
                        )
                except Exception as e:
                    logger.warning(f"⚠️  Test query failed: {e}")
            
            if not vectors_ready:
                logger.warning(f"⚠️  Pinecone indexing may not be complete after {elapsed_time}s - proceeding anyway")
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': total_added, 'total': len(chunks), 'percent': 85, 'status': 'Generating MCQs'}
        )
        
        # ==================== AUTO-GENERATE MCQs ====================
        logger.info(f"🎯 Auto-generating MCQs for uploaded chapter...")
        try:
            from students.improved_quiz_generator import generate_quiz_with_textbook_questions
            
            # Create chapter_id in format: class_X_subject_chapter_Y
            chapter_num = book_obj.chapter.replace('Chapter', '').replace('chapter', '').strip()
            chapter_id = f"class_{book_obj.standard}_{book_obj.subject.lower().replace(' ', '_')}_chapter_{chapter_num}"
            
            # Normalize class format for querying
            class_number_normalized = f"Class {book_obj.standard}" if not str(book_obj.standard).lower().startswith('class') else str(book_obj.standard)
            
            # Get chapter order based on SAME class AND subject
            from students.models import QuizChapter
            existing_chapters = QuizChapter.objects.filter(
                class_number=class_number_normalized,  # Use normalized format
                subject=book_obj.subject
            ).count()
            chapter_order = existing_chapters + 1
            
            logger.info(f"📊 Chapter order calculation: {existing_chapters} existing chapters for {class_number_normalized}/{book_obj.subject}, new chapter_order={chapter_order}")
            
            # Generate quiz
            quiz_result = generate_quiz_with_textbook_questions(
                chapter_id=chapter_id,
                class_num=book_obj.standard,
                subject=book_obj.subject,
                chapter_name=book_obj.chapter,
                chapter_order=chapter_order
            )
            
            if quiz_result.get('status') == 'success':
                logger.info(f"✅ Successfully auto-generated {quiz_result.get('questions_generated', 0)} MCQs!")
                book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Auto-generated {quiz_result.get('questions_generated', 0)} MCQs."
            else:
                logger.warning(f"⚠️ Quiz generation completed with warnings: {quiz_result.get('message', 'Unknown')}")
                book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Quiz generation: {quiz_result.get('message', 'Partial success')}"
                
        except Exception as quiz_error:
            logger.error(f"❌ Error generating MCQs (upload still successful): {str(quiz_error)}")
            book_obj.notes = f"Successfully processed {total_added} chunks from {len(pages_data)} pages. Note: MCQ auto-generation failed - run 'python manage.py generate_quizzes' manually."
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': total_added, 'total': len(chunks), 'percent': 100}
        )
        
        # Mark as complete
        book_obj.status = 'done'
        book_obj.save()
        
        logger.info(f"✅ Successfully processed upload {uploaded_book_id}: {total_added} chunks")
        
        # Log vector database stats
        try:
            if hasattr(vector_db_manager, 'get_stats'):
                stats = vector_db_manager.get_stats()
                logger.info(f"📊 Vector DB Stats: {stats.get('total_documents', 0)} total documents, "
                           f"{stats.get('total_classes', 0)} classes")
            else:
                # Pinecone stats
                index_stats = vector_db_manager.index.describe_index_stats()
                logger.info(f"📊 Pinecone Stats: {index_stats.get('total_vector_count', 0)} total vectors")
        except Exception as e:
            logger.warning(f"⚠️  Could not get vector DB stats: {e}")
        
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
