"""
Management command to seed sample questions into MongoDB for testing.

Usage:
    python manage.py seed_sample_questions
    python manage.py seed_sample_questions --count 50
    python manage.py seed_sample_questions --class "Class 6" --subject Science
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed sample questions into MongoDB question bank'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of sample questions to generate'
        )
        parser.add_argument(
            '--class',
            type=str,
            default='Class 6',
            help='Class name (e.g., "Class 6")'
        )
        parser.add_argument(
            '--subject',
            type=str,
            default='Science',
            help='Subject name'
        )

    def handle(self, *args, **options):
        count = options['count']
        class_name = options['class']
        subject = options['subject']
        
        self.stdout.write(self.style.WARNING(f'\n🌱 Seeding {count} sample questions...\n'))
        
        try:
            from superadmin import mongo_questions
        except ImportError as e:
            raise CommandError(f'Failed to import mongo_questions: {e}')
        
        # Sample questions with different mark values
        sample_templates = [
            {
                'marks': 1,
                'questions': [
                    ('What is photosynthesis?', 'The process by which plants make food using sunlight.'),
                    ('Name the largest planet in our solar system.', 'Jupiter'),
                    ('What is the unit of force?', 'Newton'),
                    ('Define biodiversity.', 'The variety of life forms in an ecosystem.'),
                    ('What is gravity?', 'The force that attracts objects toward the Earth.'),
                ]
            },
            {
                'marks': 2,
                'questions': [
                    ('Explain the water cycle.', 'Water evaporates from water bodies, forms clouds, condenses, and falls as precipitation.'),
                    ('What are the three states of matter?', 'Solid, liquid, and gas are the three states of matter.'),
                    ('Describe the function of the heart.', 'The heart pumps blood throughout the body, delivering oxygen and nutrients.'),
                ]
            },
            {
                'marks': 3,
                'questions': [
                    ('Explain how earthquakes occur.', 'Earthquakes occur when tectonic plates shift suddenly, releasing energy stored in rocks. This causes seismic waves that shake the ground.'),
                    ('Describe the process of digestion.', 'Digestion begins in the mouth with chewing and saliva. Food moves to the stomach where acids break it down. Nutrients are absorbed in the intestines.'),
                ]
            },
            {
                'marks': 4,
                'questions': [
                    ('Explain the nitrogen cycle in detail.', 'Nitrogen from the atmosphere is fixed by bacteria into ammonia. Plants absorb it as nitrates. Animals eat plants. Decomposers return nitrogen to soil. Denitrifying bacteria release it back to the atmosphere.'),
                ]
            },
            {
                'marks': 5,
                'questions': [
                    ('Describe the complete process of respiration in humans.', 'Air enters through the nose, passes through the trachea to the lungs. In the alveoli, oxygen diffuses into the blood while carbon dioxide is released. Blood carries oxygen to cells where cellular respiration produces energy (ATP). Carbon dioxide is transported back to the lungs and exhaled.'),
                ]
            }
        ]
        
        saved_count = 0
        failed_count = 0
        
        for template in sample_templates:
            marks = template['marks']
            questions = template['questions']
            
            # Calculate how many of this mark type to generate
            portion = len(questions)
            for i in range(min(portion, count // 5 + 1)):
                if saved_count >= count:
                    break
                
                q_text, answer = questions[i % len(questions)]
                
                payload = {
                    'class': class_name,
                    'subject': subject,
                    'chapter_id': 1,
                    'chapter_title': 'Sample Chapter',
                    'question': f'{q_text} [Sample {saved_count + 1}]',
                    'answer': answer,
                    'marks': marks,
                    'created_by': 'seed_command',
                }
                
                success = mongo_questions.save_question(payload)
                if success:
                    saved_count += 1
                    self.stdout.write(f'✅ [{saved_count}/{count}] Saved {marks}-mark question')
                else:
                    failed_count += 1
                    self.stdout.write(self.style.WARNING(f'⚠️  Failed to save question'))
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'🎉 Seeding complete!'))
        self.stdout.write(self.style.SUCCESS(f'   Successfully saved: {saved_count}'))
        if failed_count > 0:
            self.stdout.write(self.style.WARNING(f'   Failed: {failed_count}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
        # Show how to search
        self.stdout.write(self.style.WARNING('💡 Tip: Test search with:'))
        self.stdout.write(f'   curl "http://localhost:8000/superadmin/api/get-saved-questions/?class={class_name.replace(" ", "%20")}&subject={subject}"')
