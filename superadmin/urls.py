from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_book, name='upload_book'),
    path('uploads/', views.upload_list, name='upload_list'),
    path('uploads/<int:upload_id>/', views.upload_detail, name='upload_detail'),
    path('uploads/<int:upload_id>/status/', views.upload_status, name='upload_status'),
]
