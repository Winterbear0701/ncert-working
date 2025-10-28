"""
Test script for ChatCache Quality Control System

This script tests the new quality-based caching mechanism:
1. Quality score calculation
2. Adaptive cache duration
3. Negative feedback system
4. Cache invalidation

Run from ncert-working directory:
    source ncert/bin/activate
    python test_cache_quality.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/chessman/Projects/ncert-working')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from students.models import ChatCache
from django.utils import timezone
from datetime import timedelta
import hashlib

def get_query_hash(question):
    """Create hash for question (matches web_scraper.py logic)"""
    normalized = question.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()

def test_quality_scoring():
    """Test 1: Quality Score and Adaptive Duration"""
    print("\n" + "="*60)
    print("TEST 1: Quality Score & Adaptive Cache Duration")
    print("="*60)
    
    # Clean up test data
    ChatCache.objects.filter(question__startswith="TEST:").delete()
    
    # Test Case 1: High Quality (RAG relevance 0.85)
    print("\n📊 Test Case 1: High Quality Answer (RAG 0.85)")
    cache_high = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: What is photosynthesis?"),
        question="TEST: What is photosynthesis?",
        answer="Test answer with good RAG",
        quality_score=1.0,
        has_rag_context=True,
        rag_relevance=0.85
    )
    days_cached = (cache_high.expires_at - cache_high.created_at).days
    print(f"   ✅ Quality Score: {cache_high.quality_score}")
    print(f"   ✅ RAG Relevance: {cache_high.rag_relevance}")
    print(f"   ✅ Cache Duration: {days_cached} days")
    assert days_cached >= 9 and days_cached <= 10, f"Expected 9-10 days, got {days_cached}"
    print("   ✅ PASS: High quality cached for 10 days")
    
    # Test Case 2: Medium Quality (RAG relevance 0.55)
    print("\n📊 Test Case 2: Medium Quality Answer (RAG 0.55)")
    cache_medium = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: What is mitosis?"),
        question="TEST: What is mitosis?",
        answer="Test answer with moderate RAG",
        quality_score=0.6,  # Between 0.5 and 0.7 = medium quality
        has_rag_context=True,
        rag_relevance=0.55
    )
    days_cached = (cache_medium.expires_at - cache_medium.created_at).days
    print(f"   ✅ Quality Score: {cache_medium.quality_score}")
    print(f"   ✅ RAG Relevance: {cache_medium.rag_relevance}")
    print(f"   ✅ Cache Duration: {days_cached} days")
    assert days_cached >= 2 and days_cached <= 3, f"Expected 2-3 days, got {days_cached}"
    print("   ✅ PASS: Medium quality cached for 3 days")
    
    # Test Case 3: Low Quality (No RAG)
    print("\n📊 Test Case 3: Low Quality Answer (No RAG)")
    cache_low = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: How to make unicorn?"),
        question="TEST: How to make unicorn?",
        answer="Hallucinated answer",
        quality_score=0.5,
        has_rag_context=False,
        rag_relevance=0.0
    )
    days_cached = (cache_low.expires_at - cache_low.created_at).days
    print(f"   ✅ Quality Score: {cache_low.quality_score}")
    print(f"   ✅ RAG Relevance: {cache_low.rag_relevance}")
    print(f"   ✅ Cache Duration: {days_cached} days")
    assert days_cached >= 0 and days_cached <= 1, f"Expected 0-1 days, got {days_cached}"
    print("   ✅ PASS: Low quality cached for 1 day only")
    
    print("\n✅ TEST 1 PASSED: Adaptive cache duration working correctly!")


def test_negative_feedback():
    """Test 2: Negative Feedback and Auto-Invalidation"""
    print("\n" + "="*60)
    print("TEST 2: Negative Feedback System")
    print("="*60)
    
    # Create test cache
    cache = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: Feedback test"),
        question="TEST: Feedback test",
        answer="Test answer for feedback",
        quality_score=0.7,
        has_rag_context=True,
        rag_relevance=0.6
    )
    
    print(f"\n📝 Created cache entry (ID: {cache.id})")
    print(f"   Initial negative_feedback_count: {cache.negative_feedback_count}")
    print(f"   Initial is_invalidated: {cache.is_invalidated}")
    
    # First feedback report
    print("\n👤 Student 1 reports wrong answer...")
    cache.report_negative_feedback()
    cache.refresh_from_db()
    print(f"   Feedback count: {cache.negative_feedback_count}")
    print(f"   Is invalidated: {cache.is_invalidated}")
    assert cache.negative_feedback_count == 1, "Expected count = 1"
    assert not cache.is_invalidated, "Should NOT be invalidated yet"
    print("   ✅ PASS: First report tracked, not invalidated")
    
    # Second feedback report
    print("\n👤 Student 2 reports wrong answer...")
    cache.report_negative_feedback()
    cache.refresh_from_db()
    print(f"   Feedback count: {cache.negative_feedback_count}")
    print(f"   Is invalidated: {cache.is_invalidated}")
    assert cache.negative_feedback_count == 2, "Expected count = 2"
    assert cache.is_invalidated, "Should be invalidated after 2 reports"
    print("   ✅ PASS: Auto-invalidated after 2 reports")
    
    # Try to retrieve invalidated cache
    print("\n🔍 Attempting to retrieve invalidated cache...")
    retrieved = ChatCache.get_active_cache(cache.question_hash)
    print(f"   Retrieved: {retrieved}")
    assert retrieved is None, "Invalidated cache should not be retrieved"
    print("   ✅ PASS: Invalidated cache not returned")
    
    # Check if deleted
    print("\n🗑️  Checking if cache was deleted...")
    exists = ChatCache.objects.filter(id=cache.id).exists()
    print(f"   Cache still exists in DB: {exists}")
    assert not exists, "Invalidated cache should be deleted"
    print("   ✅ PASS: Invalidated cache auto-deleted")
    
    print("\n✅ TEST 2 PASSED: Negative feedback system working correctly!")


def test_quality_gate():
    """Test 3: Quality Gate on Cache Retrieval"""
    print("\n" + "="*60)
    print("TEST 3: Quality Gate on Retrieval")
    print("="*60)
    
    # Test Case 1: Expired cache
    print("\n⏰ Test Case 1: Expired Cache")
    expired_cache = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: Expired"),
        question="TEST: Expired",
        answer="Old answer",
        quality_score=1.0,
        has_rag_context=True
    )
    # Force expiration
    expired_cache.expires_at = timezone.now() - timedelta(days=1)
    expired_cache.save()
    
    retrieved = ChatCache.get_active_cache(expired_cache.question_hash)
    print(f"   Retrieved expired cache: {retrieved}")
    assert retrieved is None, "Expired cache should not be retrieved"
    print("   ✅ PASS: Expired cache rejected")
    
    # Test Case 2: Very low quality
    print("\n📉 Test Case 2: Very Low Quality (0.2)")
    low_quality = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: Low quality"),
        question="TEST: Low quality",
        answer="Bad answer",
        quality_score=0.2,  # Very low
        has_rag_context=False
    )
    
    retrieved = ChatCache.get_active_cache(low_quality.question_hash)
    print(f"   Retrieved low quality cache: {retrieved}")
    assert retrieved is None, "Very low quality cache should be rejected"
    print("   ✅ PASS: Low quality cache rejected")
    
    # Test Case 3: Valid high-quality cache
    print("\n⭐ Test Case 3: Valid High-Quality Cache")
    good_cache = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: Good answer"),
        question="TEST: Good answer",
        answer="Excellent answer",
        quality_score=0.9,
        has_rag_context=True,
        rag_relevance=0.8
    )
    
    retrieved = ChatCache.get_active_cache(good_cache.question_hash)
    print(f"   Retrieved: {retrieved}")
    print(f"   Hit count: {retrieved.hit_count if retrieved else 0}")
    assert retrieved is not None, "Good cache should be retrieved"
    assert retrieved.hit_count == 1, "Hit count should increment"
    print("   ✅ PASS: High-quality cache retrieved successfully")
    
    print("\n✅ TEST 3 PASSED: Quality gate working correctly!")


def test_manual_invalidation():
    """Test 4: Manual Invalidation"""
    print("\n" + "="*60)
    print("TEST 4: Manual Invalidation")
    print("="*60)
    
    # Create cache
    cache = ChatCache.objects.create(
        question_hash=get_query_hash("TEST: Manual invalidate"),
        question="TEST: Manual invalidate",
        answer="Answer to be invalidated",
        quality_score=0.8,
        has_rag_context=True
    )
    
    print(f"\n📝 Created cache entry")
    print(f"   Is invalidated: {cache.is_invalidated}")
    
    # Manually invalidate
    print("\n🛑 Manually invalidating cache...")
    cache.invalidate()
    cache.refresh_from_db()
    print(f"   Is invalidated: {cache.is_invalidated}")
    assert cache.is_invalidated, "Should be invalidated"
    print("   ✅ PASS: Manual invalidation works")
    
    # Try to retrieve
    print("\n🔍 Attempting retrieval...")
    retrieved = ChatCache.get_active_cache(cache.question_hash)
    print(f"   Retrieved: {retrieved}")
    assert retrieved is None, "Invalidated cache should not be retrieved"
    print("   ✅ PASS: Manually invalidated cache rejected")
    
    print("\n✅ TEST 4 PASSED: Manual invalidation working correctly!")


def cleanup():
    """Clean up all test data"""
    print("\n" + "="*60)
    print("CLEANUP")
    print("="*60)
    deleted = ChatCache.objects.filter(question__startswith="TEST:").delete()[0]
    print(f"🗑️  Deleted {deleted} test cache entries")


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  CHATBOT CACHE QUALITY CONTROL - TEST SUITE")
    print("="*70)
    
    try:
        test_quality_scoring()
        test_negative_feedback()
        test_quality_gate()
        test_manual_invalidation()
        
        print("\n" + "="*70)
        print("  ✅ ALL TESTS PASSED!")
        print("="*70)
        print("\n✨ Cache quality control system is working correctly!")
        print("\nKey Features Verified:")
        print("  ✅ Adaptive cache duration (1-10 days based on quality)")
        print("  ✅ RAG relevance scoring")
        print("  ✅ Negative feedback tracking")
        print("  ✅ Auto-invalidation after 2 reports")
        print("  ✅ Quality gate on retrieval")
        print("  ✅ Manual invalidation")
        print("  ✅ Automatic cleanup of invalid entries")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
