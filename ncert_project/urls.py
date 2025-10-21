from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.conf import settings
from django.conf.urls.static import static

# Home view
def home_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'role') and request.user.role == 'super_admin':
            from django.shortcuts import redirect
            return redirect('superadmin:dashboard')
        else:
            from django.shortcuts import redirect
            return redirect('students:student_dashboard')
    return render(request, 'home.html')

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("students/", include("students.urls")),
    path("superadmin/", include("superadmin.urls")),
    path("", home_view, name="home"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
