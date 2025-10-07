"""
Script to setup and clean ChromaDB for NCERT content
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from django.conf import settings
import chromadb
from chromadb.config import Settings as ChromaSettings

def clean_chromadb():
    """Clean/reset ChromaDB by deleting old collection"""
    print("🧹 Cleaning ChromaDB...")
    
    try:
        client = chromadb.Client(ChromaSettings(
            persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
            anonymized_telemetry=False
        ))
        
        # Delete existing collection if it exists
        try:
            client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
            print(f"✅ Deleted existing collection: {settings.CHROMA_COLLECTION_NAME}")
        except:
            print(f"ℹ️  No existing collection found")
        
        # Create fresh collection
        collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={
                "description": "NCERT textbook content for RAG - Clean database",
                "created_at": str(datetime.now()),
                "standards": "5-10",
                "subjects": "All NCERT subjects"
            }
        )
        
        print(f"✅ Created fresh collection: {settings.CHROMA_COLLECTION_NAME}")
        print(f"📊 Collection count: {collection.count()}")
        
        return collection
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None

def verify_chromadb():
    """Verify ChromaDB is working"""
    print("\n🔍 Verifying ChromaDB...")
    
    try:
        client = chromadb.Client(ChromaSettings(
            persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
            anonymized_telemetry=False
        ))
        
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        count = collection.count()
        print(f"✅ Collection '{settings.CHROMA_COLLECTION_NAME}' has {count} documents")
        
        if count > 0:
            # Get sample documents
            sample = collection.peek(limit=3)
            print(f"\n📝 Sample documents:")
            for i, doc in enumerate(sample['documents'], 1):
                meta = sample['metadatas'][i-1]
                print(f"\n{i}. {doc[:100]}...")
                print(f"   Standard: {meta.get('standard')}, Subject: {meta.get('subject')}, Chapter: {meta.get('chapter')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    from datetime import datetime
    
    print("=" * 70)
    print("🚀 ChromaDB Setup & Cleanup Script")
    print("=" * 70)
    
    # Ask user
    response = input("\n⚠️  This will DELETE all existing data. Continue? (yes/no): ")
    
    if response.lower() == 'yes':
        collection = clean_chromadb()
        if collection:
            verify_chromadb()
            print("\n✅ ChromaDB is ready for fresh uploads!")
    else:
        print("❌ Cancelled")
        verify_chromadb()
