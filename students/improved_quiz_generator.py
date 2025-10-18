"""
Improved Quiz Generation System
- Extracts "Let us reflect" questions from textbooks
- Better ChromaDB chunking with proper chapter mapping
- Age-appropriate question generation
"""
import logging
import re
import json
from typing import List, Dict, Optional
import openai
import google.generativeai as genai
import os
from django.conf import settings

logger = logging.getLogger('students')


def extract_let_us_reflect_questions(content: str) -> List[Dict]:
    """
    Extract 'Let us reflect' questions from textbook content
    These are high-quality questions already in the book
    """
    questions = []
    
    # Pattern to find "Let us reflect" or similar sections
    patterns = [
        r'Let us reflect[:\s]*(.*?)(?=\n\n|\Z)',
        r'Think and Answer[:\s]*(.*?)(?=\n\n|\Z)',
        r'Check your progress[:\s]*(.*?)(?=\n\n|\Z)',
        r'Questions[:\s]*(.*?)(?=\n\n|\Z)',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            section_content = match.group(1)
            
            # Extract numbered questions
            question_pattern = r'\d+\.\s*([^\n]+(?:\n(?!\d+\.)[^\n]+)*)'
            question_matches = re.findall(question_pattern, section_content)
            
            for q_text in question_matches:
                q_text = q_text.strip()
                if len(q_text) > 20:  # Filter out very short matches
                    questions.append({
                        'text': q_text,
                        'source': 'textbook_reflect_section'
                    })
    
    return questions


def generate_mcqs_from_textbook_questions(textbook_questions: List[Dict], content: str, class_num: str) -> List[Dict]:
    """
    Convert textbook questions into MCQs with AI
    """
    if not textbook_questions:
        return []
    
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        
        # Age-appropriate settings
        class_number = int(''.join(filter(str.isdigit, str(class_num))))
        if class_number <= 5:
            language_level = "very simple language for 10-11 year olds"
        elif class_number <= 8:
            language_level = "moderate language for 12-14 year olds"
        else:
            language_level = "advanced language for 15+ year olds"
        
        # Prepare questions for AI
        questions_text = "\n".join([f"{i+1}. {q['text']}" for i, q in enumerate(textbook_questions[:10])])
        
        prompt = f"""You are converting textbook reflection questions into MCQs for Class {class_num} students.

TEXTBOOK QUESTIONS:
{questions_text}

CHAPTER CONTENT (for context):
{content[:3000]}

TASK: Convert EACH question into a 4-option MCQ with 3 variants.

REQUIREMENTS:
1. Use {language_level}
2. Keep the original question's intent and difficulty
3. Create exactly 4 options (A, B, C, D) per question
4. Generate 3 variants (different wording, same concept)
5. Extract relevant RAG context from the content
6. Mix difficulty: label as easy/medium/hard based on original question complexity
7. EXPLANATIONS: Keep SHORT (2-3 sentences max), simple, plain text - NO markdown (no *, #, **, _)

EXPLANATION RULES:
✅ GOOD: "The answer is B because rivers flow from mountains to the sea. Water always moves downward due to gravity."
❌ BAD: "**Rivers flow from mountains to the sea.** This is because of *gravity* which pulls water downward. Rivers start high up..."

OUTPUT FORMAT (JSON):
[
  {{
    "original_question": "Original textbook question",
    "topic": "Topic name",
    "difficulty": "easy|medium|hard",
    "rag_context": "Relevant content quote",
    "variants": [
      {{
        "question": "MCQ version of the question?",
        "options": {{
          "A": "First option",
          "B": "Second option",
          "C": "Third option",
          "D": "Fourth option"
        }},
        "correct": "B",
        "explanation": "Why B is correct with reference to content"
      }},
      {{
        "question": "Variant 2 wording?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "C",
        "explanation": "Explanation for variant 2"
      }},
      {{
        "question": "Variant 3 wording?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "A",
        "explanation": "Explanation for variant 3"
      }}
    ]
  }}
]

Return ONLY the JSON array."""
        
        # Try OpenAI
        if openai.api_key:
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an expert at converting textbook questions to MCQs. Output only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000
                )
                result_text = response.choices[0].message.content
                logger.info("✅ OpenAI converted textbook questions to MCQs")
            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                result_text = None
        else:
            result_text = None
        
        # Fallback to Gemini
        if not result_text and gemini_api_key:
            try:
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(prompt)
                result_text = response.text
                logger.info("✅ Gemini converted textbook questions to MCQs")
            except Exception as e:
                logger.error(f"Gemini error: {e}")
                return []
        
        if not result_text:
            logger.error("❌ No AI service available")
            return []
        
        # Parse JSON
        result_text = result_text.strip()
        if result_text.startswith('```json'):
            result_text = result_text[7:]
        if result_text.startswith('```'):
            result_text = result_text[3:]
        if result_text.endswith('```'):
            result_text = result_text[:-3]
        
        questions = json.loads(result_text.strip())
        logger.info(f"✅ Generated {len(questions)} MCQs from textbook questions")
        
        return questions
        
    except Exception as e:
        logger.error(f"❌ Error converting textbook questions: {e}")
        return []


def generate_quiz_with_textbook_questions(chapter_id: str, class_num: str, subject: str, chapter_name: str, chapter_order: int) -> Dict:
    """
    NEW APPROACH: Generate quizzes prioritizing textbook "Let us reflect" questions
    Falls back to AI generation if needed
    """
    from ncert_project.chromadb_utils import get_chromadb_manager
    from students.models import QuizChapter, QuizQuestion, QuestionVariant
    
    try:
        # Get ChromaDB content
        chroma_manager = get_chromadb_manager()
        logger.info(f"🔍 Fetching content for: {chapter_name} (Class {class_num}, {subject})")
        
        # Build specific query for this chapter
        query_text = f"{subject} {chapter_name} Class {class_num}"
        
        results = chroma_manager.query_by_class_subject_chapter(
            query_text=query_text,
            class_num=class_num,
            n_results=30  # Get more content
        )
        
        if not results or not results.get("documents") or not results["documents"][0]:
            logger.error(f"❌ No ChromaDB content for {chapter_id}")
            return {"success": False, "error": "No content in ChromaDB"}
        
        # Combine all documents
        documents = results["documents"][0]
        full_content = "\n\n".join(documents)
        
        logger.info(f"📄 Retrieved {len(documents)} chunks, total {len(full_content)} chars")
        
        # STEP 1: Extract "Let us reflect" questions
        textbook_questions = extract_let_us_reflect_questions(full_content)
        logger.info(f"📝 Found {len(textbook_questions)} textbook reflection questions")
        
        # STEP 2: Convert to MCQs
        if textbook_questions:
            mcq_data = generate_mcqs_from_textbook_questions(textbook_questions, full_content, class_num)
        else:
            logger.warning("⚠️ No textbook questions found, generating from content")
            # Fallback to regular AI generation
            from students.quiz_generator import generate_mcq_questions_with_ai
            mcq_data = generate_mcq_questions_with_ai(full_content, chapter_name, class_num)
        
        if not mcq_data:
            logger.error("❌ Failed to generate MCQs")
            return {"success": False, "error": "Failed to generate questions"}
        
        # Ensure exactly 10 questions (or use what we have)
        mcq_data = mcq_data[:10]
        
        # STEP 3: Create/update database records
        quiz_chapter, created = QuizChapter.objects.get_or_create(
            chapter_id=chapter_id,
            defaults={
                'class_number': f"Class {class_num}",
                'subject': subject,
                'chapter_name': chapter_name,
                'chapter_order': chapter_order,
                'total_questions': len(mcq_data),
                'passing_percentage': 70,
                'is_active': True
            }
        )
        
        if not created:
            # Delete old questions
            QuizQuestion.objects.filter(chapter=quiz_chapter).delete()
            quiz_chapter.total_questions = len(mcq_data)
            quiz_chapter.save()
        
        # Create questions and variants
        for q_num, q_data in enumerate(mcq_data, 1):
            quiz_question = QuizQuestion.objects.create(
                chapter=quiz_chapter,
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
        
        logger.info(f"✅ Created quiz: {len(mcq_data)} questions × 3 variants = {len(mcq_data)*3} total variants")
        
        return {
            "success": True,
            "chapter_id": chapter_id,
            "total_questions": len(mcq_data),
            "textbook_questions_used": len(textbook_questions)
        }
        
    except Exception as e:
        logger.error(f"❌ Quiz generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
