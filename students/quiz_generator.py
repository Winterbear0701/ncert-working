"""
Quiz Generation Utilities
Auto-generates quiz questions from ChromaDB content
"""
import logging
import re
from typing import List, Dict
import openai
import google.generativeai as genai
import os
from django.conf import settings

logger = logging.getLogger('students')


def generate_quiz_from_chromadb(chapter_id: str, class_num: str, subject: str, chapter_name: str, chapter_order: int) -> Dict:
    """
    Generate quiz questions from existing ChromaDB content
    
    Args:
        chapter_id: Unique chapter identifier (e.g., "class_5_math_chapter_1")
        class_num: Class number (e.g., "5")
        subject: Subject name (e.g., "Mathematics")
        chapter_name: Chapter name (e.g., "Shapes and Angles")
        chapter_order: Sequential order (1, 2, 3...)
    
    Returns:
        Dict with quiz data including questions and variants
    """
    from ncert_project.chromadb_utils import get_chromadb_manager
    from students.models import QuizChapter, QuizQuestion, QuestionVariant
    
    try:
        # 1. Get ChromaDB content for this chapter
        chroma_manager = get_chromadb_manager()
        logger.info(f"🔍 Fetching content from ChromaDB for: {chapter_id}")
        
        # Query for comprehensive chapter content - MUST filter by chapter!
        results = chroma_manager.query_by_class_subject_chapter(
            query_text=f"{chapter_name} complete content summary",
            class_num=class_num,
            subject=subject,
            chapter=chapter_name,  # ← CRITICAL: Filter by specific chapter
            n_results=50  # Get comprehensive content from THIS CHAPTER ONLY
        )
        
        if not results or not results.get("documents") or not results["documents"][0]:
            logger.error(f"❌ No content found in ChromaDB for {chapter_id}")
            logger.error(f"   Searched for: Class {class_num}, Subject: {subject}, Chapter: {chapter_name}")
            return {"success": False, "error": "No content in ChromaDB"}
        
        # Extract chapter content
        documents = results["documents"][0]
        metadatas = results.get("metadatas", [[]])[0]
        
        # Verify we got content from the right chapter
        if metadatas:
            logger.info(f"📚 Retrieved from: {metadatas[0].get('class')} - {metadatas[0].get('subject')} - {metadatas[0].get('chapter')}")
        
        # Combine content
        chapter_content = "\n\n".join(documents)  # Use all retrieved chunks
        logger.info(f"✅ Retrieved {len(documents)} chunks from ChromaDB, {len(chapter_content)} chars")
        
        # 2. Create or get QuizChapter
        quiz_chapter, created = QuizChapter.objects.get_or_create(
            chapter_id=chapter_id,
            defaults={
                'class_number': class_num,
                'subject': subject,
                'chapter_number': chapter_order,
                'chapter_name': chapter_name,
                'chapter_order': chapter_order,
                'total_questions': 10,
                'passing_percentage': 70
            }
        )
        
        if not created:
            logger.info(f"📚 Quiz already exists for {chapter_id}, regenerating questions...")
            # Delete old questions to regenerate
            quiz_chapter.questions.all().delete()
        
        # 3. Generate questions using AI
        logger.info(f"🤖 Generating 10 MCQ questions using AI...")
        questions_data = generate_mcq_questions_with_ai(chapter_content, chapter_name, class_num)
        
        if not questions_data:
            logger.error("❌ AI failed to generate questions")
            return {"success": False, "error": "AI generation failed"}
        
        # 4. Create QuizQuestion and QuestionVariant records
        created_count = 0
        for q_num, q_data in enumerate(questions_data, 1):
            # Create base question
            quiz_question = QuizQuestion.objects.create(
                chapter=quiz_chapter,
                question_number=q_num,
                topic=q_data.get('topic', 'General'),
                difficulty=q_data.get('difficulty', 'medium'),
                rag_context=q_data.get('rag_context', chapter_content[:500])
            )
            
            # Create variants (3 variants per question)
            for variant_num, variant_data in enumerate(q_data.get('variants', []), 1):
                QuestionVariant.objects.create(
                    question=quiz_question,
                    variant_number=variant_num,
                    question_text=variant_data['question'],
                    option_a=variant_data['options']['A'],
                    option_b=variant_data['options']['B'],
                    option_c=variant_data['options']['C'],
                    option_d=variant_data['options']['D'],
                    correct_answer=variant_data['correct'],
                    explanation=variant_data['explanation']
                )
                created_count += 1
        
        logger.info(f"✅ Successfully created {created_count} question variants for {chapter_id}")
        
        return {
            "success": True,
            "chapter_id": chapter_id,
            "total_questions": 10,
            "total_variants": created_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating quiz for {chapter_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def generate_mcq_questions_with_ai(content: str, chapter_name: str, class_num: str, num_questions: int = 10) -> List[Dict]:
    """
    Use AI to generate MCQ questions with 5 variants each
    Age-appropriate for the student's class level
    
    Args:
        content: Chapter content from vector DB
        chapter_name: Name of the chapter
        class_num: Class number (e.g., "5")
        num_questions: Number of questions to generate (default: 10)
    """
    try:
        # Initialize AI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        
        # Age-appropriate language based on class
        class_number = int(''.join(filter(str.isdigit, str(class_num))))
        if class_number <= 5:
            language_level = "very simple, clear language suitable for 10-11 year old children"
            difficulty_mix = "5 easy, 4 medium, 1 hard"
        elif class_number <= 8:
            language_level = "moderate language suitable for 12-14 year old students"
            difficulty_mix = "3 easy, 5 medium, 2 hard"
        else:
            language_level = "advanced language suitable for 15+ year old students"
            difficulty_mix = "2 easy, 5 medium, 3 hard"
        
        # Prompt for question generation
        prompt = f"""You are an educational assessment expert creating quiz questions from NCERT textbooks for {class_num} students.

CHAPTER: {chapter_name} (Class {class_num})

CHAPTER CONTENT:
{content[:4000]}

TASK: Generate EXACTLY {num_questions} multiple-choice questions (MCQs) with 5 variants each.

IMPORTANT REQUIREMENTS:
1. Use {language_level} - students are around {10 + class_number} years old
2. Each question should test understanding of key concepts from the content
3. Create EXACTLY 5 VARIANTS of each question (same concept, different wording)
4. Each MCQ must have exactly 4 options (A, B, C, D)
5. Only ONE correct answer per question
6. EXPLANATIONS: Keep explanations SHORT (2-3 sentences max), simple, and in plain text without any markdown formatting (no *, #, **, etc.)
7. Difficulty distribution: {difficulty_mix}
8. Cover different topics within the chapter
9. Avoid overly complex vocabulary or concepts beyond the class level
10. Make questions engaging and interesting for young learners

EXPLANATION STYLE EXAMPLES:
✅ GOOD: "The correct answer is A because water freezes at 0°C. When water gets very cold, it turns into ice."
❌ BAD: "**Water freezes at 0 degrees Celsius.** This is a fundamental property of water. *When temperature drops below freezing point*, the molecular structure changes and water transforms into a solid state known as ice..."

EXAMPLE GOOD QUESTIONS FOR CLASS 5:
Easy: "What happens to water when it gets very cold?" (Simple recall)
Medium: "Why do leaves fall from trees in autumn?" (Understanding)
Hard: "If you see clouds forming in the sky, what will most likely happen next?" (Application)

OUTPUT FORMAT (STRICT JSON):
[
  {{
    "topic": "Topic name from content",
    "difficulty": "easy|medium|hard",
    "rag_context": "Direct quote from content that supports this question",
    "variants": [
      {{
        "question": "Clear, simple question for {class_num} students?",
        "options": {{
          "A": "First option",
          "B": "Second option",
          "C": "Third option",
          "D": "Fourth option"
        }},
        "correct": "A",
        "explanation": "Simple explanation why A is correct, referring to the content"
      }},
      {{
        "question": "Same concept as variant 1, different wording?",
        "options": {{
          "A": "Different first option",
          "B": "Different second option",
          "C": "Different third option",
          "D": "Different fourth option"
        }},
        "correct": "B",
        "explanation": "Explanation for variant 2"
      }},
      {{
        "question": "Third way to ask the same concept?",
        "options": {{
          "A": "Another first option",
          "B": "Another second option",
          "C": "Another third option",
          "D": "Another fourth option"
        }},
        "correct": "C",
        "explanation": "Explanation for variant 3"
      }},
      {{
        "question": "Fourth variant of the same concept?",
        "options": {{
          "A": "Fourth first option",
          "B": "Fourth second option",
          "C": "Fourth third option",
          "D": "Fourth fourth option"
        }},
        "correct": "D",
        "explanation": "Explanation for variant 4"
      }},
      {{
        "question": "Fifth variant of the same concept?",
        "options": {{
          "A": "Fifth first option",
          "B": "Fifth second option",
          "C": "Fifth third option",
          "D": "Fifth fourth option"
        }},
        "correct": "A",
        "explanation": "Explanation for variant 5"
      }}
    ]
  }},
  ... (continue for all {num_questions} questions)
]

⚠️ CRITICAL: Return ONLY valid JSON. No markdown, no comments, proper quotes, no trailing commas.
Generate EXACTLY {num_questions} questions. Return ONLY the JSON array, no other text."""

        # Use Gemini with retry
        result_text = None
        max_retries = 2
        
        if gemini_api_key:
            for attempt in range(max_retries):
                try:
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            'temperature': 0.3,
                            'top_p': 0.8,
                        }
                    )
                    result_text = response.text
                    logger.info(f"✅ Gemini generated quiz questions (attempt {attempt + 1})")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Gemini attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"❌ All Gemini attempts failed")
                        return []
        
        if not result_text:
            logger.error("❌ AI model unavailable")
            return []
        
        # Parse JSON response with error recovery
        import json
        result_text = result_text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()
        
        questions_data = None
        try:
            questions_data = json.loads(result_text)
            logger.info(f"✅ Parsed {len(questions_data)} questions")
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON parse error: {e.msg} at line {e.lineno}")
            # Try to fix common issues
            fixed_text = result_text
            fixed_text = re.sub(r',(\s*[}\]])', r'\1', fixed_text)  # Remove trailing commas
            fixed_text = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed_text)  # Quote keys
            try:
                questions_data = json.loads(fixed_text)
                logger.info(f"✅ Fixed and parsed {len(questions_data)} questions")
            except:
                logger.error(f"❌ Could not fix JSON, returning empty")
                return []
        
        if not questions_data:
            return []
        
        # Validate we have requested number of questions
        if len(questions_data) < num_questions:
            logger.warning(f"⚠️ Only {len(questions_data)} questions generated, expected {num_questions}")
        
        return questions_data[:num_questions]  # Take first num_questions
        
    except Exception as e:
        logger.error(f"❌ Error in AI question generation: {e}")
        import traceback
        traceback.print_exc()
        return None


def scan_and_generate_quizzes_for_existing_content():
    """
    Scan ChromaDB for existing content and generate quizzes
    Run this to generate quizzes for already uploaded books
    """
    from ncert_project.chromadb_utils import get_chromadb_manager
    
    try:
        chroma_manager = get_chromadb_manager()
        
        # Get available classes and subjects
        classes = chroma_manager.get_available_classes()
        
        logger.info(f"📚 Found {len(classes)} classes in ChromaDB")
        
        results = []
        for class_num in classes:
            subjects = chroma_manager.get_subjects_by_class(class_num)
            logger.info(f"  Class {class_num}: {len(subjects)} subjects")
            
            for subject in subjects:
                chapters = chroma_manager.get_chapters_by_class_subject(class_num, subject)
                logger.info(f"    {subject}: {len(chapters)} chapters")
                
                for chapter_num, chapter_name in enumerate(chapters, 1):
                    chapter_id = f"class_{class_num}_subject_{subject.replace(' ', '_').lower()}_chapter_{chapter_num}"
                    
                    logger.info(f"🎯 Generating quiz for: {chapter_id}")
                    result = generate_quiz_from_chromadb(
                        chapter_id=chapter_id,
                        class_num=class_num,
                        subject=subject,
                        chapter_name=chapter_name,
                        chapter_order=chapter_num
                    )
                    results.append(result)
        
        # Summary
        success_count = sum(1 for r in results if r.get('success'))
        logger.info(f"✅ Quiz generation complete: {success_count}/{len(results)} successful")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Error scanning ChromaDB: {e}")
        import traceback
        traceback.print_exc()
        return []
