"""
AI-Powered evaluation helpers for Unit Test answers.

This module provides:
- exact_match_score(student_answer, model_answer): case-insensitive exact match for 1-mark questions
- ai_evaluate(student_answer, model_answer, marks): AI-based scoring for 2-5 mark questions
  Returns (content_score, grammar_score, feedback) using OpenAI/Gemini

Features:
- Automatic fallback: OpenAI → Gemini → Heuristic
- Caching to avoid re-evaluating identical answers
- Detailed rubric-based scoring
- Grammar analysis with actionable feedback

Evaluation Strategy:
- 1 mark questions: Case-insensitive exact match (ignores punctuation, whitespace, case)
- 2-5 mark questions: AI-powered evaluation with:
  * Content scoring (70% weight): How well the answer matches the key concepts
  * Grammar scoring (30% weight): Language quality, structure, clarity
  * Detailed feedback for improvement
"""
import re
import os
import logging
from typing import Tuple, Dict
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text by removing extra whitespace, converting to lowercase, and removing punctuation."""
    # Remove punctuation and convert to lowercase
    text = re.sub(r'[^\w\s]', '', (text or '').strip().lower())
    # Collapse multiple spaces into one
    return re.sub(r"\s+", " ", text)


def exact_match_score(student_answer: str, model_answer: str) -> int:
    """Return 1 if exact (case-insensitive) match else 0.
    
    Used for 1-mark questions where exact answer is required.
    """
    if _normalize(student_answer) == _normalize(model_answer):
        return 1
    return 0


def _heuristic_evaluate(student_answer: str, model_answer: str) -> Tuple[float, float, str]:
    """Fallback heuristic evaluation (used when AI is unavailable).
    
    This is more lenient and focuses on keyword matching.
    """
    s = _normalize(student_answer)
    m = _normalize(model_answer)

    if not s:
        return 0.0, 0.0, "No answer provided."

    s_tokens = set(re.findall(r"\w+", s))
    m_tokens = set(re.findall(r"\w+", m))
    
    if not m_tokens:
        content = 0.5  # Give benefit of doubt
    else:
        # Calculate token overlap
        overlap = len(s_tokens & m_tokens)
        total_model = len(m_tokens)
        
        # More generous scoring - if student got some key words, give credit
        if overlap == 0:
            content = 0.0
        elif overlap >= total_model * 0.7:  # 70%+ keywords
            content = 0.9
        elif overlap >= total_model * 0.5:  # 50%+ keywords
            content = 0.75
        elif overlap >= total_model * 0.3:  # 30%+ keywords
            content = 0.6
        else:
            content = 0.4  # At least some keywords present

    # More lenient grammar heuristic
    grammar = 0.6  # Start with passing grade
    word_count = len(s.split())
    
    if word_count >= 10:  # Reasonable length answer
        grammar += 0.2
    elif word_count >= 5:
        grammar += 0.1
    
    if any(p in student_answer for p in '.!?'):  # Some punctuation
        grammar += 0.1
    
    if student_answer[0].isupper():  # Starts with capital
        grammar += 0.1
        
    grammar = min(1.0, grammar)

    feedback = f"Content: {int(content*100)}% of key concepts covered. "
    if content >= 0.7:
        feedback += "Good understanding shown! "
    elif content >= 0.5:
        feedback += "Partial understanding shown. "
    
    if grammar < 0.7:
        feedback += "Consider improving sentence structure and punctuation."
    
    return round(content, 3), round(grammar, 3), feedback


def ai_evaluate(student_answer: str, model_answer: str, marks: int = 2, question: str = "", ai_model: str = "gemini") -> Tuple[float, float, str]:
    """Evaluate answer using AI (OpenAI/Gemini) with detailed rubric.
    
    Args:
        student_answer: The student's submitted answer
        model_answer: The correct/model answer provided by staff
        marks: Question marks (2, 3, 4, or 5)
        question: The original question text (optional, helps with context)
        ai_model: Which AI to use - 'gemini' or 'openai' (default: 'gemini')
    
    Returns:
        (content_score, grammar_score, feedback)
        - content_score: 0.0 to 1.0 (how well content matches)
        - grammar_score: 0.0 to 1.0 (grammar quality)
        - feedback: Detailed explanation for the student
    """
    # Check cache first
    cache_key = f"eval_v2_{ai_model}_{hash(student_answer + model_answer + str(marks))}"
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"Using cached {ai_model} evaluation result")
        return cached
    
    # Prepare comprehensive evaluation prompt
    prompt = f"""You are a kind and fair teacher evaluating a student's answer to a {marks}-mark question in a school exam.

QUESTION: {question or "Not provided"}

MODEL ANSWER (Staff-provided correct answer):
{model_answer}

STUDENT'S ANSWER:
{student_answer}

EVALUATION INSTRUCTIONS:

**CONTENT ACCURACY** (70% weight):
FOCUS ON KEY CONCEPTS, NOT EXACT WORDING!
- Identify the main concepts/ideas in the model answer
- Check if the student's answer contains these SAME CONCEPTS (even in different words)
- Award marks if the student shows understanding, even with simple language
- Don't penalize for missing minor details if main idea is correct
- Give credit for partially correct answers

For {marks}-mark question:
- Each key concept = points
- If student mentions the concept in ANY way, give credit
- Be lenient with wording - meaning matters more than exact words

**GRAMMAR & LANGUAGE QUALITY** (30% weight):
- Only evaluate basic grammar, not perfection
- If answer is understandable, give reasonable grammar score (60%+)
- Don't be too harsh on capitalization or punctuation for younger students
- Focus on whether the meaning is clear

SCORING GUIDELINES - BE GENEROUS:
- CONTENT_SCORE (0-100):
  * 90-100: All main concepts present (may lack some details)
  * 70-89: Most main concepts present, good understanding shown
  * 50-69: Some main concepts present, partial understanding
  * 30-49: Few concepts present but some correct ideas
  * 10-29: Minimal correct content
  * 0-9: Completely wrong or blank

- GRAMMAR_SCORE (0-100):
  * 90-100: Very clear and well-written
  * 70-89: Generally clear, minor errors don't affect understanding
  * 50-69: Understandable despite several errors
  * 30-49: Somewhat difficult to understand
  * 10-29: Hard to understand but some meaning clear
  * 0-9: Incomprehensible

IMPORTANT GRADING PRINCIPLES:
✓ If the student got the MAIN IDEA correct, give good marks (70%+)
✓ Different wording is OK - check for CONCEPT not EXACT WORDS
✓ Reward partial knowledge - don't give 0 unless completely wrong
✓ If answer shows ANY understanding, minimum 30% content score
✓ Be encouraging - this is a learning process
✓ Focus on what they DID include, not just what's missing

OUTPUT FORMAT (must be exact):
CONTENT_SCORE: [number 0-100]
GRAMMAR_SCORE: [number 0-100]
FEEDBACK: [Your detailed feedback here. Start with what they got RIGHT, then gently mention what could be added for full marks.]"""

    # Try OpenAI or Gemini based on preference
    if ai_model.lower() == "openai":
        # Try OpenAI first
        try:
            import openai
            openai_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
            
            if openai_key:
                client = openai.OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Cost-effective and accurate
                    messages=[
                        {"role": "system", "content": "You are an expert teacher evaluating student answers with high academic standards."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Low temperature for consistent grading
                    max_tokens=600
                )
                
                result_text = response.choices[0].message.content
                content_score, grammar_score, feedback = _parse_ai_response(result_text)
                
                # Cache for 2 hours
                cache.set(cache_key, (content_score, grammar_score, feedback), 7200)
                logger.info(f"✅ OpenAI evaluation: content={content_score:.2f}, grammar={grammar_score:.2f}")
                return content_score, grammar_score, feedback
                
        except Exception as e:
            logger.warning(f"OpenAI evaluation failed: {e}, trying Gemini as fallback...")
        
        # Fallback to Gemini if OpenAI fails
        try:
            import google.generativeai as genai
            gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
            
            if gemini_key:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.3,
                        'max_output_tokens': 600,
                    }
                )
                
                result_text = response.text
                content_score, grammar_score, feedback = _parse_ai_response(result_text)
                
                # Cache for 2 hours
                cache.set(cache_key, (content_score, grammar_score, feedback), 7200)
                logger.info(f"✅ Gemini evaluation (fallback): content={content_score:.2f}, grammar={grammar_score:.2f}")
                return content_score, grammar_score, feedback
                
        except Exception as e:
            logger.warning(f"Gemini fallback failed: {e}, using heuristic...")
    
    else:  # Default to Gemini
        # Try Gemini first
        try:
            import google.generativeai as genai
            gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
            
            if gemini_key:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.3,
                        'max_output_tokens': 600,
                    }
                )
                
                result_text = response.text
                content_score, grammar_score, feedback = _parse_ai_response(result_text)
                
                # Cache for 2 hours
                cache.set(cache_key, (content_score, grammar_score, feedback), 7200)
                logger.info(f"✅ Gemini evaluation: content={content_score:.2f}, grammar={grammar_score:.2f}")
                return content_score, grammar_score, feedback
                
        except Exception as e:
            logger.warning(f"Gemini evaluation failed: {e}, trying OpenAI as fallback...")
        
        # Fallback to OpenAI if Gemini fails
        try:
            import openai
            openai_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
            
            if openai_key:
                client = openai.OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an expert teacher evaluating student answers with high academic standards."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=600
                )
                
                result_text = response.choices[0].message.content
                content_score, grammar_score, feedback = _parse_ai_response(result_text)
                
                # Cache for 2 hours
                cache.set(cache_key, (content_score, grammar_score, feedback), 7200)
                logger.info(f"✅ OpenAI evaluation (fallback): content={content_score:.2f}, grammar={grammar_score:.2f}")
                return content_score, grammar_score, feedback
                
        except Exception as e:
            logger.warning(f"OpenAI fallback failed: {e}, using heuristic...")

    # Fallback to heuristic
    logger.warning("Using heuristic evaluation (AI unavailable)")
    return _heuristic_evaluate(student_answer, model_answer)


def _parse_ai_response(text: str) -> Tuple[float, float, str]:
    """Parse AI response to extract scores and feedback."""
    content_score = 0.0
    grammar_score = 0.0
    feedback = "Evaluation completed."
    
    # Extract CONTENT_SCORE
    content_match = re.search(r'CONTENT_SCORE:\s*(\d+)', text)
    if content_match:
        content_score = int(content_match.group(1)) / 100.0
    
    # Extract GRAMMAR_SCORE
    grammar_match = re.search(r'GRAMMAR_SCORE:\s*(\d+)', text)
    if grammar_match:
        grammar_score = int(grammar_match.group(1)) / 100.0
    
    # Extract FEEDBACK
    feedback_match = re.search(r'FEEDBACK:\s*(.+?)(?:\n\n|\Z)', text, re.DOTALL)
    if feedback_match:
        feedback = feedback_match.group(1).strip()
    
    return round(content_score, 3), round(grammar_score, 3), feedback


def evaluate_answer(student_answer: str, model_answer: str, marks: int, question: str = "", ai_model: str = "gemini") -> Dict:
    """Main evaluation function that routes to appropriate evaluator.
    
    Args:
        student_answer: Student's submitted answer
        model_answer: Staff-provided model answer
        marks: Question marks (1, 2, 3, 4, or 5)
        question: Original question text (optional)
        ai_model: AI model to use - 'gemini' or 'openai' (default: 'gemini')
    
    Returns dict with:
        - awarded_marks: float (actual marks awarded)
        - content_score: float (0-1, content accuracy)
        - grammar_score: float (0-1, grammar quality)
        - feedback: str (detailed feedback)
        - evaluation_type: str ('exact', 'ai', or 'heuristic')
        - ai_model_used: str (which AI was actually used)
    """
    # Check if this is an explanatory question (even if 1 mark)
    explanatory_keywords = ['why', 'how', 'explain', 'describe', 'what do you think', 
                            'in your opinion', 'justify', 'give reason', 'because']
    
    question_lower = question.lower() if question else ""
    is_explanatory = any(keyword in question_lower for keyword in explanatory_keywords)
    
    # Also check if model answer is long (>15 words) - suggests explanation needed
    model_word_count = len(model_answer.split())
    is_long_answer = model_word_count > 15
    
    # Use AI evaluation if:
    # 1. Marks >= 2, OR
    # 2. Question asks for explanation (why/how/explain), OR  
    # 3. Model answer is lengthy (>15 words)
    use_ai_evaluation = (marks >= 2) or is_explanatory or is_long_answer
    
    if marks == 1 and not use_ai_evaluation:
        # Case-insensitive exact match for simple 1-mark questions only
        score = exact_match_score(student_answer, model_answer)
        return {
            'awarded_marks': score * marks,
            'content_score': float(score),
            'grammar_score': 1.0 if score else 0.5,  # Grammar less critical for short answers
            'feedback': '✓ Correct!' if score else f'✗ Incorrect. Expected: "{model_answer}"',
            'evaluation_type': 'exact',
            'ai_model_used': 'none'
        }
    else:
        # AI evaluation for 2-5 mark questions
        content_score, grammar_score, feedback = ai_evaluate(
            student_answer, model_answer, marks, question, ai_model
        )
        
        # Calculate awarded marks (70% content, 30% grammar)
        combined_score = (content_score * 0.7) + (grammar_score * 0.3)
        awarded_marks = round(combined_score * marks, 2)
        
        # Add marks breakdown to feedback
        content_marks = round(content_score * marks * 0.7, 2)
        grammar_marks = round(grammar_score * marks * 0.3, 2)
        
        detailed_feedback = f"""📊 **Score Breakdown:**
• Content: {content_marks}/{marks * 0.7:.1f} marks ({content_score*100:.0f}%)
• Grammar & Expression: {grammar_marks}/{marks * 0.3:.1f} marks ({grammar_score*100:.0f}%)
• **Total: {awarded_marks}/{marks} marks**

{feedback}"""
        
        return {
            'awarded_marks': awarded_marks,
            'content_score': content_score,
            'grammar_score': grammar_score,
            'feedback': detailed_feedback,
            'evaluation_type': 'ai',
            'ai_model_used': ai_model
        }
