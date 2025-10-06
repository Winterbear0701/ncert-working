from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

# Temporary placeholder views
def home_view(request):
    return render(request, 'base.html', {'message': 'Welcome to NCERT Project'})

def student_dashboard_view(request):
    return render(request, 'base.html', {'message': 'Student Dashboard - Coming Soon'})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    
    # Temporary placeholder routes
    path("", home_view, name="home"),
    path("dashboard/student/", student_dashboard_view, name="student_dashboard"),
    
    # Placeholder dashboard route for students
    # path("", include("students.urls")),  # Create 'students' app later
]
