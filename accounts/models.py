from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

class CustomUserManager(BaseUserManager): 
    def create_user(self, email, name, role='student', password=None, **extra_fields): 
        if not email: 
            raise ValueError("Email is required") 
        email = self.normalize_email(email) 
        user = self.model(email=email, name=name, role=role, **extra_fields)
        user.set_password(password) 
        user.save() 
        return user 
    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True) 
        extra_fields.setdefault('is_superuser', True) 
        return self.create_user(email, name, role='super_admin', password=password, **extra_fields) 
class CustomUser(AbstractBaseUser, PermissionsMixin): 
    ROLE_STUDENT = "student" 
    ROLE_STAFF = "staff" 
    ROLE_SCHOOL_ADMIN = "school_admin" 
    ROLE_SUPER_ADMIN = "super_admin" 
    ROLE_CHOICES = [ 
        (ROLE_STUDENT, "Student"), 
        (ROLE_STAFF, "Staff"), 
        (ROLE_SCHOOL_ADMIN, "School Admin"), 
        (ROLE_SUPER_ADMIN, "Super Admin"), 
    ] 
    email = models.EmailField(unique=True) 
    name = models.CharField(max_length=150) 
    age = models.PositiveIntegerField(null=True, blank=True) 
    standard = models.CharField(max_length=10, null=True, blank=True)  # grade/class for students 
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_STUDENT) 
    is_active = models.BooleanField(default=True) 
    is_staff = models.BooleanField(default=False) 
    date_joined = models.DateTimeField(auto_now_add=True) 
    objects = CustomUserManager() 
    USERNAME_FIELD = "email" 
    REQUIRED_FIELDS = ["name"] 
    def __str__(self): 
        return f"{self.email} ({self.role})"