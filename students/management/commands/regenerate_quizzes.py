"""
Management command to regenerate quizzes using improved method
"""
from django.core.management.base import BaseCommand
from students.improved_quiz_generator import generate_quiz_with_textbook_questions
from students.models import QuizChapter
import logging

logger = logging.getLogger('students')


class Command(BaseCommand):
    help = 'Regenerate quizzes using improved textbook-based method'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chapter-id',
            type=str,
            help='Specific chapter ID to regenerate (optional)',
        )
        parser.add_argument(
            '--class',
            type=str,
            dest='class_num',
            help='Regenerate for specific class (optional)',
        )

    def handle(self, *args, **options):
        chapter_id = options.get('chapter_id')
        class_num = options.get('class_num')
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting Quiz Regeneration'))
        self.stdout.write(self.style.WARNING('This will use textbook "Let us reflect" questions'))
        
        if chapter_id:
            # Regenerate specific chapter
            try:
                chapter = QuizChapter.objects.get(chapter_id=chapter_id)
                self.stdout.write(f'📖 Regenerating: {chapter.chapter_name}')
                
                result = generate_quiz_with_textbook_questions(
                    chapter_id=chapter.chapter_id,
                    class_num=chapter.class_number.replace('Class ', ''),
                    subject=chapter.subject,
                    chapter_name=chapter.chapter_name,
                    chapter_order=chapter.chapter_order
                )
                
                if result['success']:
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Generated {result["total_questions"]} questions '
                        f'({result["textbook_questions_used"]} from textbook)'
                    ))
                else:
                    self.stdout.write(self.style.ERROR(f'❌ Error: {result["error"]}'))
                    
            except QuizChapter.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Chapter not found: {chapter_id}'))
        
        else:
            # Regenerate all chapters (or by class)
            queryset = QuizChapter.objects.filter(is_active=True)
            if class_num:
                queryset = queryset.filter(class_number__contains=class_num)
            
            total = queryset.count()
            self.stdout.write(f'📚 Found {total} chapters to regenerate')
            
            success_count = 0
            for i, chapter in enumerate(queryset, 1):
                self.stdout.write(f'\n[{i}/{total}] {chapter.chapter_name}...')
                
                result = generate_quiz_with_textbook_questions(
                    chapter_id=chapter.chapter_id,
                    class_num=chapter.class_number.replace('Class ', ''),
                    subject=chapter.subject,
                    chapter_name=chapter.chapter_name,
                    chapter_order=chapter.chapter_order
                )
                
                if result['success']:
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✅ {result["total_questions"]} questions '
                        f'({result.get("textbook_questions_used", 0)} from textbook)'
                    ))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  ❌ {result["error"]}'))
            
            self.stdout.write(self.style.SUCCESS(
                f'\n🎉 Completed: {success_count}/{total} chapters regenerated'
            ))
