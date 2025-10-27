from django.core.management.base import BaseCommand
from ncert_project.mongodb_utils import get_mongo_db


class Command(BaseCommand):
    help = 'Check chapter data in MongoDB (book_chapters and quiz_chapters)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-test-data',
            action='store_true',
            help='Create test chapters for Class 5',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n📚 MongoDB Chapter Check\n'))
        
        try:
            # Get MongoDB connection
            db = get_mongo_db()
            
            # ==================== CHECK BOOK_CHAPTERS (NEW) ====================
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('📖 BOOK_CHAPTERS (Uploaded PDFs)'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
            book_chapters = db.book_chapters
            book_total = book_chapters.count_documents({})
            
            self.stdout.write(f'\nTotal chapters in book_chapters: {book_total}')
            
            if book_total > 0:
                # Check unique class/subject combinations
                self.stdout.write('\n📋 Chapters by Class and Subject:')
                pipeline = [
                    {'$group': {
                        '_id': {
                            'class': '$class_number',
                            'subject': '$subject'
                        },
                        'count': {'$sum': 1}
                    }},
                    {'$sort': {'_id.class': 1, '_id.subject': 1}}
                ]
                
                for doc in book_chapters.aggregate(pipeline):
                    self.stdout.write(
                        f"  • {doc['_id']['class']} - {doc['_id']['subject']}: "
                        f"{self.style.WARNING(str(doc['count']))} chapters"
                    )
                
                # Sample chapters
                self.stdout.write('\n📝 Sample Chapters:')
                for ch in book_chapters.find().limit(5):
                    self.stdout.write(f"  • {ch.get('class_number')} - {ch.get('subject')} - {ch.get('chapter_name')}")
            else:
                self.stdout.write(self.style.WARNING('\n❌ No chapters found in book_chapters!'))
                self.stdout.write('\n💡 Chapters will be auto-saved when you upload PDFs')
            
            # ==================== CHECK QUIZ_CHAPTERS (EXISTING) ====================
            self.stdout.write('\n')
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('🎯 QUIZ_CHAPTERS (Quiz-Enabled Only)'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
            quiz_chapters = db.quiz_chapters
            quiz_total = quiz_chapters.count_documents({})
            
            self.stdout.write(f'\nTotal chapters in quiz_chapters: {quiz_total}')
            
            if quiz_total == 0:
                self.stdout.write(self.style.WARNING('\n❌ No quiz chapters found!'))
                self.stdout.write('\n💡 Quiz chapters are created when you generate quizzes for uploaded PDFs')
            else:
                # Check unique class/subject combinations
                self.stdout.write('\n📋 Quiz Chapters by Class and Subject:')
                pipeline = [
                    {'$group': {
                        '_id': {
                            'class': '$class_number',
                            'subject': '$subject'
                        },
                        'count': {'$sum': 1}
                    }},
                    {'$sort': {'_id.class': 1, '_id.subject': 1}}
                ]
                
                for doc in quiz_chapters.aggregate(pipeline):
                    self.stdout.write(
                        f"  • {doc['_id']['class']} - {doc['_id']['subject']}: "
                        f"{self.style.WARNING(str(doc['count']))} chapters"
                    )
            
            # ==================== SUMMARY ====================
            self.stdout.write('\n')
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('📊 SUMMARY'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(f'\nTotal uploaded chapters (book_chapters): {book_total}')
            self.stdout.write(f'Total quiz-enabled chapters (quiz_chapters): {quiz_total}')
            
            if book_total > 0:
                self.stdout.write(self.style.SUCCESS('\n✅ Unit tests will work! Chapters available in book_chapters.'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️ No chapters available for unit tests yet.'))
                self.stdout.write('   Upload some PDFs first!')
            
            self.stdout.write(self.style.SUCCESS('\n✅ Check complete!\n'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error connecting to MongoDB: {e}'))
            self.stdout.write('\nMake sure:')
            self.stdout.write('  1. MongoDB is running')
            self.stdout.write('  2. MONGODB_URI is set in environment')
            self.stdout.write('  3. Virtual environment is activated\n')
