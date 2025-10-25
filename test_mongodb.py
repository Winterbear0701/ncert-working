#!/usr/bin/env python
"""
Test MongoDB Atlas Connection
Run this to verify your MongoDB Atlas setup
"""
import os
import sys
from pathlib import Path

# Add project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
import django
django.setup()

from ncert_project.mongodb_utils import mongodb_manager
from ncert_project.chromadb_utils import get_chromadb_manager
from django.conf import settings

def test_mongodb():
    """Test MongoDB Atlas connection"""
    print("=" * 60)
    print("TESTING MONGODB ATLAS CONNECTION")
    print("=" * 60)
    
    # Check if password is set
    if '<db_password>' in settings.MONGODB_URI:
        print("❌ FAILED: MongoDB password not set in .env file")
        print("   Please edit .env and replace <db_password> with your actual password")
        print(f"   Current URI: {settings.MONGODB_URI[:50]}...")
        return False
    
    try:
        # Test connection
        print(f"📡 Connecting to MongoDB Atlas...")
        print(f"   Database: {settings.MONGODB_DB_NAME}")
        
        # Get database
        db = mongodb_manager.db
        
        # List collections
        collections = db.list_collection_names()
        print(f"✅ Connected successfully!")
        print(f"   Collections in database: {collections if collections else '(empty - this is OK for new setup)'}")
        
        # Test write operation
        test_collection = db['_connection_test']
        result = test_collection.insert_one({'test': True, 'message': 'Connection successful'})
        print(f"✅ Write test successful (ID: {result.inserted_id})")
        
        # Clean up test
        test_collection.delete_one({'_id': result.inserted_id})
        print(f"✅ Cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"❌ MongoDB connection FAILED: {e}")
        print("\n🔧 Troubleshooting:")
        print("   1. Check MongoDB Atlas dashboard - is cluster running?")
        print("   2. Network Access - is your IP allowed?")
        print("   3. Database User - password correct?")
        print("   4. Check .env file for typos")
        return False

def test_chromadb():
    """Test ChromaDB connection"""
    print("\n" + "=" * 60)
    print("TESTING CHROMADB (LOCAL VECTOR STORE)")
    print("=" * 60)
    
    try:
        chroma = get_chromadb_manager()
        doc_count = chroma.collection.count()
        stats = chroma.get_stats()
        
        print(f"✅ ChromaDB connected successfully!")
        print(f"   Total documents: {doc_count}")
        print(f"   Total classes: {stats.get('total_classes', 0)}")
        print(f"   Storage: {settings.CHROMA_PERSIST_DIRECTORY}")
        
        if doc_count == 0:
            print("   ⚠️  No documents yet - upload PDFs to populate")
        
        return True
        
    except Exception as e:
        print(f"❌ ChromaDB connection FAILED: {e}")
        return False

def show_summary():
    """Show architecture summary"""
    print("\n" + "=" * 60)
    print("DATABASE ARCHITECTURE SUMMARY")
    print("=" * 60)
    print("""
📊 Two-Database System:

1. MongoDB Atlas (Cloud)
   Purpose: Store structured app data
   - Users, quizzes, scores
   - Chat history, analytics
   - Admin data
   Status: Ready for scaling ✅

2. ChromaDB (Local)
   Purpose: Store vector embeddings
   - PDF content chunks
   - Semantic search
   - RAG context
   Status: Active ✅

3. SQLite (Local) - Current
   Purpose: Django ORM models
   - Used by Django admin
   - Will migrate to MongoDB later
   Status: Active ✅
    """)

if __name__ == "__main__":
    print("\n🚀 NCERT Learning Platform - Database Connection Test\n")
    
    mongodb_ok = test_mongodb()
    chromadb_ok = test_chromadb()
    
    show_summary()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"MongoDB Atlas: {'✅ PASSED' if mongodb_ok else '❌ FAILED'}")
    print(f"ChromaDB:      {'✅ PASSED' if chromadb_ok else '❌ FAILED'}")
    
    if mongodb_ok and chromadb_ok:
        print("\n🎉 All systems operational!")
    else:
        print("\n⚠️  Some systems need attention - see errors above")
    
    print("=" * 60)
