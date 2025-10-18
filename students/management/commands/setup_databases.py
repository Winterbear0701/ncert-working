"""
Django management command to setup MongoDB and ChromaDB
Run this after configuring your MongoDB connection
"""
from django.core.management.base import BaseCommand
from ncert_project.mongodb_utils import create_indexes, get_mongo_db
from ncert_project.chromadb_utils import get_chromadb_manager


class Command(BaseCommand):
    help = 'Setup MongoDB indexes and verify ChromaDB connection'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-chroma',
            action='store_true',
            help='Clear ChromaDB collection (WARNING: Deletes all documents!)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('🚀 Setting up MongoDB and ChromaDB'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        
        # Setup MongoDB
        self.stdout.write('\n📦 Setting up MongoDB...')
        try:
            db = get_mongo_db()
            self.stdout.write(self.style.SUCCESS(f'✅ Connected to MongoDB: {db.name}'))
            
            # Create indexes
            self.stdout.write('Creating indexes...')
            if create_indexes():
                self.stdout.write(self.style.SUCCESS('✅ MongoDB indexes created successfully'))
            else:
                self.stdout.write(self.style.ERROR('❌ Failed to create MongoDB indexes'))
            
            # Show collections
            collections = db.list_collection_names()
            self.stdout.write(f'\n📊 Available collections: {", ".join(collections) if collections else "None"}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ MongoDB Error: {str(e)}'))
        
        # Setup ChromaDB
        self.stdout.write('\n\n📚 Setting up ChromaDB...')
        try:
            chroma_manager = get_chromadb_manager()
            
            if options['reset_chroma']:
                self.stdout.write(self.style.WARNING('⚠️  Clearing ChromaDB collection...'))
                chroma_manager.clear_collection()
                self.stdout.write(self.style.SUCCESS('✅ ChromaDB collection cleared'))
            
            # Show stats
            stats = chroma_manager.get_stats()
            self.stdout.write(self.style.SUCCESS(f'✅ ChromaDB connected'))
            self.stdout.write(f'\n📊 ChromaDB Statistics:')
            self.stdout.write(f'   Total Documents: {stats.get("total_documents", 0)}')
            self.stdout.write(f'   Total Classes: {stats.get("total_classes", 0)}')
            
            if stats.get('classes'):
                self.stdout.write(f'\n   Available Classes:')
                for class_name in stats['classes']:
                    subjects = stats['subjects_by_class'].get(class_name, [])
                    self.stdout.write(f'   - {class_name}: {", ".join(subjects) if subjects else "No subjects"}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ ChromaDB Error: {str(e)}'))
        
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✅ Setup complete!'))
        self.stdout.write('=' * 70)
        self.stdout.write('\n💡 Next steps:')
        self.stdout.write('   1. Add your API keys to .env file')
        self.stdout.write('   2. Upload NCERT books through the admin interface')
        self.stdout.write('   3. Books will be stored in ChromaDB with format: Class X, Subject: Y, Chapter: Z')
        self.stdout.write('   4. User/Admin data will be stored in MongoDB\n')
