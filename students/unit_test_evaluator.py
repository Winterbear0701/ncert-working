"""
AI-Powered Unit Test Evaluator

This module evaluates student answers using the advanced AI evaluation system.
It integrates with superadmin.evaluate to provide:
- Case-insensitive exact matching for 1-mark questions (ignores punctuation, whitespace, case)
- AI-based content and grammar scoring for 2-5 mark questions
- Separate content score (70% weight) and grammar score (30% weight)
- Detailed feedback for each answer
- Support for both OpenAI and Gemini models
- Overall test statistics and feedback

Evaluation Strategy:
- 1-mark questions: Exact match (case-insensitive, punctuation ignored)
- 2-5 mark questions: 
  * Content accuracy: 70% of marks (based on model answer key points)
  * Grammar quality: 30% of marks (language structure, clarity, expression)
  * Detailed AI-generated feedback with improvement suggestions
"""
import logging
from django.utils import timezone
from typing import Dict, List
import os

logger = logging.getLogger(__name__)


class UnitTestEvaluator:
    """Evaluates unit test attempts using AI-powered evaluation."""
    
    def __init__(self, ai_model: str = "gemini"):
        """Initialize evaluator with preferred AI model.
        
        Args:
            ai_model: 'gemini' or 'openai' (default: 'gemini')
        """
        self.ai_model = ai_model.lower()
        if self.ai_model not in ['gemini', 'openai']:
            logger.warning(f"Invalid AI model '{ai_model}', defaulting to 'gemini'")
            self.ai_model = 'gemini'
    
    def evaluate_full_test(self, attempt_id: int, ai_model: str = None) -> Dict:
        """Evaluate all answers in a unit test attempt.
        
        Args:
            attempt_id: ID of the UnitTestAttempt to evaluate
            ai_model: Override AI model for this evaluation ('gemini' or 'openai')
                     If None, uses the evaluator's default model
        
        Returns:
            Dict with evaluation results and statistics
        """
        from students.models import UnitTestAttempt, UnitTestAnswer
        from superadmin.evaluate import evaluate_answer
        
        # Use specified model or fall back to instance default
        model_to_use = (ai_model or self.ai_model).lower()
        
        try:
            attempt = UnitTestAttempt.objects.get(id=attempt_id)
        except UnitTestAttempt.DoesNotExist:
            logger.error(f"UnitTestAttempt {attempt_id} not found")
            return {'success': False, 'error': 'Attempt not found'}
        
        logger.info(f"🔍 Evaluating unit test attempt {attempt_id} for {attempt.student.email}")
        logger.info(f"🤖 Using AI model: {model_to_use.upper()}")
        
        # Get all answers
        answers = UnitTestAnswer.objects.filter(attempt=attempt).select_related('question')
        
        total_marks = 0.0
        total_content = 0.0
        total_grammar = 0.0
        evaluated_count = 0
        feedback_parts = []
        
        # Track question type statistics
        one_mark_count = 0
        one_mark_correct = 0
        multi_mark_count = 0
        
        for answer_obj in answers:
            question = answer_obj.question
            student_answer = answer_obj.answer_text or ''
            model_answer = question.model_answer
            
            # Evaluate using AI with specified model
            result = evaluate_answer(
                student_answer=student_answer,
                model_answer=model_answer,
                marks=question.marks,
                question=question.question_text,
                ai_model=model_to_use
            )
            
            # Store evaluation in answer object
            answer_obj.awarded_marks = result['awarded_marks']
            answer_obj.content_score = result['content_score']
            answer_obj.grammar_score = result['grammar_score']
            answer_obj.ai_feedback = result['feedback']
            answer_obj.evaluation_type = result['evaluation_type']
            answer_obj.evaluation_model = result.get('ai_model_used', model_to_use)
            answer_obj.evaluated_at = timezone.now()
            answer_obj.save()
            
            # Accumulate stats
            total_marks += result['awarded_marks']
            total_content += result['content_score']
            total_grammar += result['grammar_score']
            evaluated_count += 1
            
            # Track question types
            if question.marks == 1:
                one_mark_count += 1
                if result['awarded_marks'] == 1:
                    one_mark_correct += 1
            else:
                multi_mark_count += 1
            
            logger.info(f"   Q{question.question_number} ({question.marks}m): "
                       f"{result['awarded_marks']:.2f}/{question.marks} marks "
                       f"(content: {result['content_score']*100:.0f}%, "
                       f"grammar: {result['grammar_score']*100:.0f}%) "
                       f"[{result['evaluation_type']}]")
        
        # Calculate averages
        avg_content = total_content / max(1, evaluated_count)
        avg_grammar = total_grammar / max(1, evaluated_count)
        
        # Update attempt with final scores
        attempt.total_marks_obtained = round(total_marks, 2)
        attempt.content_score = round(avg_content, 3)
        attempt.grammar_score = round(avg_grammar, 3)
        attempt.overall_score = round(total_marks, 2)
        attempt.status = 'evaluated'
        attempt.evaluated_at = timezone.now()
        
        # Generate comprehensive overall feedback
        percentage = (total_marks / attempt.unit_test.total_marks * 100) if attempt.unit_test.total_marks > 0 else 0
        
        feedback_parts.append("=" * 60)
        feedback_parts.append("📊 **UNIT TEST EVALUATION SUMMARY**")
        feedback_parts.append("=" * 60)
        feedback_parts.append("")
        
        # Overall performance
        feedback_parts.append(f"🎯 **Overall Score: {total_marks:.2f}/{attempt.unit_test.total_marks} ({percentage:.1f}%)**")
        feedback_parts.append(f"📝 **Content Accuracy: {avg_content*100:.1f}%** (How well you covered key concepts)")
        feedback_parts.append(f"✍️ **Grammar & Expression: {avg_grammar*100:.1f}%** (Language quality & clarity)")
        feedback_parts.append(f"🤖 **Evaluated by: {model_to_use.upper()} AI**")
        feedback_parts.append("")
        
        # Question breakdown
        if one_mark_count > 0:
            one_mark_percentage = (one_mark_correct / one_mark_count * 100)
            feedback_parts.append(f"📌 **1-Mark Questions: {one_mark_correct}/{one_mark_count} correct ({one_mark_percentage:.0f}%)**")
        
        if multi_mark_count > 0:
            multi_mark_obtained = total_marks - one_mark_correct
            multi_mark_total = attempt.unit_test.total_marks - one_mark_count
            if multi_mark_total > 0:
                multi_mark_percentage = (multi_mark_obtained / multi_mark_total * 100)
                feedback_parts.append(f"📝 **Long-Answer Questions: {multi_mark_obtained:.1f}/{multi_mark_total:.1f} ({multi_mark_percentage:.0f}%)**")
        
        feedback_parts.append("")
        feedback_parts.append("-" * 60)
        
        # Performance-based encouragement
        if percentage >= 90:
            feedback_parts.append("🌟 **OUTSTANDING PERFORMANCE!**")
            feedback_parts.append("Excellent work! You have demonstrated exceptional understanding of the topics.")
            feedback_parts.append("Your answers show clarity, depth, and strong grasp of concepts.")
        elif percentage >= 75:
            feedback_parts.append("👍 **GREAT JOB!**")
            feedback_parts.append("Very good performance! You have a solid understanding of most topics.")
            feedback_parts.append("Review the detailed feedback to further strengthen your knowledge.")
        elif percentage >= 60:
            feedback_parts.append("💪 **GOOD EFFORT!**")
            feedback_parts.append("You're on the right track! You understand the basics well.")
            feedback_parts.append("Focus on the feedback for each question to improve your scores.")
        elif percentage >= 40:
            feedback_parts.append("📚 **KEEP IMPROVING!**")
            feedback_parts.append("You're making progress. With more practice, you'll do better.")
            feedback_parts.append("Pay attention to the key concepts highlighted in the feedback.")
        else:
            feedback_parts.append("🎯 **DON'T GIVE UP!**")
            feedback_parts.append("Learning takes time and practice. Don't be discouraged!")
            feedback_parts.append("Review your textbook notes and the detailed feedback carefully.")
        
        feedback_parts.append("")
        feedback_parts.append("-" * 60)
        feedback_parts.append("💡 **PERSONALIZED RECOMMENDATIONS:**")
        feedback_parts.append("")
        
        # Specific recommendations based on scores
        if avg_content < 0.6:
            feedback_parts.append("� **Content Focus:**")
            feedback_parts.append("   • Review the model answers carefully to understand key points")
            feedback_parts.append("   • Make sure you include all important concepts in your answers")
            feedback_parts.append("   • Practice explaining topics in your own words while covering all main ideas")
            feedback_parts.append("")
        
        if avg_grammar < 0.7:
            feedback_parts.append("✏️ **Language Improvement:**")
            feedback_parts.append("   • Work on sentence structure and grammar")
            feedback_parts.append("   • Use proper punctuation (periods, commas, capital letters)")
            feedback_parts.append("   • Write in clear, complete sentences")
            feedback_parts.append("   • Read your answer once before submitting to check for errors")
            feedback_parts.append("")
        
        if one_mark_count > 0 and one_mark_correct < one_mark_count * 0.7:
            feedback_parts.append("🎯 **Short Answer Tips:**")
            feedback_parts.append("   • Read 1-mark questions carefully - they need exact answers")
            feedback_parts.append("   • Review definitions and key terms from your textbook")
            feedback_parts.append("   • Be precise and specific in short answers")
            feedback_parts.append("")
        
        feedback_parts.append("-" * 60)
        feedback_parts.append("📝 **Next Steps:**")
        feedback_parts.append("1. Review each question's detailed feedback below")
        feedback_parts.append("2. Understand why points were awarded or deducted")
        feedback_parts.append("3. Note down the areas where you can improve")
        feedback_parts.append("4. Practice similar questions to strengthen weak areas")
        feedback_parts.append("=" * 60)
        
        attempt.overall_feedback = "\n".join(feedback_parts)
        attempt.save()
        
        logger.info(f"✅ Evaluation complete: {total_marks:.2f}/{attempt.unit_test.total_marks} "
                   f"({percentage:.1f}%) | Content: {avg_content*100:.0f}% | Grammar: {avg_grammar*100:.0f}%")
        
        return {
            'success': True,
            'total_marks': total_marks,
            'max_marks': attempt.unit_test.total_marks,
            'percentage': percentage,
            'avg_content': avg_content,
            'avg_grammar': avg_grammar,
            'evaluated_count': evaluated_count,
            'one_mark_stats': {
                'total': one_mark_count,
                'correct': one_mark_correct
            },
            'ai_model': model_to_use
        }


# Global evaluator instance (default: Gemini)
evaluator = UnitTestEvaluator(ai_model=os.environ.get('DEFAULT_EVAL_AI', 'gemini'))
