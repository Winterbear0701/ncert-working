from django.db import models
from django.conf import settings

class ChatHistory(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    model_used = models.CharField(max_length=20, default='openai')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.email} - {self.question[:30]}"
