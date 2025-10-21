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


# ==================== QUIZ SYSTEM MODELS ====================

class QuizChapter(models.Model):
    """
    Represents a chapter with quiz questions
    Auto-generated when book is uploaded
    """
    chapter_id = models.CharField(max_length=255, unique=True, db_index=True)  # e.g., "class_5_math_chapter_1"
    class_number = models.CharField(max_length=10)
    subject = models.CharField(max_length=100)
    chapter_number = models.IntegerField()
    chapter_name = models.CharField(max_length=255)
    chapter_order = models.IntegerField(help_text="Sequential order for unlocking")
    is_active = models.BooleanField(default=True)
    total_questions = models.IntegerField(default=10)
    passing_percentage = models.IntegerField(default=70)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.class_number} - {self.subject} - {self.chapter_name}"
    
    class Meta:
        ordering = ['class_number', 'subject', 'chapter_order']
        indexes = [
            models.Index(fields=['chapter_id']),
            models.Index(fields=['class_number', 'subject', 'chapter_order']),
        ]


class QuizQuestion(models.Model):
    """
    Quiz questions with multiple variants for re-attempts
    Generated from ChromaDB RAG content
    """
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    chapter = models.ForeignKey(QuizChapter, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField()  # 1-10
    topic = models.CharField(max_length=255)  # e.g., "Triangles", "Photosynthesis"
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    rag_context = models.TextField(help_text="ChromaDB content used to generate this question")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.chapter.chapter_name} - Q{self.question_number} - {self.topic}"
    
    class Meta:
        ordering = ['chapter', 'question_number']
        unique_together = ['chapter', 'question_number']


class QuestionVariant(models.Model):
    """
    Multiple variants of the same question for re-attempts
    Same concept, different wording
    """
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='variants')
    variant_number = models.IntegerField()  # 1, 2, 3...
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_answer = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])
    explanation = models.TextField(help_text="Why this answer is correct")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.question} - Variant {self.variant_number}"
    
    class Meta:
        ordering = ['question', 'variant_number']
        unique_together = ['question', 'variant_number']


class StudentChapterProgress(models.Model):
    """
    Tracks student's progress through chapters
    Manages progressive unlocking
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chapter_progress')
    chapter = models.ForeignKey(QuizChapter, on_delete=models.CASCADE)
    is_unlocked = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    best_score = models.IntegerField(default=0)
    total_attempts = models.IntegerField(default=0)
    last_attempt_date = models.DateTimeField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.student.email} - {self.chapter.chapter_name} - Score: {self.best_score}%"
    
    class Meta:
        unique_together = ['student', 'chapter']
        ordering = ['student', 'chapter__chapter_order']


class QuizAttempt(models.Model):
    """
    Records each quiz attempt by a student
    Stores all answers and verification results
    """
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
    ]
    
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    chapter = models.ForeignKey(QuizChapter, on_delete=models.CASCADE)
    attempt_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    current_question_number = models.IntegerField(default=1)
    
    # Results
    total_questions = models.IntegerField(default=10)
    correct_answers = models.IntegerField(default=0)
    score_percentage = models.IntegerField(default=0)
    is_passed = models.BooleanField(default=False)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_time_seconds = models.IntegerField(default=0)
    
    # Topic performance (JSON field for heatmap)
    topic_performance = models.JSONField(null=True, blank=True)
    
    # AI Feedback
    feedback_message = models.TextField(null=True, blank=True, help_text="AI-generated feedback on topic performance")
    
    def __str__(self):
        return f"{self.student.email} - {self.chapter.chapter_name} - Attempt {self.attempt_number}"
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['student', 'chapter', '-started_at']),
        ]


class QuizAnswer(models.Model):
    """
    Individual answer for each question in a quiz attempt
    """
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    variant_used = models.ForeignKey(QuestionVariant, on_delete=models.CASCADE)
    
    # Student's response
    selected_answer = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])
    is_correct = models.BooleanField(default=False)
    time_taken_seconds = models.IntegerField(default=0)
    
    # RAG Verification
    verification_status = models.CharField(max_length=50, default='pending')  # pending, verified_by_rag, no_rag_content
    ai_explanation = models.TextField(null=True, blank=True)
    rag_confidence = models.FloatField(null=True, blank=True)  # 0.0 to 1.0
    
    answered_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.attempt} - Q{self.question.question_number} - {'✓' if self.is_correct else '✗'}"
    
    class Meta:
        ordering = ['attempt', 'question__question_number']
        unique_together = ['attempt', 'question']


# ==================== UNIT TEST MODELS ====================

class UnitTest(models.Model):
    """
    Subjective/Essay-type test created by admin
    Can cover multiple chapters
    """
    title = models.CharField(max_length=255)
    chapters = models.ManyToManyField(QuizChapter, related_name='unit_tests')
    description = models.TextField(blank=True)
    
    # Test settings
    total_marks = models.IntegerField(default=100)
    duration_minutes = models.IntegerField(default=60)
    passing_marks = models.IntegerField(default=40)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        chapter_names = ", ".join([ch.chapter_name for ch in self.chapters.all()[:3]])
        if self.chapters.count() > 3:
            chapter_names += "..."
        return f"{self.title} - {chapter_names}"
    
    def get_chapters_display(self):
        """Get formatted string of all chapters"""
        return ", ".join([f"Ch{ch.chapter_number}" for ch in self.chapters.all().order_by('chapter_number')])
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at']),
        ]


class UnitTestQuestion(models.Model):
    """
    Individual question in a unit test with model answer
    """
    unit_test = models.ForeignKey(UnitTest, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField()
    
    # Question details
    question_text = models.TextField()
    marks = models.IntegerField(default=10)
    
    # Model answer provided by admin
    model_answer = models.TextField(help_text="Expected answer from students")
    
    # Evaluation criteria (optional)
    key_points = models.JSONField(null=True, blank=True, help_text="Key points that should be in answer")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.unit_test.title} - Q{self.question_number}"
    
    class Meta:
        ordering = ['unit_test', 'question_number']
        unique_together = ['unit_test', 'question_number']


class UnitTestAttempt(models.Model):
    """
    Student's attempt at a unit test
    """
    unit_test = models.ForeignKey(UnitTest, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='unit_test_attempts')
    
    # Attempt details
    attempt_number = models.IntegerField(default=1)
    
    # Scores
    total_marks_obtained = models.FloatField(default=0)
    content_score = models.FloatField(default=0, help_text="Score based on content match")
    grammar_score = models.FloatField(default=0, help_text="Score based on grammar quality")
    overall_score = models.FloatField(default=0, help_text="Combined final score")
    
    # Topic-wise performance for heatmap
    topic_performance = models.JSONField(default=dict, blank=True)
    
    # Status
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('evaluated', 'Evaluated'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    
    # Feedback
    overall_feedback = models.TextField(null=True, blank=True)
    strengths = models.TextField(null=True, blank=True)
    improvements = models.TextField(null=True, blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    time_taken_seconds = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.student.email} - {self.unit_test.title} - Attempt {self.attempt_number}"
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['student', 'unit_test', '-started_at']),
        ]


class UnitTestAnswer(models.Model):
    """
    Student's answer to a unit test question
    """
    attempt = models.ForeignKey(UnitTestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(UnitTestQuestion, on_delete=models.CASCADE)
    
    # Student's answer
    answer_text = models.TextField()
    
    # AI Evaluation scores
    content_score = models.FloatField(default=0, help_text="How well content matches model answer")
    grammar_score = models.FloatField(default=0, help_text="Grammar and language quality")
    marks_obtained = models.FloatField(default=0)
    
    # AI Feedback
    content_feedback = models.TextField(null=True, blank=True)
    grammar_feedback = models.TextField(null=True, blank=True)
    overall_feedback = models.TextField(null=True, blank=True)
    
    # Key points matched
    key_points_covered = models.JSONField(null=True, blank=True)
    key_points_missed = models.JSONField(null=True, blank=True)
    
    # Evaluation metadata
    evaluated_at = models.DateTimeField(null=True, blank=True)
    evaluation_model = models.CharField(max_length=50, default='gemini')
    
    answered_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.attempt} - Q{self.question.question_number}"
    
    class Meta:
        ordering = ['attempt', 'question__question_number']
        unique_together = ['attempt', 'question']


# ==================== PREVIOUS YEAR PAPER ANALYSIS ====================

class PreviousYearPaper(models.Model):
    """
    Student uploads previous year question papers for analysis
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_papers')
    
    # Paper details
    title = models.CharField(max_length=255, help_text="e.g., 2023 Board Exam, Sample Paper 1")
    standard = models.CharField(max_length=10, help_text="e.g., 10")
    subject = models.CharField(max_length=100, help_text="e.g., Science, Mathematics")
    exam_type = models.CharField(max_length=100, default="Board Exam", help_text="e.g., Board Exam, Sample Paper")
    year = models.IntegerField(null=True, blank=True, help_text="Exam year")
    
    # File
    pdf_file = models.FileField(upload_to='previous_year_papers/')
    
    # Processing status
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('analyzed', 'Analyzed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    
    # Extracted data
    extracted_text = models.TextField(null=True, blank=True)
    total_questions = models.IntegerField(default=0)
    questions_list = models.JSONField(null=True, blank=True, help_text="Extracted questions")
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.standard} {self.subject}"
    
    class Meta:
        ordering = ['-uploaded_at']


class PaperAnalysis(models.Model):
    """
    Analysis results for uploaded previous year papers
    Fast probability-based analysis using RAG
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paper_analyses')
    
    # Papers included in analysis
    papers = models.ManyToManyField(PreviousYearPaper, related_name='analyses')
    
    # Analysis parameters
    standard = models.CharField(max_length=10)
    subject = models.CharField(max_length=100)
    total_papers_analyzed = models.IntegerField(default=0)
    total_questions_analyzed = models.IntegerField(default=0)
    
    # Analysis results (JSON format for fast access)
    chapter_importance = models.JSONField(default=dict, help_text="Chapter-wise importance scores")
    topic_importance = models.JSONField(default=dict, help_text="Topic-wise importance scores")
    question_frequency = models.JSONField(default=dict, help_text="Question type frequency")
    
    # Recommendations
    priority_chapters = models.JSONField(default=list, help_text="Top priority chapters to study")
    priority_topics = models.JSONField(default=list, help_text="Top priority topics")
    study_strategy = models.JSONField(default=dict, help_text="Personalized study strategy")
    
    # Study time estimates
    estimated_study_hours = models.FloatField(default=0, help_text="Estimated hours needed")
    
    # Metadata
    analysis_completed_at = models.DateTimeField(auto_now_add=True)
    processing_time_seconds = models.FloatField(default=0)
    
    def __str__(self):
        return f"Analysis for {self.student.email} - {self.standard} {self.subject}"
    
    class Meta:
        ordering = ['-analysis_completed_at']
        verbose_name_plural = "Paper Analyses"

