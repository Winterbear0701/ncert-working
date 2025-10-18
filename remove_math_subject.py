"""
Remove Mathematics subject and chapter from database
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from students.models import QuizChapter, QuizQuestion, QuestionVariant, QuizAttempt, QuizAnswer, StudentChapterProgress

print("="*70)
print("🗑️  REMOVING MATHEMATICS SUBJECT")
print("="*70)

# Find Math chapters
math_chapters = QuizChapter.objects.filter(subject='Mathematics')

print(f"\n📚 Found {math_chapters.count()} Mathematics chapters:")
for ch in math_chapters:
    print(f"   • {ch.chapter_name} (ID: {ch.chapter_id})")

if math_chapters.exists():
    # Get counts before deletion
    question_count = QuizQuestion.objects.filter(chapter__in=math_chapters).count()
    variant_count = QuestionVariant.objects.filter(question__chapter__in=math_chapters).count()
    attempt_count = QuizAttempt.objects.filter(chapter__in=math_chapters).count()
    answer_count = QuizAnswer.objects.filter(attempt__chapter__in=math_chapters).count()
    progress_count = StudentChapterProgress.objects.filter(chapter__in=math_chapters).count()
    
    print(f"\n📊 Related data to be deleted:")
    print(f"   • Questions: {question_count}")
    print(f"   • Question Variants: {variant_count}")
    print(f"   • Quiz Attempts: {attempt_count}")
    print(f"   • Quiz Answers: {answer_count}")
    print(f"   • Student Progress: {progress_count}")
    
    print(f"\n⚠️  This will DELETE all Mathematics chapters and related data!")
    confirm = input("\nType 'DELETE' to confirm: ")
    
    if confirm == 'DELETE':
        print("\n🗑️  Deleting...")
        
        # Delete in correct order (due to foreign keys)
        # 1. Delete answers first
        deleted_answers = QuizAnswer.objects.filter(attempt__chapter__in=math_chapters).delete()
        print(f"   ✅ Deleted {deleted_answers[0]} quiz answers")
        
        # 2. Delete attempts
        deleted_attempts = QuizAttempt.objects.filter(chapter__in=math_chapters).delete()
        print(f"   ✅ Deleted {deleted_attempts[0]} quiz attempts")
        
        # 3. Delete student progress
        deleted_progress = StudentChapterProgress.objects.filter(chapter__in=math_chapters).delete()
        print(f"   ✅ Deleted {deleted_progress[0]} student progress records")
        
        # 4. Delete question variants
        deleted_variants = QuestionVariant.objects.filter(question__chapter__in=math_chapters).delete()
        print(f"   ✅ Deleted {deleted_variants[0]} question variants")
        
        # 5. Delete questions
        deleted_questions = QuizQuestion.objects.filter(chapter__in=math_chapters).delete()
        print(f"   ✅ Deleted {deleted_questions[0]} questions")
        
        # 6. Finally, delete chapters
        deleted_chapters = math_chapters.delete()
        print(f"   ✅ Deleted {deleted_chapters[0]} chapters")
        
        print("\n" + "="*70)
        print("✅ MATHEMATICS SUBJECT REMOVED SUCCESSFULLY")
        print("="*70)
        
        # Show remaining chapters
        remaining = QuizChapter.objects.all()
        print(f"\n📚 Remaining Chapters: {remaining.count()}")
        for ch in remaining:
            print(f"   • {ch.subject}: {ch.chapter_name}")
    else:
        print("\n❌ Deletion cancelled")
else:
    print("\n✅ No Mathematics chapters found - nothing to delete")

print()
