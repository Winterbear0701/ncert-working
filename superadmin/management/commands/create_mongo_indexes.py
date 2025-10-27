"""
Management command to create MongoDB indexes for optimal performance.

Usage:
    python manage.py create_mongo_indexes

Creates:
- Text index on question and answer fields for full-text search
- Compound index on class + subject + chapter_id for filtered queries
- Index on created_at for sorting by recency
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Create MongoDB indexes for saved questions collection'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n📊 Creating MongoDB Indexes...\n'))
        
        try:
            from superadmin import mongo_questions
            from pymongo import TEXT, ASCENDING
        except ImportError as e:
            raise CommandError(f'Import failed: {e}')
        
        # Get MongoDB connection
        client = mongo_questions._get_client()
        if not client:
            raise CommandError('MONGODB_URI not configured')
        
        db_name = getattr(settings, 'MONGODB_DB_NAME', 'ncert_central')
        db = client[db_name]
        col = db.get_collection('saved_questions')
        
        self.stdout.write('📋 Current indexes:')
        for idx in col.list_indexes():
            self.stdout.write(f'   - {idx["name"]}')
        
        # Create text index for full-text search
        self.stdout.write('\n📝 Creating text index on question and answer...')
        try:
            col.create_index([
                ('question', TEXT),
                ('answer', TEXT)
            ], name='text_search_idx')
            self.stdout.write(self.style.SUCCESS('✅ Text index created'))
        except Exception as e:
            if 'already exists' in str(e):
                self.stdout.write(self.style.WARNING('⚠️  Text index already exists'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed: {e}'))
        
        # Create compound index for filtered queries
        self.stdout.write('\n🔍 Creating compound index on class + subject + chapter_id...')
        try:
            col.create_index([
                ('class', ASCENDING),
                ('subject', ASCENDING),
                ('chapter_id', ASCENDING)
            ], name='filter_idx')
            self.stdout.write(self.style.SUCCESS('✅ Filter index created'))
        except Exception as e:
            if 'already exists' in str(e):
                self.stdout.write(self.style.WARNING('⚠️  Filter index already exists'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed: {e}'))
        
        # Create index on marks for sorting
        self.stdout.write('\n⭐ Creating index on marks...')
        try:
            col.create_index([('marks', ASCENDING)], name='marks_idx')
            self.stdout.write(self.style.SUCCESS('✅ Marks index created'))
        except Exception as e:
            if 'already exists' in str(e):
                self.stdout.write(self.style.WARNING('⚠️  Marks index already exists'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed: {e}'))
        
        # Create index on created_at for sorting by recency
        self.stdout.write('\n📅 Creating index on created_at...')
        try:
            col.create_index([('created_at', ASCENDING)], name='created_at_idx')
            self.stdout.write(self.style.SUCCESS('✅ Created_at index created'))
        except Exception as e:
            if 'already exists' in str(e):
                self.stdout.write(self.style.WARNING('⚠️  Created_at index already exists'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed: {e}'))
        
        # Show final index list
        self.stdout.write('\n📊 Final indexes:')
        for idx in col.list_indexes():
            self.stdout.write(f'   - {idx["name"]}: {idx.get("key", {})}')
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('🎉 MongoDB indexes created successfully!'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
