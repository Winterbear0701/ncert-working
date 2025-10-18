"""
Regenerate ALL quizzes correctly with proper chapter mapping
Generates EXACTLY 10 questions per chapter from correct ChromaDB content
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

import chromadb
from students.models import QuizChapter, QuizQuestion, QuestionVariant
import openai
import google.generativeai as genai
import json
import re

# Setup AI
openai.api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)


def get_chapter_content_from_chromadb(chapter_name):
    """Get content for a specific chapter from ChromaDB"""
    client = chromadb.PersistentClient(path='./chromadb_data')
    collection = client.get_collection(name='ncert_documents')
    
    # Get ALL data and filter by chapter
    all_data = collection.get(include=["documents", "metadatas"])
    
    chapter_docs = []
    for i, meta in enumerate(all_data['metadatas']):
        if meta.get('chapter') == chapter_name:
            chapter_docs.append(all_data['documents'][i])
    
    combined_content = '\n\n'.join(chapter_docs)
    print(f"   📄 Found {len(chapter_docs)} chunks, {len(combined_content)} chars")
    
    return combined_content


def generate_10_questions_with_ai(content, chapter_name):
    """Generate EXACTLY 10 MCQ questions using AI"""
    
    prompt = f"""You are creating a quiz for Class 5 students from NCERT "The World Around Us" textbook.

CHAPTER: {chapter_name}

CHAPTER CONTENT:
{content[:4000]}

TASK: Generate EXACTLY 10 multiple-choice questions (MCQs) with 3 variants each.

CRITICAL REQUIREMENTS:
1. ALL questions MUST be about the content of THIS chapter only
2. Use very simple language for 10-11 year old students
3. Create EXACTLY 3 VARIANTS of each question (same concept, different wording)
4. Each MCQ must have exactly 4 options (A, B, C, D)
5. Only ONE correct answer per question
6. Explanations: SHORT (2-3 sentences max), plain text, NO markdown formatting
7. Difficulty: 5 easy, 4 medium, 1 hard
8. Cover different topics within THIS chapter
9. MUST generate EXACTLY 10 questions

EXPLANATION STYLE:
✅ GOOD: "The answer is B because rivers flow from mountains to the sea. Water moves downward due to gravity."
❌ BAD: "**Rivers flow** from high to low. This is because of *gravity*..."

OUTPUT FORMAT (STRICT JSON):
[
  {{
    "topic": "Topic name from THIS chapter",
    "difficulty": "easy|medium|hard",
    "rag_context": "Quote from chapter content",
    "variants": [
      {{
        "question": "Simple question about THIS chapter?",
        "options": {{
          "A": "Option A",
          "B": "Option B", 
          "C": "Option C",
          "D": "Option D"
        }},
        "correct": "B",
        "explanation": "Short plain text explanation without markdown"
      }},
      {{
        "question": "Same concept, different wording?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "A",
        "explanation": "Short explanation"
      }},
      {{
        "question": "Third variant of same concept?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "C",
        "explanation": "Short explanation"
      }}
    ]
  }},
  ... (continue for all 10 questions)
]

Generate EXACTLY 10 questions. Return ONLY the JSON array."""

    # Try OpenAI
    if openai.api_key:
        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert NCERT quiz generator. Output only valid JSON with EXACTLY 10 questions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            result_text = response.choices[0].message.content
            print(f"   ✅ OpenAI generated quiz")
        except Exception as e:
            print(f"   ❌ OpenAI error: {e}")
            result_text = None
    else:
        result_text = None
    
    # Fallback to Gemini
    if not result_text and gemini_api_key:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content(prompt)
            result_text = response.text
            print(f"   ✅ Gemini generated quiz")
        except Exception as e:
            print(f"   ❌ Gemini error: {e}")
            return None
    
    if not result_text:
        print(f"   ❌ No AI service available")
        return None
    
    # Parse JSON
    result_text = result_text.strip()
    if result_text.startswith('```json'):
        result_text = result_text[7:]
    if result_text.startswith('```'):
        result_text = result_text[3:]
    if result_text.endswith('```'):
        result_text = result_text[:-3]
    
    try:
        questions = json.loads(result_text.strip())
        print(f"   ✅ Parsed {len(questions)} questions")
        return questions
    except Exception as e:
        print(f"   ❌ JSON parse error: {e}")
        return None


def regenerate_chapter_quiz(chapter):
    """Regenerate quiz for a single chapter"""
    print(f"\n{'='*70}")
    print(f"📖 {chapter.chapter_name}")
    print(f"{'='*70}")
    
    # Get content from ChromaDB
    content = get_chapter_content_from_chromadb(chapter.chapter_name)
    
    if not content or len(content) < 100:
        print(f"   ❌ No content found in ChromaDB!")
        return False
    
    # Generate questions
    questions_data = generate_10_questions_with_ai(content, chapter.chapter_name)
    
    if not questions_data:
        print(f"   ❌ Failed to generate questions")
        return False
    
    # Ensure exactly 10 questions
    if len(questions_data) < 10:
        print(f"   ⚠️  Only got {len(questions_data)} questions, expected 10")
    
    questions_data = questions_data[:10]  # Take max 10
    
    # Save to database
    chapter.total_questions = len(questions_data)
    chapter.save()
    
    for q_num, q_data in enumerate(questions_data, 1):
        quiz_question = QuizQuestion.objects.create(
            chapter=chapter,
            question_number=q_num,
            topic=q_data.get('topic', 'General'),
            difficulty=q_data.get('difficulty', 'medium'),
            rag_context=q_data.get('rag_context', '')
        )
        
        # Create 3 variants
        for v_num, variant_data in enumerate(q_data['variants'], 1):
            QuestionVariant.objects.create(
                question=quiz_question,
                variant_number=v_num,
                question_text=variant_data['question'],
                option_a=variant_data['options']['A'],
                option_b=variant_data['options']['B'],
                option_c=variant_data['options']['C'],
                option_d=variant_data['options']['D'],
                correct_answer=variant_data['correct'],
                explanation=variant_data['explanation']
            )
    
    print(f"   ✅ Created {len(questions_data)} questions × 3 variants = {len(questions_data)*3} total")
    return True


def main():
    """Main regeneration script"""
    print("="*70)
    print("🚀 REGENERATING ALL QUIZZES WITH CORRECT CONTENT")
    print("="*70)
    
    chapters = QuizChapter.objects.filter(
        subject='The World Around Us'
    ).order_by('chapter_order')
    
    print(f"\nFound {chapters.count()} chapters to regenerate\n")
    
    success_count = 0
    for chapter in chapters:
        if regenerate_chapter_quiz(chapter):
            success_count += 1
    
    print(f"\n{'='*70}")
    print(f"✅ COMPLETED: {success_count}/{chapters.count()} chapters regenerated")
    print(f"{'='*70}")
    
    # Summary
    print(f"\n📊 Summary:")
    for ch in QuizChapter.objects.filter(subject='The World Around Us').order_by('chapter_order'):
        q_count = QuizQuestion.objects.filter(chapter=ch).count()
        print(f"  {ch.chapter_name}: {q_count} questions")


if __name__ == '__main__':
    main()
