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
