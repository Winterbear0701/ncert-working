"""
Django management command to generate quizzes from existing ChromaDB content
Usage: python manage.py generate_quizzes
"""
from django.core.management.base import BaseCommand
from students.quiz_generator import scan_and_generate_quizzes_for_existing_content


class Command(BaseCommand):
    help = 'Generate quiz questions from existing ChromaDB content'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Starting quiz generation from ChromaDB...'))
        
        results = scan_and_generate_quizzes_for_existing_content()
        
        success_count = sum(1 for r in results if r.get('success'))
        fail_count = len(results) - success_count
        
        self.stdout.write(self.style.SUCCESS(f'✅ Quiz generation complete!'))
        self.stdout.write(self.style.SUCCESS(f'  Successful: {success_count}'))
        if fail_count > 0:
            self.stdout.write(self.style.WARNING(f'  Failed: {fail_count}'))
        
        self.stdout.write(self.style.SUCCESS('\n📊 Summary:'))
        for result in results:
            if result.get('success'):
                self.stdout.write(f"  ✅ {result['chapter_id']}: {result['total_variants']} variants")
            else:
                self.stdout.write(self.style.ERROR(f"  ❌ Error: {result.get('error')}"))
