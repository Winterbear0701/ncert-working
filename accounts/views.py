from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from .forms import CustomUserCreationForm, CustomAuthenticationForm


def register_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            # Redirect based on user role
            if user.role == "student":
                return redirect("student_dashboard")
            return redirect("home")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/register.html", {"form": form})


class MyLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = CustomAuthenticationForm


def logout_view(request):
    logout(request)
    return redirect("accounts:login")
