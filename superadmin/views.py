import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
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
    from django.contrib.auth import get_user_model
    from students.models import QuizAttempt, UnitTestAttempt, ChatHistory
    
    User = get_user_model()
    
    # Book Upload Statistics
    total_uploads = UploadedBook.objects.count()
    queued = UploadedBook.objects.filter(status='queued').count()
    processing = UploadedBook.objects.filter(status='processing').count()
    completed = UploadedBook.objects.filter(status='done').count()
    failed = UploadedBook.objects.filter(status='failed').count()
    
    recent_uploads = UploadedBook.objects.all().order_by('-uploaded_at')[:10]
    
    # Student Analytics Statistics
    total_students = User.objects.filter(role='student').count()
    
    # MCQ Statistics - count unique students who completed at least one quiz
    total_mcq_attempts = QuizAttempt.objects.filter(status='completed').count()
    students_attempted_mcq = QuizAttempt.objects.filter(status='completed').values('student').distinct().count()
    
    # Unit Test Statistics - count unique students who completed at least one test
    total_unit_test_attempts = UnitTestAttempt.objects.filter(status='evaluated').count()
    students_attempted_unit_test = UnitTestAttempt.objects.filter(status='evaluated').values('student').distinct().count()
    
    # Chat/AI Tutor Statistics
    total_chat_sessions = ChatHistory.objects.count()
    students_used_chat = ChatHistory.objects.values('student').distinct().count()
    
    context = {
        # Book stats
        'total_uploads': total_uploads,
        'queued': queued,
        'processing': processing,
        'completed': completed,
        'failed': failed,
        'recent_uploads': recent_uploads,
        
        # Student stats
        'total_students': total_students,
        'total_mcq_attempts': total_mcq_attempts,
        'students_attempted_mcq': students_attempted_mcq,
        'total_unit_test_attempts': total_unit_test_attempts,
        'students_attempted_unit_test': students_attempted_unit_test,
        'total_chat_sessions': total_chat_sessions,
        'students_used_chat': students_used_chat,
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
@require_POST
def delete_upload(request, upload_id):
    """
    Delete an uploaded book and all related data (ChromaDB chunks, quizzes, etc.)
    """
    import os
    from django.conf import settings
    from students.models import QuizChapter, QuizQuestion, QuestionVariant, QuizAttempt, QuizAnswer
    from ncert_project.chromadb_utils import get_chromadb_manager
    
    upload = get_object_or_404(UploadedBook, id=upload_id)
    
    try:
        # Store info for logging
        filename = upload.original_filename
        chapter_info = f"{upload.standard} - {upload.subject} - {upload.chapter}"
        
        # 1. Delete from ChromaDB (PDF chunks and embeddings)
        try:
            chroma_manager = get_chromadb_manager()
            
            # Delete chunks matching this upload
            chroma_manager.collection.delete(
                where={
                    "$and": [
                        {"standard": {"$eq": str(upload.standard)}},
                        {"subject": {"$eq": upload.subject}},
                        {"chapter": {"$eq": upload.chapter}}
                    ]
                }
            )
            logger.info(f"🗑️  Deleted ChromaDB chunks for {chapter_info}")
        except Exception as e:
            logger.warning(f"⚠️  Could not delete ChromaDB data: {e}")
        
        # 2. Delete related quiz data
        try:
            # Find chapters matching this upload
            chapters = QuizChapter.objects.filter(
                class_number=f"Class {upload.standard}",
                subject=upload.subject,
                chapter_name=upload.chapter
            )
            
            for chapter in chapters:
                # Delete quiz attempts and answers
                QuizAnswer.objects.filter(attempt__chapter=chapter).delete()
                QuizAttempt.objects.filter(chapter=chapter).delete()
                
                # Delete question variants and questions
                QuestionVariant.objects.filter(question__chapter=chapter).delete()
                QuizQuestion.objects.filter(chapter=chapter).delete()
                
                # Delete chapter
                chapter.delete()
                
            logger.info(f"🗑️  Deleted {chapters.count()} quiz chapters and related data")
        except Exception as e:
            logger.warning(f"⚠️  Could not delete quiz data: {e}")
        
        # 3. Delete physical PDF file
        try:
            if upload.file and os.path.exists(upload.file.path):
                os.remove(upload.file.path)
                logger.info(f"🗑️  Deleted PDF file: {upload.file.path}")
        except Exception as e:
            logger.warning(f"⚠️  Could not delete PDF file: {e}")
        
        # 4. Delete upload record from database
        upload.delete()
        
        messages.success(request, f'✅ Successfully deleted "{filename}" and all related data (PDF, quizzes, ChromaDB chunks)')
        logger.info(f"✅ Successfully deleted upload: {filename} ({chapter_info})")
        
    except Exception as e:
        logger.error(f"❌ Error deleting upload {upload_id}: {e}")
        messages.error(request, f'Error deleting upload: {str(e)}')
    
    return redirect('superadmin:upload_list')


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
def get_subjects_api(request):
    """
    API endpoint to get subjects by class from MongoDB book_chapters
    """
    from ncert_project.mongodb_utils import get_mongo_db
    
    class_num = request.GET.get('class')
    if not class_num:
        return JsonResponse({'subjects': []})
    
    try:
        # Normalize class format
        class_normalized = f"Class {class_num}" if not str(class_num).lower().startswith('class') else str(class_num)
        
        # Get MongoDB connection
        db = get_mongo_db()
        
        # Query book_chapters collection (saved during PDF upload)
        book_chapters = db.book_chapters
        
        # Get distinct subjects for this class
        subjects = book_chapters.distinct('subject', {'class_number': class_normalized})
        
        # Sort subjects
        subjects = sorted(subjects) if subjects else []
        
        logger.info(f"📚 Found {len(subjects)} subjects for {class_normalized} from book_chapters")
        
        return JsonResponse({'subjects': subjects})
    
    except Exception as e:
        logger.exception(f"Error getting subjects: {e}")
        return JsonResponse({'subjects': [], 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_superadmin)
def get_chapters_api(request):
    """
    API endpoint to get chapters by class and subject from MongoDB book_chapters
    """
    from ncert_project.mongodb_utils import get_mongo_db
    
    class_num = request.GET.get('class')
    subject = request.GET.get('subject')
    
    if not class_num or not subject:
        return JsonResponse({'chapters': []})
    
    try:
        # Normalize class format
        class_normalized = f"Class {class_num}" if not str(class_num).lower().startswith('class') else str(class_num)
        
        # Get MongoDB connection
        db = get_mongo_db()
        
        # Query book_chapters collection (saved during PDF upload)
        book_chapters = db.book_chapters
        
        # Get chapters for this class and subject
        chapters_cursor = book_chapters.find(
            {
                'class_number': class_normalized,
                'subject': subject
            },
            {
                '_id': 1,
                'chapter_id': 1,
                'chapter_number': 1,
                'chapter_name': 1
            }
        ).sort('chapter_number', 1)  # Sort by chapter number
        
        # Format chapter list
        chapter_list = []
        for ch in chapters_cursor:
            chapter_num = ch.get('chapter_number', '?')
            chapter_name = ch.get('chapter_name', 'Unknown')
            
            chapter_list.append({
                'id': ch.get('chapter_id', str(ch.get('_id'))),
                'name': chapter_name  # Use full chapter name (already has "Chapter X:" format)
            })
        
        logger.info(f"📖 Found {len(chapter_list)} chapters for {class_normalized} - {subject}")
        
        return JsonResponse({'chapters': chapter_list})
    
    except Exception as e:
        logger.exception(f"Error getting chapters: {e}")
        return JsonResponse({'chapters': [], 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_superadmin)
def get_saved_questions_api(request):
    """Return saved questions from centralized MongoDB question bank.

    Query params: class, subject, chapter_id, q (search text)
    """
    try:
        from . import mongo_questions
    except Exception:
        return JsonResponse({'questions': []})

    class_num = request.GET.get('class')
    subject = request.GET.get('subject')
    chapter_id = request.GET.get('chapter_id')
    q = request.GET.get('q', '')

    class_normalized = None
    if class_num:
        class_normalized = f'Class {class_num}' if not str(class_num).lower().startswith('class') else str(class_num)

    results = mongo_questions.search_questions(class_name=class_normalized or '', subject=subject or '', chapter_id=chapter_id or None, query=q, limit=100)
    return JsonResponse({'questions': results})


@login_required
@user_passes_test(is_superadmin)
def saved_questions_manage(request):
    """Render the saved questions management page."""
    return render(request, 'superadmin/saved_questions.html', {})


@login_required
@user_passes_test(is_superadmin)
def unit_test_create(request):
    """
    Create a new unit test with questions organized by marks
    """
    from students.models import UnitTest, UnitTestQuestion, QuizChapter
    import json
    
    if request.method == 'POST':
        # Basic form fields
        title = request.POST.get('title')
        class_num = request.POST.get('class')
        subject = request.POST.get('subject')
        chapter_ids = request.POST.getlist('chapters')
        total_marks_type = int(request.POST.get('total_marks_type', 80))
        total_marks = int(request.POST.get('total_marks', total_marks_type))
        duration_minutes = int(request.POST.get('duration_minutes', 60))
        passing_marks = int(request.POST.get('passing_marks', 40))

        # Parse questions from POST data
        questions_data = []
        question_index = 0
        while True:
            question_text = request.POST.get(f'questions[{question_index}][text]')
            if not question_text:
                break
            questions_data.append({
                'text': question_text,
                'answer': request.POST.get(f'questions[{question_index}][answer]', ''),
                'marks': int(request.POST.get(f'questions[{question_index}][marks]', 1))
            })
            question_index += 1

        # Define required distributions for each test type
        required_distributions = {
            80: {1: 20, 2: 6, 3: 7, 4: 3, 5: 3},  # Full test
            50: {1: 15, 2: 4, 3: 4, 4: 2, 5: 2},  # Half test
            0: {}  # Practice test - no restrictions
        }

        # Enforce distribution only if not a practice test
        if total_marks_type > 0:
            required = required_distributions.get(total_marks_type, {})
            counts = {}
            for q in questions_data:
                counts[q['marks']] = counts.get(q['marks'], 0) + 1

            mismatch = []
            for mark, req in required.items():
                if counts.get(mark, 0) != req:
                    mismatch.append(f"{mark}-mark: expected {req}, got {counts.get(mark,0)}")

            if mismatch:
                messages.error(request, 'Question distribution mismatch: ' + '; '.join(mismatch))
                class_list = ['Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10']
                return render(request, 'superadmin/unit_test_create_new.html', {
                    'class_list': class_list,
                    'error': 'Question distribution incorrect: ' + '; '.join(mismatch)
                })

        # Validate total marks
        computed_total = sum(q['marks'] for q in questions_data)
        if total_marks_type > 0 and computed_total != total_marks_type:
            messages.error(request, f'Total marks must be {total_marks_type} (computed {computed_total})')
            class_list = ['Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10']
            return render(request, 'superadmin/unit_test_create_new.html', {
                'class_list': class_list,
                'error': f'Total marks must be {total_marks_type} (computed {computed_total})'
            })
        
        # Get chapter names from MongoDB for description
        chapter_names = []
        if chapter_ids:
            from ncert_project.mongodb_utils import get_mongo_db
            db = get_mongo_db()
            for chapter_id in chapter_ids:
                chapter_doc = db.book_chapters.find_one({'chapter_id': chapter_id})
                if chapter_doc:
                    chapter_names.append(chapter_doc.get('chapter_name', chapter_id))
        
        # Create descriptive text with chapters
        chapters_text = ", ".join(chapter_names) if chapter_names else "Multiple Chapters"
        description_text = f"Class {class_num} - {subject} - {chapters_text}"

        # Create unit test
        unit_test = UnitTest.objects.create(
            title=title,
            description=description_text,
            total_marks=computed_total,
            duration_minutes=duration_minutes,
            passing_marks=passing_marks,
            is_active=True,
            created_by=request.user
        )

        # Note: We don't set chapters relationship here because chapter_ids are strings
        # from book_chapters collection, not QuizChapter model IDs
        # The chapter information is stored in the description and MongoDB questions

        # Create questions and save to centralized MongoDB
        try:
            from . import mongo_questions
        except Exception:
            mongo_questions = None

        for idx, q_data in enumerate(questions_data, start=1):
            UnitTestQuestion.objects.create(
                unit_test=unit_test,
                question_number=idx,
                question_text=q_data['text'],
                model_answer=q_data['answer'],
                marks=q_data['marks']
            )

            # Save to MongoDB question bank (best-effort)
            if mongo_questions:
                payload = {
                    'class': f'Class {class_num}' if not str(class_num).lower().startswith('class') else str(class_num),
                    'subject': subject,
                    'chapter_id': chapter_ids[0] if chapter_ids else None,  # Keep as string (e.g., "class_5_mathematics_chapter_1")
                    'chapter_title': '',
                    'question': q_data['text'],
                    'answer': q_data['answer'],
                    'marks': q_data['marks'],
                    'created_by': request.user.email if hasattr(request.user, 'email') else str(request.user)
                }
                try:
                    mongo_questions.save_question(payload)
                except Exception:
                    # swallow Mongo errors, this is non-critical
                    logger.exception('Failed to save question to MongoDB')

        messages.success(request, f'Unit test "{title}" created successfully with {len(questions_data)} questions!')
        return redirect('superadmin:unit_test_detail', test_id=unit_test.id)
    
    # GET request - show form
    class_list = ['Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10']
    
    return render(request, 'superadmin/unit_test_create_new.html', {
        'class_list': class_list
    })


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
@login_required
@user_passes_test(is_superadmin)
@require_POST
def unit_test_delete_question(request, question_id):
    """
    Delete a unit test question
    """
    from students.models import UnitTestQuestion
    
    try:
        question = get_object_or_404(UnitTestQuestion, id=question_id)
        question.delete()
        
        return JsonResponse({'success': True, 'message': 'Question deleted successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_superadmin)
@require_POST
def unit_test_delete(request, test_id):
    """
    Delete an entire unit test and all its questions
    """
    from students.models import UnitTest
    
    try:
        unit_test = get_object_or_404(UnitTest, id=test_id)
        
        # Delete associated questions (cascade should handle this, but being explicit)
        unit_test.questions.all().delete()
        
        # Delete the test
        unit_test.delete()
        
        return JsonResponse({'success': True, 'message': 'Unit test deleted successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_superadmin)
@require_POST
def unit_test_toggle_status(request, test_id):
    """
    Toggle unit test active/inactive status
    """
    from students.models import UnitTest
    
    try:
        unit_test = get_object_or_404(UnitTest, id=test_id)
        unit_test.is_active = not unit_test.is_active
        unit_test.save()
        
        return JsonResponse({
            'success': True, 
            'is_active': unit_test.is_active,
            'message': f'Test {"activated" if unit_test.is_active else "deactivated"} successfully'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_superadmin)
def student_analytics(request):
    """
    View all students with their MCQ and Unit Test performance
    """
    from django.contrib.auth import get_user_model
    from students.models import QuizAttempt, UnitTestAttempt, QuizChapter
    from django.db.models import Count, Avg, Q, Sum
    
    User = get_user_model()
    
    # Get all students
    students = User.objects.filter(role='student').prefetch_related(
        'quiz_attempts', 'unit_test_attempts'
    )
    
    student_data = []
    
    for student in students:
        # MCQ Statistics - Count submitted and verified quizzes
        mcq_attempts = QuizAttempt.objects.filter(student=student, status__in=['submitted', 'verified'])
        mcq_total = mcq_attempts.count()
        mcq_avg_score = mcq_attempts.aggregate(Avg('score_percentage'))['score_percentage__avg'] or 0
        
        # Unit Test Statistics - Only count evaluated tests
        unit_test_attempts = UnitTestAttempt.objects.filter(student=student, status='evaluated')
        unit_test_total = unit_test_attempts.count()
        unit_test_avg_score = unit_test_attempts.aggregate(Avg('overall_score'))['overall_score__avg'] or 0
        
        # Overall Performance Score (weighted average)
        # If student has both MCQ and unit tests, weight equally
        # If only one type exists, use that
        overall_performance = 0
        if mcq_total > 0 and unit_test_total > 0:
            overall_performance = (mcq_avg_score + unit_test_avg_score) / 2
        elif mcq_total > 0:
            overall_performance = mcq_avg_score
        elif unit_test_total > 0:
            overall_performance = unit_test_avg_score
        
        student_data.append({
            'student': student,
            'mcq_total': mcq_total,
            'mcq_avg_score': round(mcq_avg_score, 2),
            'unit_test_total': unit_test_total,
            'unit_test_avg_score': round(unit_test_avg_score, 2),
            'overall_performance': round(overall_performance, 2),
        })
    
    # Sort by overall performance (descending)
    student_data.sort(key=lambda x: x['overall_performance'], reverse=True)
    
    chapters = QuizChapter.objects.all().order_by('chapter_number')
    
    # Summary statistics
    total_students = len(student_data)
    students_with_mcq = sum(1 for s in student_data if s['mcq_total'] > 0)
    students_with_unit_test = sum(1 for s in student_data if s['unit_test_total'] > 0)
    avg_overall_performance = sum(s['overall_performance'] for s in student_data) / total_students if total_students > 0 else 0
    
    context = {
        'student_data': student_data,
        'chapters': chapters,
        'total_students': total_students,
        'students_with_mcq': students_with_mcq,
        'students_with_unit_test': students_with_unit_test,
        'avg_overall_performance': round(avg_overall_performance, 2),
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
        attempts = QuizAttempt.objects.filter(student=student, chapter=chapter, status__in=['submitted', 'verified'])
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
