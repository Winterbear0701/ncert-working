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
    Extract questions from textbook special sections
    - Let us reflect
    - Activity sections
    - Do you know
    - Discuss / Let's discuss
    - End-of-chapter questions
    These are high-quality questions already in the book
    """
    questions = []
    
    # Comprehensive patterns for all NCERT question sections (Class 5-10)
    patterns = [
        # Primary reflection sections
        r'Let us reflect[:\s]*(.*?)(?=\n\n|\Z)',
        r'Let Us Reflect[:\s]*(.*?)(?=\n\n|\Z)',
        
        # Activity sections
        r'Activity[:\s]*(.*?)(?=\n\n|\Z)',
        r'ACTIVITY[:\s]*(.*?)(?=\n\n|\Z)',
        
        # Discussion prompts
        r'Do you know[:\s\?]*(.*?)(?=\n\n|\Z)',
        r'Do You Know[:\s\?]*(.*?)(?=\n\n|\Z)',
        r'Discuss[:\s]*(.*?)(?=\n\n|\Z)',
        r'Let\'s discuss[:\s]*(.*?)(?=\n\n|\Z)',
        r'Let us discuss[:\s]*(.*?)(?=\n\n|\Z)',
        
        # Standard question sections
        r'Think and Answer[:\s]*(.*?)(?=\n\n|\Z)',
        r'Check your progress[:\s]*(.*?)(?=\n\n|\Z)',
        r'Questions[:\s]*(.*?)(?=\n\n|\Z)',
        r'Exercise[:\s]*(.*?)(?=\n\n|\Z)',
        r'EXERCISE[:\s]*(.*?)(?=\n\n|\Z)',
        
        # End-of-chapter sections
        r'Review Questions[:\s]*(.*?)(?=\n\n|\Z)',
        r'Chapter Review[:\s]*(.*?)(?=\n\n|\Z)',
        r'Summary Questions[:\s]*(.*?)(?=\n\n|\Z)',
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
        
        # Prepare questions for AI - EXACTLY 10 questions needed
        questions_text = "\n".join([f"{i+1}. {q['text']}" for i, q in enumerate(textbook_questions[:10])])
        
        prompt = f"""You are converting textbook reflection questions into MCQs for Class {class_num} students.

TEXTBOOK QUESTIONS (from "Let us reflect", "Activity", "Discuss", "Do you know" sections):
{questions_text}

CHAPTER CONTENT (includes OCR-extracted text from diagrams, maps, charts):
{content[:3000]}

TASK: Convert EACH question into a 4-option MCQ with EXACTLY 5 variants.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY 10 QUESTIONS (if textbook has fewer, create content-based questions to reach 10)
2. Each question MUST have EXACTLY 5 VARIANTS (different wording, same concept)
3. Use {language_level}
4. Keep the original question's intent and difficulty
5. Create exactly 4 options (A, B, C, D) per question
6. Extract relevant RAG context from the content
7. Mix difficulty: label as easy/medium/hard based on original question complexity
8. EXPLANATIONS: Keep SHORT (2-3 sentences max), simple, plain text - NO markdown (no *, #, **, _)
9. **IMPORTANT**: Consider image content (diagrams, maps, charts) extracted via OCR - create visual/diagram-based questions too

IMAGE-BASED QUESTION TYPES (if content has diagrams):
- "Based on the diagram, what is a dune?"
- "According to the rivers map, which landform is formed by wind?"
- "Looking at the water cycle chart, where does evaporation occur?"

EXPLANATION RULES:
[OK] GOOD: "The answer is B because rivers flow from mountains to the sea. Water always moves downward due to gravity."
[ERROR] BAD: "**Rivers flow from mountains to the sea.** This is because of *gravity* which pulls water downward. Rivers start high up..."

OUTPUT FORMAT (JSON) - MUST return array with exactly 10 questions:
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
      }},
      {{
        "question": "Variant 4 wording?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "D",
        "explanation": "Explanation for variant 4"
      }},
      {{
        "question": "Variant 5 wording?",
        "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
        "correct": "B",
        "explanation": "Explanation for variant 5"
      }}
    ]
  }},
  ... (repeat for all 10 questions - total of 10 questions × 5 variants = 50 total variants)
]

IMPORTANT: You MUST return exactly 10 questions. If textbook has less than 10 "Let us reflect" questions, create additional questions from the chapter content to reach exactly 10 questions.

[WARNING]  CRITICAL JSON FORMATTING:
1. Use ONLY double quotes (") - NO single quotes (')
2. NO trailing commas before closing brackets
3. Escape special characters in text (use \\" for quotes inside strings)
4. NO comments (// or /* */)
5. Ensure all brackets are properly closed
6. Test your JSON is valid before returning

Return ONLY the JSON array - no markdown, no extra text."""
        
        # Use Gemini with retry logic
        result_text = None
        max_retries = 3
        
        if gemini_api_key:
            for attempt in range(max_retries):
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            'temperature': 0.3 if attempt == 0 else 0.1,  # Lower temp on retry
                            'top_p': 0.8,
                            'top_k': 40,
                        }
                    )
                    result_text = response.text
                    logger.info(f"[OK] Gemini converted textbook questions to MCQs (attempt {attempt + 1})")
                    break  # Success, exit retry loop
                except Exception as e:
                    logger.warning(f"[WARNING]  Gemini attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"[ERROR] All Gemini attempts failed")
                        return []
                    import time
                    time.sleep(1)  # Brief pause before retry
        
        if not result_text:
            logger.error("[ERROR] No AI service available")
            return []
        
        # Parse JSON
        result_text = result_text.strip()
        if result_text.startswith('```json'):
            result_text = result_text[7:]
        if result_text.startswith('```'):
            result_text = result_text[3:]
        if result_text.endswith('```'):
            result_text = result_text[:-3]
        result_text = result_text.strip()
        
        # Try to parse JSON with error recovery
        questions = None
        try:
            questions = json.loads(result_text)
            logger.info(f"[OK] Generated {len(questions)} MCQs from textbook questions")
        except json.JSONDecodeError as e:
            logger.warning(f"[WARNING]  JSON parse error at line {e.lineno}: {e.msg}")
            logger.warning(f"   Error position: char {e.pos}")
            # Log the problematic section (100 chars around error)
            error_start = max(0, e.pos - 50)
            error_end = min(len(result_text), e.pos + 50)
            logger.warning(f"   Context: ...{result_text[error_start:error_end]}...")
            logger.warning(f"   Attempting to fix malformed JSON...")
            
            # Common JSON fixes
            fixed_text = result_text
            
            # Fix trailing commas
            fixed_text = re.sub(r',(\s*[}\]])', r'\1', fixed_text)
            
            # Fix unquoted property names
            fixed_text = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed_text)
            
            # Fix single quotes to double quotes
            fixed_text = fixed_text.replace("'", '"')
            
            # Remove comments
            fixed_text = re.sub(r'//.*?\n', '\n', fixed_text)
            fixed_text = re.sub(r'/\*.*?\*/', '', fixed_text, flags=re.DOTALL)
            
            # Try parsing fixed JSON
            try:
                questions = json.loads(fixed_text)
                logger.info(f"[OK] Fixed and parsed JSON: {len(questions)} questions")
            except json.JSONDecodeError as e2:
                logger.error(f"[ERROR] Could not fix JSON. Error: {e2}")
                
                # Last resort: Extract valid JSON portion
                try:
                    # Find the first [ and last ]
                    start_idx = fixed_text.find('[')
                    end_idx = fixed_text.rfind(']')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        truncated = fixed_text[start_idx:end_idx+1]
                        # Try to close any unclosed objects
                        open_braces = truncated.count('{') - truncated.count('}')
                        if open_braces > 0:
                            truncated = truncated.rstrip(',') + '}' * open_braces
                        questions = json.loads(truncated)
                        logger.info(f"[OK] Extracted partial JSON: {len(questions)} questions")
                except:
                    logger.error(f"[ERROR] All JSON repair attempts failed")
                    return []
        
        if not questions:
            return []
        
        return questions
        
    except Exception as e:
        logger.error(f"[ERROR] Error converting textbook questions: {e}")
        return []


def generate_quiz_with_textbook_questions(chapter_id: str, class_num: str, subject: str, chapter_name: str, chapter_order: int) -> Dict:
    """
    NEW APPROACH: Generate quizzes prioritizing textbook "Let us reflect" questions
    Falls back to AI generation if needed
    Uses Pinecone (production) or ChromaDB (local) via vector_db_utils
    """
    from ncert_project.vector_db_utils import get_vector_db_manager
    from students.models import QuizChapter, QuizQuestion, QuestionVariant
    
    try:
        # Get Vector DB manager (Pinecone in production, ChromaDB local)
        vector_manager = get_vector_db_manager()
        db_type = "Pinecone" if hasattr(vector_manager, 'index_name') else "ChromaDB"
        logger.info(f"[SEARCH] Fetching content from {db_type} for: {chapter_name} (Class {class_num}, {subject})")
        logger.info(f"   Parameters: class_num={class_num}, subject={subject}, chapter={chapter_name}")
        
        # Build specific query for this chapter - CRITICAL: Filter by chapter!
        query_text = f"{subject} {chapter_name} content summary questions"
        
        # IMPORTANT: Pass chapter parameter to filter results to ONLY this chapter
        results = vector_manager.query_by_class_subject_chapter(
            query_text=query_text,
            class_num=str(class_num),
            subject=subject,
            chapter=chapter_name,  # ← THIS IS CRITICAL! Filter by specific chapter
            n_results=50  # Get comprehensive content from THIS CHAPTER ONLY
        )
        
        logger.info(f"   Query returned: {len(results.get('documents', [[]])[0])} chunks")
        
        if not results or not results.get("documents") or not results["documents"][0]:
            logger.error(f"[ERROR] No content in {db_type} for {chapter_id}")
            logger.error(f"   Tried to find: Class {class_num}, Subject: {subject}, Chapter: {chapter_name}")
            return {"status": "error", "success": False, "error": f"No content in {db_type}"}
        
        # Combine all documents
        documents = results["documents"][0]
        metadatas = results.get("metadatas", [[]])[0]
        
        # Verify we got the right chapter content
        if metadatas:
            logger.info(f"[BOOK] Retrieved from {db_type}: {metadatas[0].get('class')} - {metadatas[0].get('subject')} - {metadatas[0].get('chapter')}")
        
        full_content = "\n\n".join(documents)
        
        logger.info(f"[DOC] Retrieved {len(documents)} chunks from {chapter_name}, total {len(full_content)} chars")
        
        # STEP 1: Extract "Let us reflect" questions
        textbook_questions = extract_let_us_reflect_questions(full_content)
        logger.info(f"[NOTE] Found {len(textbook_questions)} textbook reflection questions")
        
        # STEP 2: Convert to MCQs
        mcq_data = []
        if textbook_questions:
            mcq_data = generate_mcqs_from_textbook_questions(textbook_questions, full_content, class_num)
        
        # If textbook MCQ generation failed or no textbook questions, use fallback
        if not mcq_data:
            logger.warning("[WARNING] No MCQs from textbook questions, generating from content")
            # Fallback to regular AI generation
            try:
                from students.quiz_generator import generate_mcq_questions_with_ai
                mcq_data = generate_mcq_questions_with_ai(full_content, chapter_name, class_num)
            except Exception as fallback_err:
                logger.error(f"[ERROR] Fallback generation failed: {fallback_err}")
        
        if not mcq_data:
            logger.error("[ERROR] Failed to generate MCQs from all methods")
            return {"success": False, "error": "Failed to generate questions after all attempts"}
        
        # CRITICAL: Ensure EXACTLY 10 questions
        if len(mcq_data) < 10:
            logger.warning(f"[WARNING] Only {len(mcq_data)} questions generated, need exactly 10")
            # Generate additional questions to reach 10
            from students.quiz_generator import generate_mcq_questions_with_ai
            additional_needed = 10 - len(mcq_data)
            logger.info(f"🔄 Generating {additional_needed} additional questions from content...")
            additional_mcqs = generate_mcq_questions_with_ai(full_content, chapter_name, class_num, num_questions=additional_needed)
            if additional_mcqs:
                mcq_data.extend(additional_mcqs[:additional_needed])
        
        # Ensure exactly 10 questions (trim if more, keep all if less)
        if len(mcq_data) > 10:
            mcq_data = mcq_data[:10]
            logger.info(f"✂️ Trimmed to exactly 10 questions")
        
        logger.info(f"[STATS] Final question count: {len(mcq_data)} questions")
        
        # STEP 3: Create/update database records
        quiz_chapter, created = QuizChapter.objects.get_or_create(
            chapter_id=chapter_id,
            defaults={
                'class_number': f"Class {class_num}",
                'subject': subject,
                'chapter_number': chapter_order,
                'chapter_name': chapter_name,
                'chapter_order': chapter_order,
                'total_questions': 10,  # Always 10 questions
                'passing_percentage': 70,
                'is_active': True
            }
        )
        
        if not created:
            # Delete old questions
            QuizQuestion.objects.filter(chapter=quiz_chapter).delete()
            quiz_chapter.total_questions = 10  # Always 10 questions
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
        
        logger.info(f"[OK] Created quiz: {len(mcq_data)} questions × 3 variants = {len(mcq_data)*3} total variants")
        
        return {
            "status": "success",
            "success": True,
            "chapter_id": chapter_id,
            "total_questions": len(mcq_data),
            "questions_generated": len(mcq_data),
            "textbook_questions_used": len(textbook_questions)
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Quiz generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "success": False, "error": str(e), "message": str(e)}
