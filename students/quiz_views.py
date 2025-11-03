"""
Quiz System Views
Handles quiz taking, submission, verification, and analytics
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db.models import Q, Max, Avg, Count
import json
import logging

from .models import (
    QuizChapter, QuizQuestion, QuestionVariant,
    StudentChapterProgress, QuizAttempt, QuizAnswer
)
from ncert_project.vector_db_utils import get_vector_db_manager

logger = logging.getLogger('students')


@login_required
def quiz_dashboard(request):
    """
    Show all subjects and chapters for student's class
    Display lock status and best scores
    Progressive unlocking: chapter unlocks when previous chapter is completed (score >= 70%)
    """
    user = request.user
    student_class = getattr(user, 'standard', '5')
    
    # Normalize class format (handle both "5" and "Class 5")
    if not str(student_class).lower().startswith('class'):
        class_filter = f"Class {student_class}"
    else:
        class_filter = str(student_class)
    
    # Get all chapters for this class, ordered by subject and chapter_order
    chapters = QuizChapter.objects.filter(
        class_number=class_filter,
        is_active=True
    ).order_by('subject', 'chapter_order')
    
    # Group chapters by subject and apply progressive unlocking logic
    chapters_by_subject = {}
    
    for chapter in chapters:
        # Get or create progress for this chapter
        progress, created = StudentChapterProgress.objects.get_or_create(
            student=user,
            chapter=chapter,
            defaults={
                'is_unlocked': False,
                'unlocked_at': None
            }
        )
        
        # Unlock logic:
        # 1. First chapter of each subject (chapter_order == 1) is always unlocked
        # 2. Subsequent chapters unlock when previous chapter is completed (score >= 70%)
        
        if chapter.chapter_order == 1:
            # First chapter - always unlocked
            if not progress.is_unlocked:
                progress.is_unlocked = True
                progress.unlocked_at = timezone.now()
                progress.save()
                logger.info(f"🔓 Auto-unlocked first chapter for {user.email}: {chapter.chapter_name}")
        else:
            # For chapters 2+, check if previous chapter is completed
            previous_chapter = QuizChapter.objects.filter(
                class_number=class_filter,
                subject=chapter.subject,
                chapter_order=chapter.chapter_order - 1,
                is_active=True
            ).first()
            
            if previous_chapter:
                previous_progress, _ = StudentChapterProgress.objects.get_or_create(
                    student=user,
                    chapter=previous_chapter,
                    defaults={'is_unlocked': False}
                )
                
                # Unlock if previous chapter is completed (best_score >= 70%)
                if previous_progress.best_score >= 70 and not progress.is_unlocked:
                    progress.is_unlocked = True
                    progress.unlocked_at = timezone.now()
                    progress.save()
                    logger.info(f"🔓 Unlocked chapter for {user.email}: {chapter.chapter_name} (prev score: {previous_progress.best_score}%)")
        
        # Organize chapters by subject
        if chapter.subject not in chapters_by_subject:
            chapters_by_subject[chapter.subject] = []
        
        chapters_by_subject[chapter.subject].append({
            'chapter_id': chapter.chapter_id,
            'chapter_name': chapter.chapter_name,
            'order': chapter.chapter_order,
            'is_unlocked': progress.is_unlocked,
            'is_completed': progress.best_score >= 70,  # Completed if score >= 70%
            'best_score': progress.best_score if progress.total_attempts > 0 else None,
            'total_attempts': progress.total_attempts,
        })
    
    context = {
        'user': user,
        'student_class': student_class,
        'chapters_by_subject': chapters_by_subject,
    }
    
    return render(request, 'students/quiz_dashboard.html', context)


@login_required
def start_quiz(request, chapter_id):
    """
    Start a new quiz attempt for a chapter
    Shows quiz page with questions loaded one at a time
    """
    user = request.user
    
    try:
        chapter = get_object_or_404(QuizChapter, chapter_id=chapter_id)
        
        # Check if chapter is unlocked
        progress, created = StudentChapterProgress.objects.get_or_create(
            student=user, 
            chapter=chapter,
            defaults={'is_unlocked': chapter.chapter_order == 1}  # First chapter auto-unlocked
        )
        
        if not progress.is_unlocked:
            messages.error(request, 'This chapter is locked. Complete the previous chapter first.')
            return redirect('students:quiz_dashboard')
        
        # Get next attempt number
        last_attempt = QuizAttempt.objects.filter(
            student=user,
            chapter=chapter
        ).aggregate(Max('attempt_number'))
        
        attempt_number = (last_attempt['attempt_number__max'] or 0) + 1
        
        # Create new attempt
        attempt = QuizAttempt.objects.create(
            student=user,
            chapter=chapter,
            attempt_number=attempt_number,
            status='in_progress',
            total_questions=chapter.total_questions
        )
        
        # Load questions with appropriate variants
        questions = QuizQuestion.objects.filter(chapter=chapter).order_by('question_number')
        
        # Check if chapter has questions
        if not questions.exists():
            messages.warning(request, f'This chapter does not have quiz questions yet. Questions are being generated. Please try Chapter 1 or Chapter 2 for now.')
            return redirect('students:quiz_dashboard')
        
        questions_data = []
        
        for question in questions:
            # Select variant based on attempt number (cycle through variants)
            variants = question.variants.all().order_by('variant_number')
            if variants:
                variant_index = (attempt_number - 1) % len(variants)
                variant = variants[variant_index]
                
                questions_data.append({
                    'id': question.id,
                    'variant_id': variant.id,
                    'question_number': question.question_number,
                    'question_text': variant.question_text,
                    'option_a': variant.option_a,
                    'option_b': variant.option_b,
                    'option_c': variant.option_c,
                    'option_d': variant.option_d,
                    'topic': question.topic,
                    'difficulty': question.difficulty,
                })
        
        logger.info(f"[OK] Started quiz attempt {attempt_number} for {user.email} - {chapter.chapter_name}")
        
        # Render the quiz template (shows one question at a time via Alpine.js)
        return render(request, 'students/quiz_question.html', {
            'attempt_id': attempt.id,
            'attempt_number': attempt_number,
            'chapter_name': chapter.chapter_name,
            'chapter': chapter,
            'questions': json.dumps(questions_data),  # Pass as JSON for Alpine.js
            'total_questions': len(questions_data),
        })
        
    except Exception as e:
        logger.error(f"Error starting quiz: {e}")
        messages.error(request, f'Error starting quiz: {str(e)}')
        return redirect('students:quiz_dashboard')


@login_required
@require_POST
def submit_quiz(request, attempt_id):
    """
    Submit entire quiz with all answers at once
    Verify answers using RAG and generate explanations
    Calculate score and heatmap
    """
    user = request.user
    
    try:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=user)
        
        if attempt.status != 'in_progress':
            return JsonResponse({
                'status': 'error',
                'error': 'Quiz already submitted'
            }, status=400)
        
        # Parse submitted answers
        answers_data = json.loads(request.body)
        submitted_answers = answers_data.get('answers', [])
        
        logger.info(f"[NOTE] Submitting quiz for {user.email} - Attempt {attempt.id}")
        
        # Process each answer
        correct_count = 0
        topic_performance = {}
        all_answers = []
        
        for ans_data in submitted_answers:
            question = get_object_or_404(QuizQuestion, id=ans_data['question_id'])
            variant = get_object_or_404(QuestionVariant, id=ans_data['variant_id'])
            selected = ans_data['selected_answer']
            
            # Check if correct
            is_correct = (selected == variant.correct_answer)
            if is_correct:
                correct_count += 1
            
            # Track topic performance
            topic = question.topic
            if topic not in topic_performance:
                topic_performance[topic] = {'correct': 0, 'total': 0}
            topic_performance[topic]['total'] += 1
            if is_correct:
                topic_performance[topic]['correct'] += 1
            
            # Verify with RAG
            verification_result = verify_answer_with_rag(
                question=variant.question_text,
                selected_answer=selected,
                correct_answer=variant.correct_answer,
                options={
                    'A': variant.option_a,
                    'B': variant.option_b,
                    'C': variant.option_c,
                    'D': variant.option_d,
                },
                chapter_id=attempt.chapter.chapter_id,
                topic=question.topic
            )
            
            # Create answer record
            quiz_answer = QuizAnswer.objects.create(
                attempt=attempt,
                question=question,
                variant_used=variant,
                selected_answer=selected,
                is_correct=is_correct,
                time_taken_seconds=ans_data.get('time_taken', 0),
                verification_status=verification_result['status'],
                ai_explanation=verification_result['explanation'],
                rag_confidence=verification_result.get('confidence', 0.0)
            )
            
            all_answers.append({
                'question_number': question.question_number,
                'question_text': variant.question_text,
                'selected': selected,
                'correct': variant.correct_answer,
                'is_correct': is_correct,
                'explanation': verification_result['explanation'],
                'topic': topic,
            })
        
        # Calculate score
        score_percentage = int((correct_count / len(submitted_answers)) * 100)
        is_passed = score_percentage >= attempt.chapter.passing_percentage
        
        # Calculate topic performance percentages
        for topic in topic_performance:
            perf = topic_performance[topic]
            perf['percentage'] = int((perf['correct'] / perf['total']) * 100)
        
        # Generate topic-based feedback
        strong_topics = []
        weak_topics = []
        
        for topic, perf in topic_performance.items():
            if perf['percentage'] >= 80:
                strong_topics.append(topic)
            elif perf['percentage'] < 60:
                weak_topics.append(topic)
        
        # Create feedback message
        feedback_message = ""
        if strong_topics:
            feedback_message += f"✅ Great job! You are strong in: {', '.join(strong_topics)}. "
        if weak_topics:
            feedback_message += f"📚 You need to focus more on: {', '.join(weak_topics)}. "
        
        if not weak_topics and score_percentage >= 80:
            feedback_message = "🎉 Excellent! You have mastered this chapter!"
        elif not weak_topics:
            feedback_message += "Keep practicing to improve further!"
        
        # Update attempt
        attempt.status = 'verified'
        attempt.submitted_at = timezone.now()
        attempt.total_time_seconds = answers_data.get('total_time', 0)
        attempt.correct_answers = correct_count
        attempt.score_percentage = score_percentage
        attempt.is_passed = is_passed
        attempt.feedback_message = feedback_message  # Store feedback
        attempt.topic_performance = topic_performance
        attempt.save()
        
        # Sync to MongoDB for analytics
        try:
            from ncert_project.mongodb_utils import sync_quiz_attempt_to_mongo
            sync_quiz_attempt_to_mongo(attempt)
        except Exception as e:
            logger.warning(f"⚠️  Failed to sync quiz to MongoDB: {e}")
        
        # Update chapter progress
        progress = StudentChapterProgress.objects.get(student=user, chapter=attempt.chapter)
        progress.total_attempts += 1
        progress.last_attempt_date = timezone.now()
        
        if score_percentage > progress.best_score:
            progress.best_score = score_percentage
        
        if is_passed and not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = timezone.now()
            
            # Unlock next chapter in same subject
            next_chapter = QuizChapter.objects.filter(
                class_number=attempt.chapter.class_number,
                subject=attempt.chapter.subject,
                chapter_order=attempt.chapter.chapter_order + 1,
                is_active=True
            ).first()
            
            if next_chapter:
                next_progress, created = StudentChapterProgress.objects.get_or_create(
                    student=user,
                    chapter=next_chapter,
                    defaults={'is_unlocked': True, 'unlocked_at': timezone.now()}
                )
                if not next_progress.is_unlocked:
                    next_progress.is_unlocked = True
                    next_progress.unlocked_at = timezone.now()
                    next_progress.save()
                    logger.info(f"🔓 Unlocked next chapter: {next_chapter.chapter_name}")
        
        progress.save()
        
        # Sync progress to MongoDB
        try:
            from ncert_project.mongodb_utils import sync_student_progress_to_mongo
            sync_student_progress_to_mongo(progress)
        except Exception as e:
            logger.warning(f"⚠️  Failed to sync progress to MongoDB: {e}")
        
        logger.info(f"[OK] Quiz submitted: Score {score_percentage}% - {'PASSED' if is_passed else 'FAILED'}")
        
        # Generate redirect URL using reverse
        from django.urls import reverse
        redirect_url = reverse('students:quiz_results', kwargs={'attempt_id': attempt.id})
        
        return JsonResponse({
            'status': 'success',
            'attempt_id': attempt.id,
            'score_percentage': score_percentage,
            'correct_answers': correct_count,
            'total_questions': len(submitted_answers),
            'is_passed': is_passed,
            'passing_percentage': attempt.chapter.passing_percentage,
            'topic_performance': topic_performance,
            'all_answers': all_answers,
            'redirect_url': redirect_url,
        })
        
    except Exception as e:
        logger.error(f"Error submitting quiz: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


def verify_answer_with_rag(question, selected_answer, correct_answer, options, chapter_id, topic):
    """
    Verify answer using Vector DB (Pinecone/ChromaDB) RAG and generate explanation
    """
    try:
        # Get relevant content from Vector DB (Pinecone in production)
        vector_manager = get_vector_db_manager()
        results = vector_manager.query_by_class_subject_chapter(
            query_text=f"{topic} {question}",
            n_results=3
        )
        
        rag_content = ""
        if results and results.get("documents") and results["documents"][0]:
            rag_content = "\n".join(results["documents"][0][:2])
        
        # Ask AI to verify and explain
        import openai
        import google.generativeai as genai
        import os
        
        openai.api_key = os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        prompt = f"""Based on the NCERT textbook content below, provide a SHORT explanation (2-3 sentences MAXIMUM).

NCERT CONTENT:
{rag_content if rag_content else "No specific content found"}

QUESTION: {question}
OPTIONS:
A) {options['A']}
B) {options['B']}
C) {options['C']}
D) {options['D']}

STUDENT SELECTED: {selected_answer}
CORRECT ANSWER: {correct_answer}

IMPORTANT RULES:
- Maximum 2-3 sentences only
- Use plain simple text - NO markdown formatting (no *, #, **, _, etc.)
- Keep it simple for Class 5 students (10-11 years old)
- Explain why the correct answer is right based on the content
- If student was wrong, briefly explain why

GOOD EXAMPLE: "The correct answer is B because water flows from mountains to the sea. Rivers always move downward due to gravity."
BAD EXAMPLE: "**Water flows from high to low.** This is because of *gravity* which pulls water downward. Rivers originate from mountains..."

Explanation:"""

        explanation = ""
        
        # Try AI for explanation
        if openai.api_key:
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an NCERT teacher. Explain answers in 2-3 simple sentences with NO markdown formatting."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=150  # Reduced from 300 to force shorter responses
                )
                explanation = response.choices[0].message.content
            except:
                pass
        
        if not explanation and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt)
                explanation = response.text
            except:
                pass
        
        if not explanation:
            explanation = f"The correct answer is {correct_answer}. {options[correct_answer]}"
        
        return {
            'status': 'verified_by_rag' if rag_content else 'no_rag_content',
            'explanation': explanation,
            'confidence': 0.9 if rag_content else 0.5
        }
        
    except Exception as e:
        logger.error(f"RAG verification error: {e}")
        return {
            'status': 'error',
            'explanation': f"The correct answer is {correct_answer}.",
            'confidence': 0.0
        }


@login_required
def quiz_results(request, attempt_id):
    """
    Show detailed quiz results with heatmap
    """
    user = request.user
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=user)
    
    answers = attempt.answers.all().select_related('question', 'variant_used').order_by('question__question_number')
    
    # Calculate derived values
    correct_count = attempt.correct_answers
    total_questions = attempt.chapter.total_questions
    
    # Format time taken
    if attempt.total_time_seconds:
        minutes = attempt.total_time_seconds // 60
        seconds = attempt.total_time_seconds % 60
        time_taken = f"{minutes}m {seconds}s"
    else:
        time_taken = "N/A"
    
    context = {
        'user': user,
        'attempt': attempt,
        'answers': answers,
        'topic_performance': attempt.topic_performance,
        'correct_count': correct_count,
        'total_questions': total_questions,
        'time_taken': time_taken,
        'attempt_number': attempt.attempt_number,
    }
    
    return render(request, 'students/quiz_results.html', context)


@login_required
def quiz_history(request):
    """
    Show all past quiz attempts with scores and heatmaps
    """
    user = request.user
    
    attempts = QuizAttempt.objects.filter(
        student=user,
        status='verified'
    ).select_related('chapter').order_by('-submitted_at')
    
    context = {
        'user': user,
        'attempts': attempts,
    }
    
    return render(request, 'students/quiz_history.html', context)


@login_required
def quiz_analytics(request, chapter_id):
    """
    Detailed analytics for a specific chapter
    Shows all attempts with trend analysis
    """
    user = request.user
    chapter = get_object_or_404(QuizChapter, chapter_id=chapter_id)
    
    attempts = QuizAttempt.objects.filter(
        student=user,
        chapter=chapter,
        status='verified'
    ).order_by('started_at')
    
    # Calculate statistics
    best_score = 0
    average_score = 0
    improvement = 0
    
    if attempts.exists():
        scores = [a.score_percentage for a in attempts]
        best_score = max(scores)
        average_score = sum(scores) / len(scores)
        
        # Calculate improvement (first vs last attempt)
        if len(scores) > 1:
            improvement = scores[-1] - scores[0]
    
    # Calculate trends
    attempt_data = []
    topic_performance_data = {}
    
    for attempt in attempts:
        attempt_data.append({
            'attempt_number': attempt.attempt_number,
            'score': attempt.score_percentage,
            'date': attempt.started_at,
            'topic_performance': attempt.topic_performance,
        })
        
        # Collect topic performance across attempts
        if attempt.topic_performance:
            for topic, perf in attempt.topic_performance.items():
                if topic not in topic_performance_data:
                    topic_performance_data[topic] = []
                topic_performance_data[topic].append(perf.get('percentage', 0))
    
    # Calculate average performance per topic
    topic_averages = {}
    for topic, percentages in topic_performance_data.items():
        topic_averages[topic] = sum(percentages) / len(percentages) if percentages else 0
    
    # Y-axis values for chart
    y_axis_values = [100, 80, 60, 40, 20, 0]
    
    context = {
        'user': user,
        'chapter': chapter,
        'attempts': attempts,
        'attempt_data': attempt_data,
        'best_score': best_score,
        'average_score': average_score,
        'improvement': improvement,
        'y_axis_values': y_axis_values,
        'topic_averages': topic_averages,
    }
    
    return render(request, 'students/quiz_analytics.html', context)
