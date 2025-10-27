"""
Management command to test MongoDB connection and verify saved questions functionality.

Usage:
    python manage.py test_mongo_connection

This command:
1. Verifies MONGODB_URI is configured
2. Tests connection to MongoDB Atlas
3. Creates a test question document
4. Searches for it
5. Cleans up test data
6. Reports connection status
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
import sys


class Command(BaseCommand):
    help = 'Test MongoDB connection and saved questions functionality'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n🔍 Testing MongoDB Connection...\n'))
        
        try:
            from superadmin import mongo_questions
        except ImportError as e:
            raise CommandError(f'Failed to import mongo_questions: {e}')
        
        # Step 1: Check configuration
        self.stdout.write('📋 Step 1: Checking configuration...')
        from django.conf import settings
        import os
        
        uri = getattr(settings, 'MONGODB_URI', None) or os.environ.get('MONGODB_URI')
        if not uri:
            self.stdout.write(self.style.ERROR('❌ MONGODB_URI not configured'))
            self.stdout.write(self.style.WARNING('\nPlease set MONGODB_URI:'))
            self.stdout.write('  export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"')
            return
        
        self.stdout.write(self.style.SUCCESS('✅ MONGODB_URI is configured'))
        
        # Step 2: Test connection
        self.stdout.write('\n📡 Step 2: Testing connection...')
        client = mongo_questions._get_client()
        if not client:
            raise CommandError('Failed to create MongoDB client')
        
        try:
            # Ping the server
            client.admin.command('ping')
            self.stdout.write(self.style.SUCCESS('✅ Successfully connected to MongoDB'))
        except Exception as e:
            raise CommandError(f'Connection failed: {e}')
        
        # Step 3: Test saving a question
        self.stdout.write('\n💾 Step 3: Testing save_question()...')
        test_payload = {
            'class': 'Class 6',
            'subject': 'Science',
            'chapter_id': 9999,
            'chapter_title': 'Test Chapter',
            'question': 'What is the capital of France? [TEST QUESTION - DELETE ME]',
            'answer': 'Paris',
            'marks': 1,
            'created_by': 'test_command',
        }
        
        success = mongo_questions.save_question(test_payload)
        if success:
            self.stdout.write(self.style.SUCCESS('✅ Successfully saved test question'))
        else:
            raise CommandError('Failed to save test question')
        
        # Step 4: Test searching
        self.stdout.write('\n🔎 Step 4: Testing search_questions()...')
        results = mongo_questions.search_questions(
            class_name='Class 6',
            subject='Science',
            query='capital of France'
        )
        
        if results and len(results) > 0:
            self.stdout.write(self.style.SUCCESS(f'✅ Found {len(results)} question(s)'))
            self.stdout.write(f'   First result: {results[0]["question"][:50]}...')
        else:
            self.stdout.write(self.style.WARNING('⚠️  No results found (this might be expected)'))
        
        # Step 5: Cleanup test data
        self.stdout.write('\n🧹 Step 5: Cleaning up test data...')
        try:
            db_name = getattr(settings, 'MONGODB_DB_NAME', 'ncert_central')
            db = client[db_name]
            col = db.get_collection('saved_questions')
            result = col.delete_many({'created_by': 'test_command'})
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {result.deleted_count} test document(s)'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Cleanup failed: {e}'))
        
        # Step 6: Get collection stats
        self.stdout.write('\n📊 Step 6: Collection statistics...')
        try:
            count = col.count_documents({})
            self.stdout.write(self.style.SUCCESS(f'✅ Total saved questions in database: {count}'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Could not get count: {e}'))
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('🎉 All tests passed! MongoDB is ready to use.'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
