from django.db import models
from django.conf import settings

class UploadedBook(models.Model):
    STATUS_CHOICES = [
        ('queued','Queued'),
        ('processing','Processing'),
        ('done','Done'),
        ('failed','Failed'),
    ]

    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to='uploads/books/')
    original_filename = models.CharField(max_length=255)
    standard = models.CharField(max_length=20)
    subject = models.CharField(max_length=50)
    chapter = models.CharField(max_length=150)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    notes = models.TextField(blank=True, null=True)
    ingestion_job_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.standard} - {self.subject} - {self.chapter} ({self.original_filename})"
