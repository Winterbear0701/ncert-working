"""
Unit Test Evaluation System - Test Script

This script demonstrates and tests the evaluation system with sample questions.
Run this to verify the evaluation is working correctly.

Usage:
    python test_evaluation_system.py
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from superadmin.evaluate import evaluate_answer


def test_one_mark_questions():
    """Test case-insensitive matching for 1-mark questions"""
    print("\n" + "="*70)
    print("TEST 1: ONE-MARK QUESTIONS (Case-Insensitive Exact Match)")
    print("="*70)
    
    model_answer = "Photosynthesis"
    question = "What is the process by which plants make food?"
    
    test_cases = [
        ("photosynthesis", 1, "lowercase"),
        ("PHOTOSYNTHESIS", 1, "uppercase"),
        ("Photosynthesis", 1, "correct case"),
        ("Photosynthesis.", 1, "with period"),
        ("  photosynthesis  ", 1, "with spaces"),
        ("Photo synthesis", 0, "with space in middle"),
        ("The process is photosynthesis", 0, "extra words"),
        ("synthesis", 0, "partial answer"),
    ]
    
    for student_answer, expected_marks, description in test_cases:
        result = evaluate_answer(
            student_answer=student_answer,
            model_answer=model_answer,
            marks=1,
            question=question
        )
        
        status = "✓ PASS" if result['awarded_marks'] == expected_marks else "✗ FAIL"
        print(f"\n{status} | {description}")
        print(f"Student: '{student_answer}'")
        print(f"Expected: {expected_marks}/1, Got: {result['awarded_marks']}/1")
        print(f"Feedback: {result['feedback']}")


def test_multi_mark_questions():
    """Test AI evaluation for 2-5 mark questions"""
    print("\n" + "="*70)
    print("TEST 2: MULTI-MARK QUESTIONS (AI Evaluation)")
    print("="*70)
    
    # Test Case 1: 3-mark question
    question_3m = "Explain the process of photosynthesis."
    model_answer_3m = """Photosynthesis is the process by which green plants make 
their own food using sunlight, water, and carbon dioxide. Chlorophyll in the leaves 
absorbs sunlight. The plant takes in carbon dioxide from the air and water from the 
soil. Using the energy from sunlight, these are converted into glucose (food) and 
oxygen. The oxygen is released into the air."""
    
    print("\n" + "-"*70)
    print("3-MARK QUESTION:")
    print(f"Q: {question_3m}")
    print(f"\nModel Answer:\n{model_answer_3m}")
    print("-"*70)
    
    # Good answer
    student_answer_good = """Photosynthesis is the process where green plants produce 
food. Plants use sunlight, carbon dioxide from air, and water from soil. Chlorophyll 
in leaves captures sunlight energy. This energy converts CO2 and water into glucose 
which is food for the plant. Oxygen is produced and released as a byproduct."""
    
    print("\n📝 Student Answer 1 (Expected: High Score):")
    print(student_answer_good)
    
    result_good = evaluate_answer(
        student_answer=student_answer_good,
        model_answer=model_answer_3m,
        marks=3,
        question=question_3m,
        ai_model='gemini'
    )
    
    print(f"\n✨ RESULT:")
    print(f"Marks: {result_good['awarded_marks']}/3")
    print(f"Content: {result_good['content_score']*100:.0f}%")
    print(f"Grammar: {result_good['grammar_score']*100:.0f}%")
    print(f"Type: {result_good['evaluation_type']}")
    print(f"AI Model: {result_good['ai_model_used']}")
    print(f"\nFeedback:\n{result_good['feedback']}")
    
    # Average answer
    student_answer_avg = """photosynthesis is when plants make food they use sun 
and water and co2 to make food and give oxygen"""
    
    print("\n" + "-"*70)
    print("\n📝 Student Answer 2 (Expected: Medium Score):")
    print(student_answer_avg)
    
    result_avg = evaluate_answer(
        student_answer=student_answer_avg,
        model_answer=model_answer_3m,
        marks=3,
        question=question_3m,
        ai_model='gemini'
    )
    
    print(f"\n✨ RESULT:")
    print(f"Marks: {result_avg['awarded_marks']}/3")
    print(f"Content: {result_avg['content_score']*100:.0f}%")
    print(f"Grammar: {result_avg['grammar_score']*100:.0f}%")
    print(f"\nFeedback:\n{result_avg['feedback']}")
    
    # Poor answer
    student_answer_poor = """plants make food"""
    
    print("\n" + "-"*70)
    print("\n📝 Student Answer 3 (Expected: Low Score):")
    print(student_answer_poor)
    
    result_poor = evaluate_answer(
        student_answer=student_answer_poor,
        model_answer=model_answer_3m,
        marks=3,
        question=question_3m,
        ai_model='gemini'
    )
    
    print(f"\n✨ RESULT:")
    print(f"Marks: {result_poor['awarded_marks']}/3")
    print(f"Content: {result_poor['content_score']*100:.0f}%")
    print(f"Grammar: {result_poor['grammar_score']*100:.0f}%")
    print(f"\nFeedback:\n{result_poor['feedback']}")


def test_five_mark_question():
    """Test 5-mark question evaluation"""
    print("\n" + "="*70)
    print("TEST 3: FIVE-MARK QUESTION")
    print("="*70)
    
    question_5m = "Describe the water cycle and explain its importance."
    model_answer_5m = """The water cycle is the continuous movement of water on, 
above, and below the Earth's surface. It involves four main processes: evaporation, 
condensation, precipitation, and collection. 

The sun heats water in oceans, rivers, and lakes, causing evaporation where water 
turns into water vapor. This vapor rises and cools in the atmosphere, undergoing 
condensation to form clouds. When clouds become heavy, water falls back to Earth 
as precipitation (rain, snow, sleet, or hail). The water then collects in water 
bodies or seeps into the ground, and the cycle continues.

The water cycle is important because it provides fresh water for drinking, 
agriculture, and industry. It helps regulate Earth's temperature and distributes 
water resources across different regions. It also supports all forms of life on Earth."""
    
    print(f"Q: {question_5m}")
    print(f"\nModel Answer:\n{model_answer_5m}")
    print("-"*70)
    
    student_answer = """The water cycle describes how water moves continuously on Earth. 
It has four main steps. First is evaporation where the sun heats water and it becomes 
vapor. Second is condensation when the vapor cools and forms clouds. Third is 
precipitation when water falls as rain or snow. Fourth is collection when water 
gathers in rivers and oceans.

The water cycle is very important. It gives us fresh water to drink. It is used for 
farming and factories. It helps maintain temperature on Earth. It also supports plants 
and animals."""
    
    print(f"\n📝 Student Answer:")
    print(student_answer)
    
    result = evaluate_answer(
        student_answer=student_answer,
        model_answer=model_answer_5m,
        marks=5,
        question=question_5m,
        ai_model='gemini'
    )
    
    print(f"\n✨ RESULT:")
    print(f"Marks: {result['awarded_marks']}/5")
    print(f"Content: {result['content_score']*100:.0f}%")
    print(f"Grammar: {result['grammar_score']*100:.0f}%")
    print(f"\nFeedback:\n{result['feedback']}")


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("UNIT TEST EVALUATION SYSTEM - TEST SUITE")
    print("="*70)
    print("\nThis script tests the AI-powered evaluation system.")
    print("It demonstrates:")
    print("  1. Case-insensitive exact matching for 1-mark questions")
    print("  2. AI evaluation with content & grammar scoring for multi-mark questions")
    print("  3. Detailed feedback generation")
    
    try:
        # Run tests
        test_one_mark_questions()
        test_multi_mark_questions()
        test_five_mark_question()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS COMPLETED")
        print("="*70)
        print("\nNOTE: AI evaluations may vary slightly based on:")
        print("  - API availability")
        print("  - Model version")
        print("  - Prompt interpretation")
        print("\nThis is normal and expected behavior.")
        
    except Exception as e:
        print("\n" + "="*70)
        print("❌ ERROR OCCURRED")
        print("="*70)
        print(f"\nError: {str(e)}")
        print("\nPossible causes:")
        print("  1. API keys not set in .env file")
        print("  2. API quota exceeded")
        print("  3. Network connectivity issues")
        print("\nCheck the documentation for troubleshooting.")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
