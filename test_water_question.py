"""
Quick test for the water question evaluation issue
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from superadmin.evaluate import evaluate_answer

# The problematic question
question = "Why do you think most of the water on Earth cannot be used for drinking or farming?"

model_answer = "Most of the water on Earth cannot be used for drinking or farming, because our earth has 70% ocean and the water are salty."

student_answer = "because it is too salty and it is not used in drinking and farming"

print("=" * 80)
print("TESTING WATER QUESTION EVALUATION")
print("=" * 80)
print(f"\nQuestion: {question}")
print(f"\nModel Answer:\n{model_answer}")
print(f"\nStudent Answer:\n{student_answer}")
print("\n" + "-" * 80)

# Test with both AI models
for ai_model in ['gemini', 'openai']:
    print(f"\n🤖 Testing with {ai_model.upper()}:")
    print("-" * 80)
    
    try:
        result = evaluate_answer(
            student_answer=student_answer,
            model_answer=model_answer,
            marks=1,  # Assuming 1 mark based on the screenshot
            question=question,
            ai_model=ai_model
        )
        
        print(f"✅ SUCCESS")
        print(f"Awarded Marks: {result['awarded_marks']}/1")
        print(f"Content Score: {result['content_score']*100:.0f}%")
        print(f"Grammar Score: {result['grammar_score']*100:.0f}%")
        print(f"Evaluation Type: {result['evaluation_type']}")
        print(f"\nFeedback:\n{result['feedback']}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    print("\n" + "=" * 80)

print("\n💡 ANALYSIS:")
print("The student's answer correctly identifies:")
print("  ✓ Water is salty (main concept)")
print("  ✓ Cannot be used for drinking (mentioned)")
print("  ✓ Cannot be used for farming (mentioned)")
print("\nThe student has the RIGHT CONCEPT even though wording is different!")
print("They should get at least 70-80% content score for this.")
