"""
Test script to verify the database pipeline for PDF upload and processing
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from django.conf import settings
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

print("=" * 60)
print("TESTING DATABASE PIPELINE")
print("=" * 60)

# Test 1: Check Settings
print("\n1. Checking Django Settings...")
print(f"   ✓ BASE_DIR: {settings.BASE_DIR}")
print(f"   ✓ MEDIA_ROOT: {settings.MEDIA_ROOT}")
print(f"   ✓ MEDIA_URL: {settings.MEDIA_URL}")
print(f"   ✓ CHROMA_PERSIST_DIRECTORY: {settings.CHROMA_PERSIST_DIRECTORY}")
print(f"   ✓ CHROMA_COLLECTION_NAME: {settings.CHROMA_COLLECTION_NAME}")

# Test 2: Check Directories
print("\n2. Checking Directories...")
media_exists = os.path.exists(settings.MEDIA_ROOT)
chroma_exists = os.path.exists(settings.CHROMA_PERSIST_DIRECTORY)
print(f"   {'✓' if media_exists else '✗'} MEDIA_ROOT exists: {media_exists}")
print(f"   {'✓' if chroma_exists else '✗'} CHROMA directory exists: {chroma_exists}")

# Test 3: Test ChromaDB Connection
print("\n3. Testing ChromaDB Connection...")
try:
    chroma_client = chromadb.Client(ChromaSettings(
        persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
        anonymized_telemetry=False
    ))
    print(f"   ✓ ChromaDB client initialized")
    
    # Get or create collection
    collection = chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"description": "NCERT textbook content for RAG"}
    )
    print(f"   ✓ Collection '{settings.CHROMA_COLLECTION_NAME}' ready")
    
    # Check existing data
    count = collection.count()
    print(f"   ✓ Existing chunks in ChromaDB: {count}")
    
except Exception as e:
    print(f"   ✗ ChromaDB Error: {str(e)}")

# Test 4: Test Embedding Model
print("\n4. Testing Embedding Model...")
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print(f"   ✓ SentenceTransformer model loaded")
    
    # Test embedding
    test_text = "This is a test sentence."
    embedding = embedding_model.encode([test_text]).tolist()
    print(f"   ✓ Test embedding generated: {len(embedding[0])} dimensions")
    
except Exception as e:
    print(f"   ✗ Embedding Error: {str(e)}")

# Test 5: Check UploadedBook Model
print("\n5. Checking Database Models...")
try:
    from superadmin.models import UploadedBook
    count = UploadedBook.objects.count()
    print(f"   ✓ UploadedBook model accessible")
    print(f"   ✓ Total uploads in database: {count}")
    
    if count > 0:
        recent = UploadedBook.objects.latest('uploaded_at')
        print(f"   ✓ Latest upload: {recent.original_filename}")
        print(f"   ✓ Status: {recent.status}")
        
except Exception as e:
    print(f"   ✗ Model Error: {str(e)}")

# Test 6: Test PDF Processing Functions
print("\n6. Testing PDF Processing Functions...")
try:
    from superadmin.tasks import extract_text_from_pdf, chunk_text_with_metadata, get_embeddings
    print(f"   ✓ extract_text_from_pdf imported")
    print(f"   ✓ chunk_text_with_metadata imported")
    print(f"   ✓ get_embeddings imported")
    
    # Test embeddings function
    test_texts = ["Hello world", "Test text"]
    embeddings = get_embeddings(test_texts)
    print(f"   ✓ get_embeddings working: {len(embeddings)} embeddings")
    
except Exception as e:
    print(f"   ✗ Processing Functions Error: {str(e)}")

# Test 7: Check Required Packages
print("\n7. Checking Required Packages...")
try:
    import pdfplumber
    print(f"   ✓ pdfplumber installed")
except:
    print(f"   ✗ pdfplumber NOT installed")

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    print(f"   ✓ langchain installed")
except:
    print(f"   ✗ langchain NOT installed")

try:
    import chromadb
    print(f"   ✓ chromadb installed (version: {chromadb.__version__})")
except:
    print(f"   ✗ chromadb NOT installed")

try:
    import sentence_transformers
    print(f"   ✓ sentence_transformers installed")
except:
    print(f"   ✗ sentence_transformers NOT installed")

# Final Summary
print("\n" + "=" * 60)
print("PIPELINE STATUS")
print("=" * 60)
print("""
✅ If all tests passed above, the pipeline is ready!

To upload a PDF:
1. Go to: http://localhost:8000/superadmin/upload/
2. Select a PDF file
3. Fill in: Standard, Subject, Chapter
4. Click Upload

The PDF will be:
1. Saved to media/uploads/books/
2. Text extracted using pdfplumber
3. Chunked into 1000-char pieces with 200-char overlap
4. Embedded using sentence-transformers
5. Stored in ChromaDB with metadata

The chatbot will then be able to retrieve this content!
""")
