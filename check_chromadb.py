"""
Quick diagnostic script to see what's in ChromaDB
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

import chromadb
from collections import defaultdict


def analyze_chromadb():
    """Show what's currently stored in ChromaDB"""
    print("="*60)
    print("🔍 ChromaDB Content Analysis")
    print("="*60)
    
    client = chromadb.PersistentClient(path='./chromadb_data')
    
    try:
        collection = client.get_collection(name='ncert_documents')
    except Exception as e:
        print(f"\n❌ No collection 'ncert_documents' found: {e}")
        return
    
    total_docs = collection.count()
    print(f"\n📊 Total documents: {total_docs}")
    
    # Get all documents
    results = collection.get(
        include=["metadatas"]
    )
    
    if not results or not results['metadatas']:
        print("\n❌ No documents in collection")
        return
    
    # Analyze by class, subject, chapter
    analysis = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    for meta in results['metadatas']:
        class_num = meta.get('class', 'Unknown')
        subject = meta.get('subject', 'Unknown')
        chapter = meta.get('chapter', 'Unknown')
        
        analysis[class_num][subject][chapter] += 1
    
    # Display results
    print("\n📚 Content Breakdown:\n")
    
    for class_num in sorted(analysis.keys()):
        print(f"\n📖 Class {class_num}:")
        
        for subject in sorted(analysis[class_num].keys()):
            print(f"\n  📗 {subject}:")
            
            chapters = analysis[class_num][subject]
            for chapter in sorted(chapters.keys()):
                chunk_count = chapters[chapter]
                print(f"    • {chapter}: {chunk_count} chunks")
    
    # Sample content
    print("\n" + "="*60)
    print("📄 Sample Content (first 3 documents):")
    print("="*60)
    
    sample = collection.get(
        limit=3,
        include=["documents", "metadatas"]
    )
    
    for i, (doc, meta) in enumerate(zip(sample['documents'], sample['metadatas']), 1):
        print(f"\n--- Document {i} ---")
        print(f"Class: {meta.get('class', 'N/A')}")
        print(f"Subject: {meta.get('subject', 'N/A')}")
        print(f"Chapter: {meta.get('chapter', 'N/A')}")
        print(f"Page: {meta.get('page', 'N/A')}")
        print(f"Content preview: {doc[:200]}...")
    
    print("\n" + "="*60)
    print("✅ Analysis complete")
    print("="*60)


if __name__ == '__main__':
    analyze_chromadb()
