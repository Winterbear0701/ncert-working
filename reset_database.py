#!/usr/bin/env python
"""
Script to completely reset ALL databases (SQLite, MongoDB Atlas, ChromaDB)
This will:
1. Delete the SQLite database (in-memory, not used for persistence)
2. Clear ALL collections in MongoDB Atlas
3. Clear ChromaDB data
4. Clear media files
5. Run migrations
6. Create a superadmin user
"""

import os
import sys
import shutil
import django
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.core.management import call_command
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

def reset_mongodb_atlas():
    """Reset MongoDB Atlas - Delete all collections"""
    print("\n☁️  Resetting MongoDB Atlas...")
    print("-" * 60)
    
    try:
        # Get MongoDB connection details from environment
        mongodb_uri = os.getenv('MONGODB_URI')
        mongodb_db_name = os.getenv('MONGODB_DB_NAME', 'ncert_learning_db')
        
        if not mongodb_uri:
            print("⚠️  MongoDB URI not found in .env file")
            print("   Skipping MongoDB Atlas reset")
            return False
        
        # Check if password is set
        if '<db_password>' in mongodb_uri:
            print("⚠️  MongoDB password not set in .env file")
            print("   Please replace <db_password> with actual password")
            print("   Skipping MongoDB Atlas reset")
            return False
        
        print(f"📡 Connecting to MongoDB Atlas...")
        print(f"   Database: {mongodb_db_name}")
        
        # Connect to MongoDB
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        print("✅ Connected to MongoDB Atlas")
        
        # Get database
        db = client[mongodb_db_name]
        
        # Get all collections
        collections = db.list_collection_names()
        
        if not collections:
            print("ℹ️  No collections found in MongoDB (already empty)")
            client.close()
            return True
        
        print(f"\n🗑️  Found {len(collections)} collections to delete:")
        for col in collections:
            print(f"   • {col}")
        
        # Delete all collections
        print("\n🔥 Deleting all collections...")
        deleted_count = 0
        for collection_name in collections:
            result = db[collection_name].delete_many({})
            print(f"   ✅ {collection_name}: Deleted {result.deleted_count} documents")
            deleted_count += result.deleted_count
            
            # Drop the collection entirely
            db[collection_name].drop()
        
        print(f"\n✅ MongoDB Atlas reset complete!")
        print(f"   Total documents deleted: {deleted_count}")
        print(f"   Total collections dropped: {len(collections)}")
        
        client.close()
        return True
        
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        print(f"\n❌ Could not connect to MongoDB Atlas: {e}")
        print("   Skipping MongoDB Atlas reset")
        return False
    except Exception as e:
        print(f"\n❌ Error resetting MongoDB Atlas: {e}")
        return False

def reset_database():
    """Reset the entire database"""
    print("🔥 Starting Fresh Database Reset...")
    print("=" * 60)
    
    # 1. Reset MongoDB Atlas (FIRST - cloud database)
    mongodb_success = reset_mongodb_atlas()
    
    # 2. Delete SQLite database (local, not used for persistence anymore)
    db_path = 'db.sqlite3'
    if os.path.exists(db_path):
        print(f"\n📦 Deleting SQLite database: {db_path}")
        os.remove(db_path)
        print("✅ SQLite database deleted successfully")
        print("   (Note: Now using in-memory SQLite for Django admin only)")
    else:
        print(f"\n⚠️  SQLite database not found: {db_path}")
    
    # 3. Clear Vector Database (Pinecone)
    print(f"\n☁️  Clearing Pinecone vector database...")
    pinecone_cleared = False
    try:
        from pinecone import Pinecone
        api_key = os.getenv('PINECONE_API_KEY')
        index_name = os.getenv('PINECONE_INDEX_NAME', 'ncert-learning-rag')
        
        if api_key and api_key != 'your_pinecone_api_key_here':
            pc = Pinecone(api_key=api_key)
            index = pc.Index(index_name)
            
            # Delete all vectors from index
            index.delete(delete_all=True)
            pinecone_cleared = True
            print("✅ Pinecone vectors cleared successfully")
        else:
            print("⚠️  Pinecone API key not configured, skipping")
    except Exception as e:
        print(f"❌ Error clearing Pinecone index: {e}")
        pinecone_cleared = False
    
    # 4. Delete old ChromaDB data folder (not used in production)
    chromadb_path = 'chromadb_data'
    if os.path.exists(chromadb_path):
        print(f"\n🗑️  Deleting old ChromaDB data folder: {chromadb_path}")
        import shutil
        shutil.rmtree(chromadb_path)
        print("✅ ChromaDB data folder deleted (using Pinecone in production)")
    
    # 4b. Clean up archive folder (old logs)
    archive_path = 'archive'
    if os.path.exists(archive_path):
        print(f"\n🗑️  Cleaning archive folder: {archive_path}")
        import shutil
        shutil.rmtree(archive_path)
        print("✅ Archive folder deleted (old logs removed)")
    
    # 5. Clear media files (uploaded PDFs, etc.)
    media_path = 'media'
    if os.path.exists(media_path):
        print(f"\n📦 Clearing media files: {media_path}")
        deleted_files = 0
        for root, dirs, files in os.walk(media_path):
            for file in files:
                if not file.startswith('.'):  # Keep .gitkeep files
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    deleted_files += 1
        print(f"✅ Media files cleared successfully ({deleted_files} files deleted)")
    
    # 6. Run migrations (create schema in-memory SQLite)
    print("\n🔧 Running Django migrations...")
    call_command('migrate', verbosity=1)
    print("✅ Migrations completed successfully")
    
    print("\n" + "=" * 60)
    print("🎉 Database reset completed successfully!")
    if mongodb_success:
        print("   ✅ MongoDB Atlas: All collections deleted")
    else:
        print("   ⚠️  MongoDB Atlas: Skipped (check connection)")
    if pinecone_cleared:
        print("   ✅ Pinecone: All vectors deleted")
    else:
        print("   ⚠️  Pinecone: Not cleared (check connection)")
    print("   ✅ ChromaDB: Old data folder removed")
    print("   ✅ Media files: All uploads deleted")
    print("   ✅ Migrations: Schema created in memory")
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
    print("🚀 NCERT Learning Platform - Complete Database Reset Tool")
    print("=" * 60)
    
    # Confirm action
    print("\n⚠️  WARNING: This will DELETE ALL DATA from:")
    print("\n   ☁️  MongoDB Atlas (Cloud Database):")
    print("      • All users (students, teachers, superadmins)")
    print("      • All quiz chapters, questions, and variants")
    print("      • All quiz attempts and scores")
    print("      • All unit tests and evaluations")
    print("      • All chat history, cache, and memories")
    print("      • All upload metadata")
    print("\n   ☁️  Pinecone (Cloud Vector Database):")
    print("      • All PDF text chunks")
    print("      • All embeddings for RAG")
    print("\n   📁 Local Files:")
    print("      • All uploaded PDFs")
    print("      • All extracted images")
    print("      • SQLite database (if exists)")
    
    confirm = input("\n❓ Are you sure you want to continue? Type 'DELETE ALL' to confirm: ").strip()
    
    if confirm != 'DELETE ALL':
        print("\n❌ Operation cancelled. No changes made.")
        return
    
    # Reset database
    reset_database()
    
    # Create superadmin
    create_superadmin()
    
    print("\n🎊 All done! Production Database Architecture:")
    print("\n   ☁️  MongoDB Atlas (Cloud):")
    print("      • Stores: Users, quizzes, scores, chat, uploads")
    print("      • Location: cluster0.jxdvukx.mongodb.net")
    print("      • Status: Empty and ready ✅")
    print("\n   ☁️  Pinecone (Cloud Vector Database):")
    print("      • Stores: PDF chunks, embeddings for RAG")
    print("      • Index: ncert-learning-rag")
    print("      • Status: Empty and ready ✅")
    print("\n   � SQLite (Local - Minimal):")
    print("      • Used for: Django admin/auth sessions only")
    print("      • Data: Temporary (resets on server restart)")
    print("      • All real data goes to MongoDB Atlas")
    
    print("\n   Next steps:")
    print("   1. Start the server: python manage.py runserver")
    print("   2. Login with your superadmin credentials")
    print("   3. Upload PDFs (will populate ChromaDB)")
    print("   4. Quiz data will be stored in MongoDB Atlas")
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
