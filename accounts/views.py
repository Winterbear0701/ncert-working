from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from .forms import CustomUserCreationForm, CustomAuthenticationForm


def register_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # Always assign student role during registration
            user.role = "student"
            user.save()
            login(request, user)
            
            # Always redirect students to their dashboard
            return redirect("students:student_dashboard")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/register.html", {"form": form})


class MyLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = CustomAuthenticationForm
    
    def get_success_url(self):
        """Redirect based on user role after login"""
        user = self.request.user
        if user.role == 'super_admin':
            return '/superadmin/'
        else:
            return '/students/dashboard/'


def logout_view(request):
    logout(request)
    return redirect("accounts:login")
