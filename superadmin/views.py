import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from celery.result import AsyncResult
from .forms import UploadBookForm
from .models import UploadedBook

logger = logging.getLogger(__name__)

def is_superadmin(user):
    return user.is_authenticated and user.role == 'super_admin'


@login_required
@user_passes_test(is_superadmin)
def dashboard(request):
    """
    Superadmin dashboard with statistics
    """
    total_uploads = UploadedBook.objects.count()
    queued = UploadedBook.objects.filter(status='queued').count()
    processing = UploadedBook.objects.filter(status='processing').count()
    completed = UploadedBook.objects.filter(status='done').count()
    failed = UploadedBook.objects.filter(status='failed').count()
    
    recent_uploads = UploadedBook.objects.all().order_by('-uploaded_at')[:10]
    
    context = {
        'total_uploads': total_uploads,
        'queued': queued,
        'processing': processing,
        'completed': completed,
        'failed': failed,
        'recent_uploads': recent_uploads,
    }
    
    return render(request, 'superadmin/dashboard.html', context)


@login_required
@user_passes_test(is_superadmin)
def upload_book(request):
    """
    Upload a new NCERT PDF book
    """
    if request.method == 'POST':
        form = UploadBookForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.uploader = request.user
            obj.save()
            
            # Try to process immediately (without Celery for now)
            try:
                # Import processing functions
                from superadmin.tasks import process_uploaded_book_sync
                
                # Process synchronously
                result = process_uploaded_book_sync(obj.id)
                
                logger.info(f"Processed upload {obj.id}: {result}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'upload_id': obj.id,
                        'message': 'PDF processed successfully'
                    })
                
                return redirect('superadmin:upload_list')
                
            except Exception as e:
                logger.error(f"Error processing upload: {str(e)}")
                obj.status = 'failed'
                obj.notes = f"Processing error: {str(e)}"
                obj.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'error',
                        'error': str(e)
                    }, status=500)
                
                return redirect('superadmin:upload_list')
    else:
        form = UploadBookForm()
    
    return render(request, 'superadmin/upload.html', {'form': form})


@login_required
@user_passes_test(is_superadmin)
def upload_list(request):
    """
    List all uploaded books with status
    """
    uploads = UploadedBook.objects.all().order_by('-uploaded_at')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        uploads = uploads.filter(status=status_filter)
    
    context = {
        'uploads': uploads,
        'status_filter': status_filter,
    }
    
    return render(request, 'superadmin/upload_list.html', context)


@login_required
@user_passes_test(is_superadmin)
def upload_detail(request, upload_id):
    """
    View details of a specific upload
    """
    upload = get_object_or_404(UploadedBook, id=upload_id)
    
    context = {
        'upload': upload,
    }
    
    return render(request, 'superadmin/upload_detail.html', context)


@login_required
@user_passes_test(is_superadmin)
def upload_status(request, upload_id):
    """
    Get real-time status of an upload processing job (AJAX endpoint)
    """
    upload = get_object_or_404(UploadedBook, id=upload_id)
    
    response_data = {
        'upload_id': upload.id,
        'status': upload.status,
        'filename': upload.original_filename,
        'notes': upload.notes or '',
    }
    
    # If processing, check Celery task status
    if upload.ingestion_job_id and upload.status == 'processing':
        task = AsyncResult(upload.ingestion_job_id)
        response_data['celery_state'] = task.state
        
        if task.state == 'PROGRESS':
            response_data['progress'] = task.info
    
    return JsonResponse(response_data)


# ==================== UNIT TEST MANAGEMENT ====================

@login_required
@user_passes_test(is_superadmin)
def unit_test_list(request):
    """
    List all unit tests
    """
    from students.models import UnitTest, QuizChapter
    
    tests = UnitTest.objects.select_related('created_by').prefetch_related('chapters').all().order_by('-created_at')
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    
    context = {
        'tests': tests,
        'chapters': chapters,
    }
    
    return render(request, 'superadmin/unit_test_list.html', context)


@login_required
@user_passes_test(is_superadmin)
def unit_test_create(request):
    """
    Create a new unit test (manual or from uploaded document)
    """
    from students.models import UnitTest, QuizChapter
    
    if request.method == 'POST':
        title = request.POST.get('title')
        chapter_ids = request.POST.getlist('chapters')  # Changed to getlist for multiple chapters
        description = request.POST.get('description', '')
        total_marks = request.POST.get('total_marks', 100)
        duration_minutes = request.POST.get('duration_minutes', 60)
        passing_marks = request.POST.get('passing_marks', 40)
        is_active = request.POST.get('is_active') == 'on'
        
        # Create unit test without chapters first
        unit_test = UnitTest.objects.create(
            title=title,
            description=description,
            total_marks=total_marks,
            duration_minutes=duration_minutes,
            passing_marks=passing_marks,
            is_active=is_active,
            created_by=request.user
        )
        
        # Add multiple chapters
        if chapter_ids:
            unit_test.chapters.set(chapter_ids)
        
        return redirect('superadmin:unit_test_detail', test_id=unit_test.id)
    
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    
    return render(request, 'superadmin/unit_test_create.html', {'chapters': chapters})


@login_required
@user_passes_test(is_superadmin)
def unit_test_upload_questions(request):
    """
    Upload questions from PDF/DOC file
    Admin provides metadata: class, subject, units, chapter
    File contains questions and answers in structured format
    """
    from students.models import QuizChapter
    import json
    
    if request.method == 'POST':
        # Get metadata from form
        class_name = request.POST.get('class_name')
        subject_name = request.POST.get('subject_name')
        units = request.POST.get('units')
        chapter_id = request.POST.get('chapter')
        
        # Get uploaded file
        uploaded_file = request.FILES.get('question_file')
        
        if not uploaded_file:
            return render(request, 'superadmin/unit_test_upload.html', {
                'error': 'Please upload a file',
                'chapters': QuizChapter.objects.all().order_by('chapter_number')
            })
        
        # Save file temporarily
        import os
        import tempfile
        from django.conf import settings
        
        # Create uploads directory if not exists
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'unit_test_uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_dir, uploaded_file.name)
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        try:
            # Parse the document
            from .document_parser import parse_document
            result = parse_document(file_path)
            
            # Check if parsing was successful
            if not result['is_valid']:
                return render(request, 'superadmin/unit_test_upload.html', {
                    'error': 'Document parsing errors: ' + ', '.join(result['errors']),
                    'chapters': QuizChapter.objects.all().order_by('chapter_number'),
                    'parsed_data': result
                })
            
            # Store parsed data in session for preview
            request.session['parsed_questions'] = {
                'metadata': result['metadata'],
                'questions': result['questions'],
                'user_metadata': {
                    'class_name': class_name,
                    'subject_name': subject_name,
                    'units': units,
                    'chapter_id': chapter_id
                }
            }
            
            # Redirect to preview page
            return redirect('superadmin:unit_test_preview_upload')
        
        except Exception as e:
            return render(request, 'superadmin/unit_test_upload.html', {
                'error': f'Error parsing document: {str(e)}',
                'chapters': QuizChapter.objects.all().order_by('chapter_number')
            })
        finally:
            # Clean up temp file
            if os.path.exists(file_path):
                os.remove(file_path)
    
    # GET request - show upload form
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    return render(request, 'superadmin/unit_test_upload.html', {'chapters': chapters})


@login_required
@user_passes_test(is_superadmin)
def unit_test_preview_upload(request):
    """
    Preview parsed questions before creating test
    """
    from students.models import UnitTest, UnitTestQuestion, QuizChapter
    
    parsed_data = request.session.get('parsed_questions')
    if not parsed_data:
        return redirect('superadmin:unit_test_upload_questions')
    
    if request.method == 'POST':
        # Create the unit test
        action = request.POST.get('action')
        
        if action == 'confirm':
            user_metadata = parsed_data['user_metadata']
            questions_data = parsed_data['questions']
            doc_metadata = parsed_data['metadata']
            
            # Get chapter
            chapter = get_object_or_404(QuizChapter, id=user_metadata['chapter_id'])
            
            # Calculate total marks
            total_marks = sum(q['marks'] for q in questions_data)
            
            # Create test title
            title = f"{user_metadata['class_name']} - {user_metadata['subject_name']} - {user_metadata['units']}"
            
            # Create unit test
            unit_test = UnitTest.objects.create(
                title=title,
                chapter=chapter,
                description=f"Units: {user_metadata['units']}\nClass: {user_metadata['class_name']}\nSubject: {user_metadata['subject_name']}",
                total_marks=total_marks,
                duration_minutes=60,  # default
                passing_marks=int(total_marks * 0.4),  # 40%
                is_active=False,  # Admin should review before activating
                created_by=request.user
            )
            
            # Create questions
            for q_data in questions_data:
                UnitTestQuestion.objects.create(
                    unit_test=unit_test,
                    question_number=q_data['question_number'],
                    question_text=q_data['question_text'],
                    marks=q_data['marks'],
                    model_answer=q_data['model_answer'],
                    key_points=q_data['key_points']
                )
            
            # Clear session
            del request.session['parsed_questions']
            
            # Redirect to test detail
            return redirect('superadmin:unit_test_detail', test_id=unit_test.id)
        
        elif action == 'cancel':
            # Clear session and go back
            del request.session['parsed_questions']
            return redirect('superadmin:unit_test_upload_questions')
    
    # GET request - show preview
    context = {
        'parsed_data': parsed_data,
        'total_marks': sum(q['marks'] for q in parsed_data['questions']),
        'num_questions': len(parsed_data['questions'])
    }
    
    return render(request, 'superadmin/unit_test_preview.html', context)


@login_required
@user_passes_test(is_superadmin)
def unit_test_detail(request, test_id):
    """
    View and manage unit test questions
    """
    from students.models import UnitTest, UnitTestQuestion
    
    unit_test = get_object_or_404(UnitTest, id=test_id)
    questions = unit_test.questions.all().order_by('question_number')
    
    context = {
        'unit_test': unit_test,
        'questions': questions,
    }
    
    return render(request, 'superadmin/unit_test_detail.html', context)


@login_required
@user_passes_test(is_superadmin)
def unit_test_add_question(request, test_id):
    """
    Add a question to a unit test
    """
    from students.models import UnitTest, UnitTestQuestion
    import json
    
    unit_test = get_object_or_404(UnitTest, id=test_id)
    
    if request.method == 'POST':
        question_text = request.POST.get('question_text')
        marks = request.POST.get('marks', 10)
        model_answer = request.POST.get('model_answer')
        key_points = request.POST.get('key_points', '')
        
        # Get next question number
        last_question = unit_test.questions.order_by('-question_number').first()
        question_number = (last_question.question_number + 1) if last_question else 1
        
        # Parse key points if provided
        key_points_list = []
        if key_points:
            key_points_list = [kp.strip() for kp in key_points.split('\n') if kp.strip()]
        
        UnitTestQuestion.objects.create(
            unit_test=unit_test,
            question_number=question_number,
            question_text=question_text,
            marks=marks,
            model_answer=model_answer,
            key_points=key_points_list if key_points_list else None
        )
        
        return redirect('superadmin:unit_test_detail', test_id=test_id)
    
    return render(request, 'superadmin/unit_test_add_question.html', {'unit_test': unit_test})


@login_required
@user_passes_test(is_superadmin)
def unit_test_edit_question(request, question_id):
    """
    Edit a unit test question
    """
    from students.models import UnitTestQuestion
    
    question = get_object_or_404(UnitTestQuestion, id=question_id)
    
    if request.method == 'POST':
        question.question_text = request.POST.get('question_text')
        question.marks = request.POST.get('marks', 10)
        question.model_answer = request.POST.get('model_answer')
        
        key_points = request.POST.get('key_points', '')
        if key_points:
            key_points_list = [kp.strip() for kp in key_points.split('\n') if kp.strip()]
            question.key_points = key_points_list if key_points_list else None
        else:
            question.key_points = None
        
        question.save()
        
        return redirect('superadmin:unit_test_detail', test_id=question.unit_test.id)
    
    # Convert key points list to newline-separated string
    key_points_str = '\n'.join(question.key_points) if question.key_points else ''
    
    context = {
        'question': question,
        'key_points_str': key_points_str,
    }
    
    return render(request, 'superadmin/unit_test_edit_question.html', context)


@login_required
@user_passes_test(is_superadmin)
def unit_test_delete_question(request, question_id):
    """
    Delete a unit test question
    """
    from students.models import UnitTestQuestion
    
    question = get_object_or_404(UnitTestQuestion, id=question_id)
    test_id = question.unit_test.id
    question.delete()
    
    return redirect('superadmin:unit_test_detail', test_id=test_id)


@login_required
@user_passes_test(is_superadmin)
def student_analytics(request):
    """
    View all students with their MCQ and Unit Test performance
    """
    from django.contrib.auth import get_user_model
    from students.models import QuizAttempt, UnitTestAttempt, QuizChapter
    from django.db.models import Count, Avg, Q
    
    User = get_user_model()
    
    # Get all students
    students = User.objects.filter(role='student').prefetch_related(
        'quiz_attempts', 'unit_test_attempts'
    )
    
    student_data = []
    
    for student in students:
        # MCQ Statistics
        mcq_attempts = QuizAttempt.objects.filter(student=student, status='completed')
        mcq_total = mcq_attempts.count()
        mcq_avg_score = mcq_attempts.aggregate(Avg('score_percentage'))['score_percentage__avg'] or 0
        
        # Unit Test Statistics
        unit_test_attempts = UnitTestAttempt.objects.filter(student=student, status='evaluated')
        unit_test_total = unit_test_attempts.count()
        unit_test_avg_score = unit_test_attempts.aggregate(Avg('overall_score'))['overall_score__avg'] or 0
        
        student_data.append({
            'student': student,
            'mcq_total': mcq_total,
            'mcq_avg_score': round(mcq_avg_score, 2),
            'unit_test_total': unit_test_total,
            'unit_test_avg_score': round(unit_test_avg_score, 2),
        })
    
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    
    context = {
        'student_data': student_data,
        'chapters': chapters,
    }
    
    return render(request, 'superadmin/student_analytics.html', context)


@login_required
@user_passes_test(is_superadmin)
def student_detail_analytics(request, student_id):
    """
    Detailed analytics for a specific student
    """
    from django.contrib.auth import get_user_model
    from students.models import QuizAttempt, UnitTestAttempt, QuizChapter
    from django.db.models import Avg
    
    User = get_user_model()
    student = get_object_or_404(User, id=student_id, role='student')
    
    # MCQ Performance by Chapter
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    mcq_chapter_performance = []
    
    for chapter in chapters:
        attempts = QuizAttempt.objects.filter(student=student, chapter=chapter, status='completed')
        if attempts.exists():
            avg_score = attempts.aggregate(Avg('score_percentage'))['score_percentage__avg']
            mcq_chapter_performance.append({
                'chapter': chapter,
                'attempts': attempts.count(),
                'avg_score': round(avg_score, 2),
                'best_score': attempts.order_by('-score_percentage').first().score_percentage,
                'latest_attempt': attempts.order_by('-started_at').first(),
            })
    
    # Unit Test Performance by Chapter
    unit_test_chapter_performance = []
    
    for chapter in chapters:
        attempts = UnitTestAttempt.objects.filter(
            student=student,
            unit_test__chapters=chapter,  # Changed from chapter to chapters
            status='evaluated'
        ).select_related('unit_test')
        
        if attempts.exists():
            avg_score = attempts.aggregate(Avg('overall_score'))['overall_score__avg']
            unit_test_chapter_performance.append({
                'chapter': chapter,
                'attempts': attempts.count(),
                'avg_score': round(avg_score, 2),
                'best_score': attempts.order_by('-overall_score').first().overall_score,
                'latest_attempt': attempts.order_by('-started_at').first(),
            })
    
    # Overall topic performance heatmap (from latest MCQ attempts)
    latest_mcq_attempt = QuizAttempt.objects.filter(student=student, status='completed').order_by('-started_at').first()
    mcq_topic_performance = latest_mcq_attempt.topic_performance if latest_mcq_attempt else {}
    
    # Latest Unit Test attempt topic performance
    latest_unit_test_attempt = UnitTestAttempt.objects.filter(student=student, status='evaluated').order_by('-started_at').first()
    unit_test_topic_performance = latest_unit_test_attempt.topic_performance if latest_unit_test_attempt else {}
    
    context = {
        'student': student,
        'mcq_chapter_performance': mcq_chapter_performance,
        'unit_test_chapter_performance': unit_test_chapter_performance,
        'mcq_topic_performance': mcq_topic_performance,
        'unit_test_topic_performance': unit_test_topic_performance,
    }
    
    return render(request, 'superadmin/student_detail_analytics.html', context)
