"""
Clean up ChromaDB - Remove empty/unwanted collections
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

import chromadb
from collections import defaultdict


print("="*70)
print("🧹 CHROMADB CLEANUP & VERIFICATION")
print("="*70)

client = chromadb.PersistentClient(path='./chromadb_data')

# Step 1: List all collections
print("\n📚 STEP 1: Finding all collections...")
collections = client.list_collections()
print(f"Found {len(collections)} collections\n")

for i, col in enumerate(collections, 1):
    count = col.count()
    status = "✅ HAS DATA" if count > 0 else "❌ EMPTY"
    print(f"{i}. {col.name}")
    print(f"   Documents: {count} {status}")
    print(f"   UUID: {col.id}")
    print()

# Step 2: Clean up empty collections
print("="*70)
print("🗑️  STEP 2: Cleaning up empty collections...")
print("="*70)

for col in collections:
    count = col.count()
    
    # Delete empty collections that are NOT the main one
    if count == 0 and col.name != 'ncert_documents':
        print(f"\n⚠️  Found empty collection: '{col.name}'")
        print(f"   This collection has 0 documents and is not being used.")
        
        try:
            client.delete_collection(col.name)
            print(f"   ✅ DELETED '{col.name}'")
        except Exception as e:
            print(f"   ❌ Error deleting: {e}")

# Step 3: Verify main collection
print("\n" + "="*70)
print("📊 STEP 3: Verifying main collection (ncert_documents)...")
print("="*70)

try:
    main_collection = client.get_collection(name='ncert_documents')
    total_docs = main_collection.count()
    
    print(f"\n✅ Collection: ncert_documents")
    print(f"📄 Total documents: {total_docs}")
    
    if total_docs > 0:
        # Get all metadata
        all_data = main_collection.get(include=["metadatas"])
        
        if all_data and all_data['metadatas']:
            chapters = defaultdict(int)
            subjects = defaultdict(int)
            classes = defaultdict(int)
            
            for meta in all_data['metadatas']:
                chapter = meta.get('chapter', 'Unknown')
                subject = meta.get('subject', 'Unknown')
                class_num = meta.get('class', 'Unknown')
                
                chapters[chapter] += 1
                subjects[subject] += 1
                classes[class_num] += 1
            
            print(f"\n📖 Content Breakdown:")
            print(f"\n   Classes:")
            for cls, count in sorted(classes.items()):
                print(f"      • {cls}: {count} chunks")
            
            print(f"\n   Subjects:")
            for subj, count in sorted(subjects.items()):
                print(f"      • {subj}: {count} chunks")
            
            print(f"\n   Chapters ({len(chapters)} total):")
            for chapter in sorted(chapters.keys()):
                chunk_count = chapters[chapter]
                print(f"      • {chapter}: {chunk_count} chunks")
        
        # Get sample content
        print("\n" + "="*70)
        print("📄 SAMPLE CONTENT (first 3 documents):")
        print("="*70)
        
        sample = main_collection.get(limit=3, include=["documents", "metadatas"])
        
        for i, (doc, meta) in enumerate(zip(sample['documents'], sample['metadatas']), 1):
            print(f"\n--- Document {i} ---")
            print(f"Class: {meta.get('class', 'N/A')}")
            print(f"Subject: {meta.get('subject', 'N/A')}")
            print(f"Chapter: {meta.get('chapter', 'N/A')}")
            print(f"Page: {meta.get('page', 'N/A')}")
            print(f"\nContent preview:")
            print(doc[:300] + "..." if len(doc) > 300 else doc)
    
    else:
        print("\n⚠️  WARNING: Main collection is EMPTY!")
        print("   You need to upload books to populate ChromaDB.")
        print("   Run: python reupload_books.py")

except Exception as e:
    print(f"\n❌ Error accessing main collection: {e}")

# Step 4: Summary
print("\n" + "="*70)
print("✅ CLEANUP COMPLETE")
print("="*70)

# Final collection list
remaining = client.list_collections()
print(f"\n📚 Active Collections: {len(remaining)}")
for col in remaining:
    print(f"   • {col.name}: {col.count()} documents")

print()
