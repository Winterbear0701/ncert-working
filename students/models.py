from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class ChatHistory(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    model_used = models.CharField(max_length=20, default='openai')
    created_at = models.DateTimeField(auto_now_add=True)
    # New fields for enhanced features
    has_images = models.BooleanField(default=False)
    sources = models.JSONField(null=True, blank=True)  # Store reference links
    difficulty_level = models.CharField(max_length=20, default='normal')  # simple, normal, advanced

    def __str__(self):
        return f"{self.student.email} - {self.question[:30]}"

    class Meta:
        verbose_name_plural = "Chat Histories"
        ordering = ['-created_at']


class ChatCache(models.Model):
    """
    Auto-expiring cache for frequently asked questions
    Entries older than 10 days are automatically deleted
    """
    question_hash = models.CharField(max_length=64, unique=True, db_index=True)  # MD5 hash of normalized question
    question = models.TextField()
    answer = models.TextField()
    images = models.JSONField(null=True, blank=True)  # List of image URLs/paths
    sources = models.JSONField(null=True, blank=True)  # Reference links
    difficulty_level = models.CharField(max_length=20, default='normal')
    hit_count = models.IntegerField(default=0)  # Track how many times used
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Cache: {self.question[:50]}"

    def save(self, *args, **kwargs):
        # Set expiration date to 10 days from now
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=10)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def get_active_cache(cls, question_hash):
        """Get non-expired cache entry"""
        try:
            cache = cls.objects.get(question_hash=question_hash)
            if cache.is_expired():
                cache.delete()
                return None
            cache.hit_count += 1
            cache.save()
            return cache
        except cls.DoesNotExist:
            return None

    class Meta:
        verbose_name_plural = "Chat Caches"
        ordering = ['-created_at']


class PermanentMemory(models.Model):
    """
    User-specific permanent memory storage
    Saved when user says 'save/remember this'
    Deleted when user says 'forget/remove this'
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    images = models.JSONField(null=True, blank=True)
    sources = models.JSONField(null=True, blank=True)
    keywords = models.TextField(help_text="Keywords for quick search")
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    access_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.student.email} - Memory: {self.question[:30]}"

    class Meta:
        verbose_name_plural = "Permanent Memories"
        ordering = ['-last_accessed']
        indexes = [
            models.Index(fields=['student', '-last_accessed']),
        ]


class PDFImage(models.Model):
    """
    Images extracted from uploaded PDFs
    Linked to specific chunks in ChromaDB
    """
    upload = models.ForeignKey('superadmin.UploadedBook', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='pdf_images/')
    page_number = models.IntegerField()
    chunk_id = models.CharField(max_length=255, null=True, blank=True)  # Link to ChromaDB chunk
    caption = models.TextField(null=True, blank=True)
    image_type = models.CharField(max_length=50, default='diagram')  # diagram, chart, table, illustration
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image from {self.upload.original_filename} - Page {self.page_number}"

    class Meta:
        ordering = ['upload', 'page_number']
