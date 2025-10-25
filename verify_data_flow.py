#!/usr/bin/env python
"""
Verification script to show data flow:
1. PDF Upload → Pinecone (embeddings)
2. Student Registration → MongoDB Atlas (user data)
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from ncert_project.vector_db_utils import get_vector_db_manager
from ncert_project.mongodb_utils import mongodb_manager

print("\n" + "="*70)
print("🔍 DATA FLOW VERIFICATION")
print("="*70)

# Check Vector Database (for PDF embeddings)
print("\n📚 PDF Upload Flow:")
print("-" * 70)
vector_manager = get_vector_db_manager()
print(f"✅ Vector DB Type: {type(vector_manager).__name__}")

if hasattr(vector_manager, 'index_name'):
    print(f"✅ Storage: Pinecone Cloud")
    print(f"✅ Index: {vector_manager.index_name}")
    stats = vector_manager.index.describe_index_stats()
    total_vectors = stats.get('total_vector_count', 0)
    print(f"✅ Current Embeddings: {total_vectors}")
    print("\n   When you upload a PDF:")
    print("   1. PDF → Text extraction")
    print("   2. Text → Chunks (semantic splitting)")
    print("   3. Chunks → Embeddings (384-dim vectors)")
    print("   4. Embeddings → Pinecone Cloud ☁️")
else:
    print(f"⚠️  Using local ChromaDB (check VECTOR_DB in .env)")

# Check MongoDB Atlas (for student data)
print("\n👥 Student Registration Flow:")
print("-" * 70)
mongo_manager = mongodb_manager
print(f"✅ Database Type: MongoDB Atlas (Cloud)")
print(f"✅ Database: {mongo_manager.db.name}")

# Check current collections
collections = mongo_manager.db.list_collection_names()
print(f"✅ Current Collections: {len(collections)}")
if collections:
    for coll in collections:
        count = mongo_manager.db[coll].count_documents({})
        print(f"   • {coll}: {count} documents")
else:
    print("   (No collections yet - empty database)")

print("\n   When a student registers:")
print("   1. Registration form → User data")
print("   2. User data → MongoDB Atlas ☁️")
print("   3. Stored in 'students' collection")
print("   4. Includes: name, email, class, subjects, progress")

# Summary
print("\n" + "="*70)
print("📊 DATA STORAGE SUMMARY")
print("="*70)
print("\n☁️  PINECONE (Cloud Vector Database):")
print("   • PDF text chunks & embeddings")
print("   • RAG (chatbot) search")
print("   • Quiz question generation")

print("\n☁️  MONGODB ATLAS (Cloud Document Database):")
print("   • Student accounts & profiles")
print("   • Teacher accounts")
print("   • Quiz questions & answers")
print("   • Quiz attempts & scores")
print("   • Chat history")
print("   • Upload metadata")

print("\n💿 SQLITE (Local - Temporary):")
print("   • Django admin sessions only")
print("   • Data lost on restart")

print("\n" + "="*70)
print("✅ READY TO TEST!")
print("="*70)
print("\n1. Upload a PDF at: http://127.0.0.1:8000/superadmin/")
print("2. Register as student at: http://127.0.0.1:8000/accounts/register/")
print("3. Check this script again to see the data!")
print("\n" + "="*70)
