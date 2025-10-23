#!/usr/bin/env python
"""
Script to completely reset the database and ChromaDB
This will:
1. Delete the SQLite database
2. Clear ChromaDB data
3. Run migrations
4. Create a superadmin user
"""

import os
import sys
import shutil
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.core.management import call_command

def reset_database():
    """Reset the entire database"""
    print("🔥 Starting Fresh Database Reset...")
    print("=" * 60)
    
    # 1. Delete SQLite database
    db_path = 'db.sqlite3'
    if os.path.exists(db_path):
        print(f"\n📦 Deleting database: {db_path}")
        os.remove(db_path)
        print("✅ Database deleted successfully")
    else:
        print(f"\n⚠️  Database not found: {db_path}")
    
    # 2. Clear ChromaDB data
    chromadb_path = 'chromadb_data'
    if os.path.exists(chromadb_path):
        print(f"\n📦 Clearing ChromaDB data: {chromadb_path}")
        shutil.rmtree(chromadb_path)
        print("✅ ChromaDB data cleared successfully")
    else:
        print(f"\n⚠️  ChromaDB directory not found: {chromadb_path}")
    
    # 3. Clear media files (uploaded PDFs, etc.)
    media_path = 'media'
    if os.path.exists(media_path):
        print(f"\n📦 Clearing media files: {media_path}")
        for root, dirs, files in os.walk(media_path):
            for file in files:
                if not file.startswith('.'):  # Keep .gitkeep files
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    print(f"   Deleted: {file}")
        print("✅ Media files cleared successfully")
    
    # 4. Run migrations
    print("\n🔧 Running migrations...")
    call_command('migrate', verbosity=1)
    print("✅ Migrations completed successfully")
    
    print("\n" + "=" * 60)
    print("🎉 Database reset completed successfully!")
    print("=" * 60)

def create_superadmin():
    """Create a superadmin user"""
    print("\n👤 Creating Superadmin User...")
    print("=" * 60)
    
    User = get_user_model()
    
    # Get user input
    name = input("\nEnter superadmin name (default: Admin User): ").strip() or "Admin User"
    email = input("Enter superadmin email (default: admin@ncert.com): ").strip() or "admin@ncert.com"
    
    # Set password
    while True:
        password = input("Enter superadmin password (default: admin123): ").strip() or "admin123"
        confirm_password = input("Confirm password: ").strip() or "admin123"
        
        if password == confirm_password:
            break
        else:
            print("❌ Passwords don't match. Please try again.")
    
    try:
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            print(f"\n⚠️  User '{email}' already exists. Deleting...")
            User.objects.filter(email=email).delete()
        
        # Create superadmin using create_superuser method
        superadmin = User.objects.create_superuser(
            email=email,
            name=name,
            password=password
        )
        
        print("\n✅ Superadmin created successfully!")
        print(f"   Name: {name}")
        print(f"   Email: {email}")
        print(f"   Role: super_admin")
        print(f"   Password: {password}")
        
    except Exception as e:
        print(f"\n❌ Error creating superadmin: {e}")
        return False
    
    print("\n" + "=" * 60)
    return True

def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 NCERT Learning Platform - Database Reset Tool")
    print("=" * 60)
    
    # Confirm action
    print("\n⚠️  WARNING: This will DELETE ALL DATA including:")
    print("   • All users (students, superadmins)")
    print("   • All quiz attempts and scores")
    print("   • All chat history")
    print("   • All uploaded PDFs")
    print("   • All RAG/ChromaDB embeddings")
    print("   • All unit tests")
    
    confirm = input("\n❓ Are you sure you want to continue? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n❌ Operation cancelled. No changes made.")
        return
    
    # Reset database
    reset_database()
    
    # Create superadmin
    create_superadmin()
    
    print("\n🎊 All done! You can now:")
    print("   1. Start the server: python manage.py runserver")
    print("   2. Login with your superadmin credentials")
    print("   3. Begin uploading books and creating content")
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
