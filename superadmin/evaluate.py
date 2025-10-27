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
"""
import re
import os
import logging
from typing import Tuple, Dict
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or '').strip().lower())


def exact_match_score(student_answer: str, model_answer: str) -> int:
    """Return 1 if exact (case-insensitive) match else 0.
    
    Used for 1-mark questions where exact answer is required.
    """
    if _normalize(student_answer) == _normalize(model_answer):
        return 1
    return 0


def _heuristic_evaluate(student_answer: str, model_answer: str) -> Tuple[float, float, str]:
    """Fallback heuristic evaluation (used when AI is unavailable)."""
    s = _normalize(student_answer)
    m = _normalize(model_answer)

    if not s:
        return 0.0, 0.0, "No answer provided."

    s_tokens = set(re.findall(r"\w+", s))
    m_tokens = set(re.findall(r"\w+", m))
    
    if not m_tokens:
        content = 0.0
    else:
        content = len(s_tokens & m_tokens) / max(1, len(m_tokens))

    # Grammar heuristic
    grammar = 0.5
    if len(s.split()) >= 6:
        grammar += 0.3
    if any(p in student_answer for p in '.!?'):
        grammar += 0.2
    grammar = min(1.0, grammar)

    feedback = f"Content coverage: {int(content*100)}%. "
    if grammar < 0.7:
        feedback += "Consider improving sentence structure and punctuation."
    
    return round(content, 3), round(grammar, 3), feedback


def ai_evaluate(student_answer: str, model_answer: str, marks: int = 2, question: str = "") -> Tuple[float, float, str]:
    """Evaluate answer using AI (OpenAI/Gemini) with detailed rubric.
    
    Args:
        student_answer: The student's submitted answer
        model_answer: The correct/model answer
        marks: Question marks (2, 3, 4, or 5)
        question: The original question text (optional, helps with context)
    
    Returns:
        (content_score, grammar_score, feedback)
        - content_score: 0.0 to 1.0 (how well content matches)
        - grammar_score: 0.0 to 1.0 (grammar quality)
        - feedback: Detailed explanation for the student
    """
    # Check cache first
    cache_key = f"eval_{hash(student_answer + model_answer)}"
    cached = cache.get(cache_key)
    if cached:
        logger.info("Using cached evaluation result")
        return cached
    
    # Prepare evaluation prompt
    prompt = f"""You are an expert teacher evaluating a student's answer to a {marks}-mark question.

QUESTION: {question or "Not provided"}

MODEL ANSWER (What we expect):
{model_answer}

STUDENT'S ANSWER:
{student_answer}

EVALUATION RUBRIC:
1. CONTENT ACCURACY (0-100%):
   - Does the answer cover the key concepts from the model answer?
   - Are the facts correct?
   - Is the explanation complete?

2. GRAMMAR & EXPRESSION (0-100%):
   - Proper sentence structure
   - Correct punctuation and capitalization
   - Clear and coherent expression
   - Appropriate vocabulary

Please provide your evaluation in EXACTLY this format:

CONTENT_SCORE: [0-100]
GRAMMAR_SCORE: [0-100]
FEEDBACK: [Detailed feedback for the student: what they did well, what they missed, and specific suggestions for improvement]

Be fair but strict. Award full marks only for excellent answers."""

    # Try OpenAI first
    try:
        import openai
        openai_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
        
        if openai_key:
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Cost-effective and accurate
                messages=[
                    {"role": "system", "content": "You are an expert teacher evaluating student answers."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Low temperature for consistent grading
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content
            content_score, grammar_score, feedback = _parse_ai_response(result_text)
            
            # Cache for 1 hour
            cache.set(cache_key, (content_score, grammar_score, feedback), 3600)
            logger.info(f"OpenAI evaluation: content={content_score}, grammar={grammar_score}")
            return content_score, grammar_score, feedback
            
    except Exception as e:
        logger.warning(f"OpenAI evaluation failed: {e}, trying Gemini...")
    
    # Try Gemini as fallback
    try:
        import google.generativeai as genai
        gemini_key = getattr(settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
        
        if gemini_key:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            
            result_text = response.text
            content_score, grammar_score, feedback = _parse_ai_response(result_text)
            
            # Cache for 1 hour
            cache.set(cache_key, (content_score, grammar_score, feedback), 3600)
            logger.info(f"Gemini evaluation: content={content_score}, grammar={grammar_score}")
            return content_score, grammar_score, feedback
            
    except Exception as e:
        logger.warning(f"Gemini evaluation failed: {e}, using heuristic fallback...")
    
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


def evaluate_answer(student_answer: str, model_answer: str, marks: int, question: str = "") -> Dict:
    """Main evaluation function that routes to appropriate evaluator.
    
    Returns dict with:
        - awarded_marks: float
        - content_score: float (0-1)
        - grammar_score: float (0-1)
        - feedback: str
        - evaluation_type: str ('exact', 'ai', 'heuristic')
    """
    if marks == 1:
        # Exact match for 1-mark questions
        score = exact_match_score(student_answer, model_answer)
        return {
            'awarded_marks': score * marks,
            'content_score': float(score),
            'grammar_score': 1.0 if score else 0.0,
            'feedback': 'Correct!' if score else 'Incorrect. Expected exact match.',
            'evaluation_type': 'exact'
        }
    else:
        # AI evaluation for 2-5 mark questions
        content_score, grammar_score, feedback = ai_evaluate(
            student_answer, model_answer, marks, question
        )
        
        # Calculate awarded marks (70% content, 30% grammar)
        combined_score = (content_score * 0.7) + (grammar_score * 0.3)
        awarded_marks = round(combined_score * marks, 2)
        
        return {
            'awarded_marks': awarded_marks,
            'content_score': content_score,
            'grammar_score': grammar_score,
            'feedback': feedback,
            'evaluation_type': 'ai'
        }
