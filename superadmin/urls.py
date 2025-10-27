from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_book, name='upload_book'),
    path('uploads/', views.upload_list, name='upload_list'),
    path('uploads/<int:upload_id>/', views.upload_detail, name='upload_detail'),
    path('uploads/<int:upload_id>/status/', views.upload_status, name='upload_status'),
    path('uploads/<int:upload_id>/delete/', views.delete_upload, name='delete_upload'),
    
    # API Endpoints
    path('api/get-subjects/', views.get_subjects_api, name='get_subjects_api'),
    path('api/get-chapters/', views.get_chapters_api, name='get_chapters_api'),
    
    # Unit Test Management
    path('unit-tests/', views.unit_test_list, name='unit_test_list'),
    path('unit-tests/create/', views.unit_test_create, name='unit_test_create'),
    path('unit-tests/upload/', views.unit_test_upload_questions, name='unit_test_upload_questions'),
    path('unit-tests/preview/', views.unit_test_preview_upload, name='unit_test_preview_upload'),
    path('unit-tests/<int:test_id>/', views.unit_test_detail, name='unit_test_detail'),
    path('unit-tests/<int:test_id>/add-question/', views.unit_test_add_question, name='unit_test_add_question'),
    path('unit-tests/questions/<int:question_id>/edit/', views.unit_test_edit_question, name='unit_test_edit_question'),
    path('unit-tests/questions/<int:question_id>/delete/', views.unit_test_delete_question, name='unit_test_delete_question'),
    
    # Student Analytics
    path('analytics/students/', views.student_analytics, name='student_analytics'),
    path('analytics/students/<int:student_id>/', views.student_detail_analytics, name='student_detail_analytics'),
]
