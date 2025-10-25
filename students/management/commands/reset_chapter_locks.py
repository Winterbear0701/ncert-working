"""
Management command to reset chapter unlock status for all students
Only first chapter of each subject will be unlocked
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from students.models import StudentChapterProgress, QuizChapter

User = get_user_model()


class Command(BaseCommand):
    help = 'Reset chapter unlock status - only first chapters will be unlocked'

    def handle(self, *args, **options):
        self.stdout.write('\n🔒 Resetting Chapter Unlock Status...\n')
        self.stdout.write('=' * 60)
        
        # Get all progress records
        all_progress = StudentChapterProgress.objects.select_related('chapter', 'student').all()
        
        locked_count = 0
        unlocked_count = 0
        
        for progress in all_progress:
            # Only first chapter of each subject should be unlocked
            if progress.chapter.chapter_order == 1:
                if not progress.is_unlocked:
                    progress.is_unlocked = True
                    progress.save()
                    unlocked_count += 1
                    self.stdout.write(
                        f'🔓 Unlocked: {progress.student.email} - {progress.chapter.chapter_name}'
                    )
            else:
                # Lock all non-first chapters
                if progress.is_unlocked:
                    progress.is_unlocked = False
                    progress.save()
                    locked_count += 1
                    self.stdout.write(
                        f'🔒 Locked: {progress.student.email} - {progress.chapter.chapter_name}'
                    )
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'✅ Locked {locked_count} chapters')
        self.stdout.write(f'✅ Unlocked {unlocked_count} first chapters')
        self.stdout.write('\n🎯 Students must complete chapters (score >= 70%) to unlock next ones\n')
