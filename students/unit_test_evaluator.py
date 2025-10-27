"""
AI-Powered Unit Test Evaluator

This module evaluates student answers using the advanced AI evaluation system.
It integrates with superadmin.evaluate to provide:
- Exact matching for 1-mark questions
- AI-based content and grammar scoring for 2-5 mark questions
- Detailed feedback for each answer
- Overall test statistics and feedback
"""
import logging
from django.utils import timezone
from typing import Dict, List

logger = logging.getLogger(__name__)


class UnitTestEvaluator:
    """Evaluates unit test attempts using AI-powered evaluation."""
    
    def evaluate_full_test(self, attempt_id: int) -> Dict:
        """Evaluate all answers in a unit test attempt.
        
        Args:
            attempt_id: ID of the UnitTestAttempt to evaluate
        
        Returns:
            Dict with evaluation results and statistics
        """
        from students.models import UnitTestAttempt, UnitTestAnswer
        from superadmin.evaluate import evaluate_answer
        
        try:
            attempt = UnitTestAttempt.objects.get(id=attempt_id)
        except UnitTestAttempt.DoesNotExist:
            logger.error(f"UnitTestAttempt {attempt_id} not found")
            return {'success': False, 'error': 'Attempt not found'}
        
        logger.info(f"🔍 Evaluating unit test attempt {attempt_id} for {attempt.student.email}")
        
        # Get all answers
        answers = UnitTestAnswer.objects.filter(attempt=attempt).select_related('question')
        
        total_marks = 0.0
        total_content = 0.0
        total_grammar = 0.0
        evaluated_count = 0
        feedback_parts = []
        
        for answer_obj in answers:
            question = answer_obj.question
            student_answer = answer_obj.answer_text or ''
            model_answer = question.model_answer
            
            # Evaluate using AI
            result = evaluate_answer(
                student_answer=student_answer,
                model_answer=model_answer,
                marks=question.marks,
                question=question.question_text
            )
            
            # Store evaluation in answer object
            answer_obj.awarded_marks = result['awarded_marks']
            answer_obj.content_score = result['content_score']
            answer_obj.grammar_score = result['grammar_score']
            answer_obj.ai_feedback = result['feedback']
            answer_obj.evaluation_type = result['evaluation_type']
            answer_obj.save()
            
            # Accumulate stats
            total_marks += result['awarded_marks']
            total_content += result['content_score']
            total_grammar += result['grammar_score']
            evaluated_count += 1
            
            logger.info(f"   Q{question.question_number} ({question.marks}m): "
                       f"{result['awarded_marks']:.2f} marks "
                       f"(content: {result['content_score']:.2f}, grammar: {result['grammar_score']:.2f})")
        
        # Calculate averages
        avg_content = total_content / max(1, evaluated_count)
        avg_grammar = total_grammar / max(1, evaluated_count)
        
        # Update attempt with final scores
        attempt.total_marks_obtained = round(total_marks, 2)
        attempt.status = 'evaluated'
        attempt.evaluated_at = timezone.now()
        
        # Generate overall feedback
        percentage = (total_marks / attempt.unit_test.total_marks * 100) if attempt.unit_test.total_marks > 0 else 0
        
        feedback_parts.append(f"📊 Overall Performance: {percentage:.1f}%")
        feedback_parts.append(f"📝 Content Accuracy: {avg_content*100:.1f}%")
        feedback_parts.append(f"✍️ Grammar & Expression: {avg_grammar*100:.1f}%")
        
        if percentage >= 90:
            feedback_parts.append("🌟 Outstanding work! You have excellent understanding of the topics.")
        elif percentage >= 75:
            feedback_parts.append("👍 Great job! Keep up the good work.")
        elif percentage >= 60:
            feedback_parts.append("💪 Good effort! Review the feedback for each question to improve.")
        elif percentage >= 40:
            feedback_parts.append("📚 You're making progress. Focus on understanding key concepts better.")
        else:
            feedback_parts.append("🎯 Don't worry! Review your notes and try again. Practice makes perfect.")
        
        # Add specific recommendations
        if avg_content < 0.6:
            feedback_parts.append("💡 Tip: Focus on including all key points from the textbook in your answers.")
        if avg_grammar < 0.7:
            feedback_parts.append("✏️ Tip: Pay attention to sentence structure, punctuation, and clarity of expression.")
        
        attempt.overall_feedback = "\n".join(feedback_parts)
        attempt.save()
        
        logger.info(f"✅ Evaluation complete: {total_marks:.2f}/{attempt.unit_test.total_marks} marks")
        
        return {
            'success': True,
            'total_marks': total_marks,
            'max_marks': attempt.unit_test.total_marks,
            'percentage': percentage,
            'avg_content': avg_content,
            'avg_grammar': avg_grammar,
            'evaluated_count': evaluated_count
        }


# Global evaluator instance
evaluator = UnitTestEvaluator()
