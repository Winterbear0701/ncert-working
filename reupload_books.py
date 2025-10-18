"""
Script to properly re-upload NCERT books with better chunking
This will:
1. Delete existing ChromaDB data
2. Re-process PDFs with improved chunking strategy
3. Extract chapter names, page numbers, and content properly
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

import chromadb
from chromadb.config import Settings
import PyPDF2
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def clear_chromadb():
    """Delete all existing ChromaDB data"""
    print("🗑️  Clearing existing ChromaDB data...")
    
    client = chromadb.PersistentClient(path='./chromadb_data')
    
    try:
        # Delete existing collection
        client.delete_collection(name='ncert_books')
        print("✅ Deleted old collection")
    except Exception as e:
        print(f"ℹ️  No existing collection to delete: {e}")
    
    # Create fresh collection
    collection = client.create_collection(
        name='ncert_books',
        metadata={"description": "NCERT textbook content with proper chapter mapping"}
    )
    print("✅ Created fresh collection")
    return collection


def extract_chapter_from_text(text: str, page_num: int) -> str:
    """Extract chapter number/name from page text"""
    import re
    
    # Common patterns for chapter headings
    patterns = [
        r'Chapter\s+(\d+)[:\s]*([^\n]+)',
        r'CHAPTER\s+(\d+)[:\s]*([^\n]+)',
        r'(\d+)\.\s*([A-Z][^\n]{10,50})',  # "1. Water Everywhere"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text[:500])  # Check first 500 chars
        if match:
            if len(match.groups()) == 2:
                return f"Chapter {match.group(1)}"
            else:
                return match.group(1)
    
    return f"Page {page_num}"


def chunk_text_intelligently(text: str, chunk_size: int = 1000) -> list:
    """
    Split text into chunks at natural boundaries (paragraphs, sentences)
    """
    chunks = []
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def process_pdf_properly(pdf_path: Path, class_num: str, subject: str, collection):
    """
    Process PDF with proper chapter detection and chunking
    """
    print(f"\n📖 Processing: {pdf_path.name}")
    print(f"   Class: {class_num}, Subject: {subject}")
    
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            print(f"   Total pages: {total_pages}")
            
            current_chapter = "Introduction"
            documents = []
            metadatas = []
            ids = []
            
            for page_num in range(total_pages):
                try:
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    
                    if not text or len(text.strip()) < 50:
                        continue
                    
                    # Try to detect chapter
                    detected_chapter = extract_chapter_from_text(text, page_num + 1)
                    if detected_chapter != f"Page {page_num + 1}":
                        current_chapter = detected_chapter
                        print(f"   📍 Found: {current_chapter} (Page {page_num + 1})")
                    
                    # Chunk the page content
                    chunks = chunk_text_intelligently(text, chunk_size=800)
                    
                    for chunk_idx, chunk in enumerate(chunks):
                        doc_id = f"class_{class_num}_subject_{subject.lower().replace(' ', '_')}_chapter_{current_chapter}_page_{page_num + 1}_chunk_{chunk_idx}"
                        
                        documents.append(chunk)
                        metadatas.append({
                            "class": class_num,
                            "subject": subject,
                            "chapter": current_chapter,
                            "page": page_num + 1,
                            "chunk": chunk_idx,
                            "source": pdf_path.name
                        })
                        ids.append(doc_id)
                
                except Exception as e:
                    print(f"   ⚠️  Error on page {page_num + 1}: {e}")
                    continue
            
            # Add to ChromaDB in batches
            if documents:
                batch_size = 100
                for i in range(0, len(documents), batch_size):
                    batch_docs = documents[i:i + batch_size]
                    batch_metas = metadatas[i:i + batch_size]
                    batch_ids = ids[i:i + batch_size]
                    
                    collection.add(
                        documents=batch_docs,
                        metadatas=batch_metas,
                        ids=batch_ids
                    )
                
                print(f"   ✅ Added {len(documents)} chunks to ChromaDB")
                return True
            else:
                print(f"   ❌ No content extracted")
                return False
                
    except Exception as e:
        print(f"   ❌ Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main upload script"""
    print("="*60)
    print("📚 NCERT Books Re-Upload Script")
    print("="*60)
    
    # Step 1: Clear old data
    collection = clear_chromadb()
    
    # Step 2: Find PDFs in media/uploads/books/
    books_dir = Path('./media/uploads/books/')
    
    if not books_dir.exists():
        print(f"\n❌ Books directory not found: {books_dir}")
        print("Please place your PDF files in: media/uploads/books/")
        return
    
    pdf_files = list(books_dir.glob('*.pdf'))
    
    if not pdf_files:
        print(f"\n❌ No PDF files found in {books_dir}")
        print("Please add NCERT PDFs to this directory")
        return
    
    print(f"\n📚 Found {len(pdf_files)} PDF files")
    
    # Step 3: Process each PDF
    success_count = 0
    
    for pdf_file in pdf_files:
        # Try to extract class and subject from filename
        # Expected format: "Class_5_Mathematics.pdf" or similar
        filename = pdf_file.stem
        
        # Ask user for metadata (or parse from filename)
        print(f"\n{'='*60}")
        print(f"File: {pdf_file.name}")
        
        # Try auto-detection
        import re
        match = re.search(r'[Cc]lass[\s_]*(\d+)', filename, re.IGNORECASE)
        auto_class = match.group(1) if match else ""
        
        class_num = input(f"Enter class number [{auto_class}]: ").strip() or auto_class
        
        # Subject detection
        subjects = {
            'math': 'Mathematics',
            'science': 'Science',
            'world': 'The World Around Us',
            'english': 'English',
            'hindi': 'Hindi',
            'social': 'Social Science'
        }
        
        auto_subject = ""
        for key, full_name in subjects.items():
            if key in filename.lower():
                auto_subject = full_name
                break
        
        subject = input(f"Enter subject [{auto_subject}]: ").strip() or auto_subject
        
        if not class_num or not subject:
            print("⚠️  Skipping (missing class or subject)")
            continue
        
        # Process
        if process_pdf_properly(pdf_file, class_num, subject, collection):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Successfully processed {success_count}/{len(pdf_files)} books")
    print(f"{'='*60}")
    
    # Step 4: Verify
    print("\n🔍 Verifying ChromaDB...")
    total_docs = collection.count()
    print(f"Total documents in ChromaDB: {total_docs}")
    
    if total_docs > 0:
        print("\n✅ Upload successful!")
        print("\nNext steps:")
        print("1. Run: python manage.py regenerate_quizzes --class=5")
        print("2. Test the quiz system")
    else:
        print("\n❌ No documents were added. Please check the PDFs.")


if __name__ == '__main__':
    main()
