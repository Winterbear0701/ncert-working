"""
ChromaDB Management & Inspection Tool
View, search, and manage NCERT content in ChromaDB
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

def get_client():
    """Get ChromaDB client"""
    return chromadb.Client(ChromaSettings(
        persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
        anonymized_telemetry=False
    ))

def view_stats():
    """View database statistics"""
    print("\n" + "="*70)
    print("📊 ChromaDB Statistics")
    print("="*70)
    
    try:
        client = get_client()
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        total_count = collection.count()
        print(f"\n✅ Total documents: {total_count}")
        
        if total_count > 0:
            # Get all documents to analyze
            all_docs = collection.get()
            metadatas = all_docs['metadatas']
            
            # Group by standard
            standards = {}
            subjects = {}
            chapters = {}
            
            for meta in metadatas:
                std = meta.get('standard', 'Unknown')
                subj = meta.get('subject', 'Unknown')
                chap = meta.get('chapter', 'Unknown')
                
                standards[std] = standards.get(std, 0) + 1
                subjects[subj] = subjects.get(subj, 0) + 1
                chapters[f"{std}-{subj}-{chap}"] = chapters.get(f"{std}-{subj}-{chap}", 0) + 1
            
            print(f"\n📚 By Standard:")
            for std, count in sorted(standards.items()):
                print(f"   Standard {std}: {count} chunks")
            
            print(f"\n📖 By Subject:")
            for subj, count in sorted(subjects.items()):
                print(f"   {subj}: {count} chunks")
            
            print(f"\n📑 By Chapter:")
            for chap, count in sorted(chapters.items()):
                print(f"   {chap}: {count} chunks")
                
        else:
            print("\n⚠️  Database is empty. Upload some PDFs first!")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

def view_sample(limit=5):
    """View sample documents"""
    print("\n" + "="*70)
    print(f"📝 Sample Documents (Showing {limit})")
    print("="*70)
    
    try:
        client = get_client()
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        sample = collection.peek(limit=limit)
        
        for i, (doc, meta) in enumerate(zip(sample['documents'], sample['metadatas']), 1):
            print(f"\n{i}. ID: {sample['ids'][i-1]}")
            print(f"   Standard: {meta.get('standard')}, Subject: {meta.get('subject')}")
            print(f"   Chapter: {meta.get('chapter')}, Page: {meta.get('page')}")
            print(f"   Has Equations: {meta.get('has_equations', False)}")
            print(f"   Content Type: {meta.get('content_type', 'N/A')}")
            print(f"   Text: {doc[:150]}...")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

def search_content(query, standard=None, subject=None, limit=3):
    """Search for content"""
    print("\n" + "="*70)
    print(f"🔍 Searching: '{query}'")
    print("="*70)
    
    try:
        client = get_client()
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        # Build filter
        where_filter = {}
        if standard:
            where_filter['standard'] = str(standard)
        if subject:
            where_filter['subject'] = subject
        
        # Search
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        query_embedding = model.encode(query).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_filter if where_filter else None
        )
        
        if results['documents'] and results['documents'][0]:
            print(f"\n✅ Found {len(results['documents'][0])} results:\n")
            
            for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0]), 1):
                print(f"{i}. Standard {meta.get('standard')}, {meta.get('subject')}, {meta.get('chapter')}")
                print(f"   Page: {meta.get('page')}, Has Equations: {meta.get('has_equations', False)}")
                print(f"   {doc[:200]}...\n")
        else:
            print("\n⚠️  No results found")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

def delete_by_upload_id(upload_id):
    """Delete all chunks from a specific upload"""
    print(f"\n🗑️  Deleting all chunks from upload ID: {upload_id}")
    
    try:
        client = get_client()
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        
        # Get all documents with this upload_id
        results = collection.get(where={"upload_id": str(upload_id)})
        
        if results['ids']:
            collection.delete(ids=results['ids'])
            print(f"✅ Deleted {len(results['ids'])} chunks from upload {upload_id}")
        else:
            print(f"⚠️  No chunks found for upload {upload_id}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def main_menu():
    """Interactive menu"""
    while True:
        print("\n" + "="*70)
        print("🗄️  ChromaDB Management Tool")
        print("="*70)
        print("\n1. View Statistics")
        print("2. View Sample Documents")
        print("3. Search Content")
        print("4. Delete by Upload ID")
        print("5. Clean Database (Delete All)")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ")
        
        if choice == '1':
            view_stats()
        elif choice == '2':
            limit = input("How many samples? (default 5): ")
            view_sample(int(limit) if limit else 5)
        elif choice == '3':
            query = input("Enter search query: ")
            standard = input("Filter by standard (leave empty for all): ")
            subject = input("Filter by subject (leave empty for all): ")
            search_content(query, standard if standard else None, subject if subject else None)
        elif choice == '4':
            upload_id = input("Enter upload ID to delete: ")
            confirm = input(f"⚠️  Delete all chunks from upload {upload_id}? (yes/no): ")
            if confirm.lower() == 'yes':
                delete_by_upload_id(upload_id)
        elif choice == '5':
            confirm = input("⚠️  This will DELETE ALL data! Continue? (yes/no): ")
            if confirm.lower() == 'yes':
                import setup_chromadb
                setup_chromadb.clean_chromadb()
        elif choice == '6':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main_menu()
