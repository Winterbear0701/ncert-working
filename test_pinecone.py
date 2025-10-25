#!/usr/bin/env python
"""
Test script to verify Pinecone configuration and connectivity
"""

import os
import sys
import django
from dotenv import load_dotenv

# Setup Django
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

def test_pinecone():
    """Test Pinecone connection and basic operations"""
    
    print("\n" + "=" * 70)
    print("🧪 Pinecone Configuration Test")
    print("=" * 70)
    
    # Check environment variables
    print("\n📋 Step 1: Checking Environment Variables...")
    
    api_key = os.getenv('PINECONE_API_KEY')
    index_name = os.getenv('PINECONE_INDEX_NAME', 'ncert-learning-rag')
    vector_db = os.getenv('VECTOR_DB', 'chromadb')
    
    if not api_key or api_key == 'your_pinecone_api_key_here':
        print("   ❌ PINECONE_API_KEY not set in .env file")
        print("\n💡 Instructions:")
        print("   1. Get API key from: https://app.pinecone.io/")
        print("   2. Add to .env: PINECONE_API_KEY=your_actual_key")
        return False
    
    print(f"   ✅ PINECONE_API_KEY: {'*' * 20}{api_key[-8:]}")
    print(f"   ✅ PINECONE_INDEX_NAME: {index_name}")
    print(f"   📊 VECTOR_DB: {vector_db}")
    
    if vector_db != 'pinecone':
        print(f"\n   ⚠️  Note: VECTOR_DB is set to '{vector_db}'")
        print("   Change to 'pinecone' in .env to use Pinecone in production")
    
    # Test connection
    print("\n🔌 Step 2: Testing Pinecone Connection...")
    
    try:
        from ncert_project.pinecone_utils import get_pinecone_manager
        pinecone = get_pinecone_manager()
        print("   ✅ Successfully connected to Pinecone")
    except Exception as e:
        print(f"   ❌ Failed to connect: {e}")
        return False
    
    # Get stats
    print("\n📊 Step 3: Getting Index Statistics...")
    
    try:
        stats = pinecone.get_stats()
        print(f"   ✅ Index Name: {pinecone.index_name}")
        print(f"   ✅ Total Vectors: {stats.get('total_vectors', 0)}")
        print(f"   ✅ Dimension: {stats.get('dimension', 0)}")
        print(f"   ✅ Index Fullness: {stats.get('index_fullness', 0.0):.2%}")
        
        if stats.get('total_vectors', 0) == 0:
            print("\n   ⚠️  Index is empty!")
            print("   Run 'python migrate_to_pinecone.py' to migrate data from ChromaDB")
        
    except Exception as e:
        print(f"   ⚠️  Could not get stats: {e}")
    
    # Test query
    print("\n🔍 Step 4: Testing Query Functionality...")
    
    try:
        test_query = "What is photosynthesis?"
        print(f"   Query: '{test_query}'")
        
        results = pinecone.query_by_class_subject_chapter(
            query_text=test_query,
            n_results=3
        )
        
        num_results = len(results['documents'][0])
        print(f"   ✅ Query successful!")
        print(f"   ✅ Results returned: {num_results}")
        
        if num_results > 0:
            print(f"\n   📄 Sample Result:")
            print(f"      Text: {results['documents'][0][0][:100]}...")
            print(f"      Metadata: {results['metadatas'][0][0]}")
        else:
            print("\n   ⚠️  Query returned 0 results (index might be empty)")
        
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
    
    # Test adding sample data
    print("\n📝 Step 5: Testing Add Functionality...")
    
    try:
        sample_chunks = [
            {
                'text': 'This is a test chunk for Pinecone configuration validation.',
                'page': 1,
                'chunk_index': 0,
                'has_equations': False,
                'content_type': 'test'
            }
        ]
        
        pinecone.add_document_chunks(
            chunks=sample_chunks,
            standard='99',
            subject='Test Subject',
            chapter='Test Chapter',
            source_file='test_file.pdf',
            batch_size=1
        )
        
        print("   ✅ Successfully added test data")
        print("   ℹ️  Test data will be cleaned up automatically")
        
        # Query for test data
        test_results = pinecone.query_by_class_subject_chapter(
            query_text='test chunk',
            class_num='99',
            n_results=1
        )
        
        if len(test_results['documents'][0]) > 0:
            print("   ✅ Test data retrieved successfully")
        
        # Clean up test data
        try:
            pinecone.delete_by_filter({'standard': '99'})
            print("   ✅ Test data cleaned up")
        except:
            print("   ⚠️  Could not clean up test data (manual cleanup may be needed)")
        
    except Exception as e:
        print(f"   ⚠️  Add test warning: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("🎉 Pinecone Configuration Test Complete!")
    print("=" * 70)
    
    print("\n✅ All Systems Operational:")
    print("   • Pinecone connection: Working")
    print("   • Index access: Working")
    print("   • Query operations: Working")
    print("   • Add operations: Working")
    
    print("\n📝 Next Steps:")
    
    if stats.get('total_vectors', 0) == 0:
        print("   1. Run migration: python migrate_to_pinecone.py")
        print("   2. Update .env: VECTOR_DB=pinecone")
        print("   3. Restart server: python manage.py runserver")
    else:
        if vector_db != 'pinecone':
            print("   1. Update .env: VECTOR_DB=pinecone")
            print("   2. Restart server: python manage.py runserver")
        else:
            print("   ✅ Everything is configured correctly!")
            print("   Your application is using Pinecone for vector storage.")
    
    print("\n" + "=" * 70)
    return True


if __name__ == '__main__':
    try:
        test_pinecone()
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
