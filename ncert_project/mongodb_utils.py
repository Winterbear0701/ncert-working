"""
MongoDB utility functions for storing user and admin data
This file provides a simple interface to interact with MongoDB
for user-related data while ChromaDB handles document chunks
"""
from pymongo import MongoClient
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class MongoDBManager:
    """
    Singleton MongoDB connection manager
    """
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            try:
                mongodb_uri = settings.MONGODB_URI
                
                # Validate MongoDB URI
                if '<db_password>' in mongodb_uri:
                    logger.error("❌ MongoDB Atlas password not set in .env file!")
                    logger.error("   Please replace <db_password> in MONGODB_URI with your actual password")
                    raise ValueError("MongoDB password not configured")
                
                # Connect to MongoDB Atlas
                self._client = MongoClient(
                    mongodb_uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    retryWrites=True,
                    w='majority'
                )
                
                # Test connection
                self._client.admin.command('ping')
                
                self._db = self._client[settings.MONGODB_DB_NAME]
                logger.info(f"✅ Connected to MongoDB Atlas: {settings.MONGODB_DB_NAME}")
                logger.info(f"   Collections: {self._db.list_collection_names()}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to MongoDB Atlas: {str(e)}")
                logger.error("   Check: 1) Network access allowed in MongoDB Atlas")
                logger.error("           2) Correct password in .env file")
                logger.error("           3) Cluster is running")
                raise
    
    @property
    def db(self):
        """Get database instance"""
        return self._db
    
    @property
    def users(self):
        """Get users collection"""
        return self._db.users
    
    @property
    def chat_history(self):
        """Get chat history collection"""
        return self._db.chat_history
    
    @property
    def chat_cache(self):
        """Get chat cache collection"""
        return self._db.chat_cache
    
    @property
    def permanent_memory(self):
        """Get permanent memory collection"""
        return self._db.permanent_memory
    
    def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")


# Global MongoDB manager instance
mongodb_manager = MongoDBManager()


def get_mongo_db():
    """
    Get MongoDB database instance
    Usage: db = get_mongo_db()
    """
    return mongodb_manager.db


def sync_django_user_to_mongo(user_obj):
    """
    Sync Django user to MongoDB
    This is useful for maintaining data in both SQLite (for Django admin) 
    and MongoDB (for scalability)
    
    Args:
        user_obj: Django CustomUser object
    
    Returns:
        MongoDB document ID
    """
    try:
        db = get_mongo_db()
        users_collection = db.users
        
        user_data = {
            'django_id': user_obj.id,
            'email': user_obj.email,
            'name': user_obj.name,
            'age': user_obj.age,
            'standard': user_obj.standard,
            'role': user_obj.role,
            'is_active': user_obj.is_active,
            'is_staff': user_obj.is_staff,
            'date_joined': user_obj.date_joined,
            'last_login': user_obj.last_login,
        }
        
        # Upsert: Update if exists, insert if not
        result = users_collection.update_one(
            {'django_id': user_obj.id},
            {'$set': user_data},
            upsert=True
        )
        
        logger.info(f"✅ Synced user {user_obj.email} to MongoDB")
        return result.upserted_id or result.modified_count
        
    except Exception as e:
        logger.error(f"❌ Error syncing user to MongoDB: {str(e)}")
        return None


def save_chat_to_mongo(student_id, question, answer, model_used='openai', **kwargs):
    """
    Save chat history to MongoDB
    
    Args:
        student_id: User ID
        question: User's question
        answer: AI's answer
        model_used: Which AI model was used
        **kwargs: Additional metadata (sources, difficulty_level, etc.)
    """
    try:
        db = get_mongo_db()
        chat_collection = db.chat_history
        
        chat_data = {
            'student_id': student_id,
            'question': question,
            'answer': answer,
            'model_used': model_used,
            'created_at': kwargs.get('created_at'),
            'has_images': kwargs.get('has_images', False),
            'sources': kwargs.get('sources', []),
            'difficulty_level': kwargs.get('difficulty_level', 'normal'),
        }
        
        result = chat_collection.insert_one(chat_data)
        logger.info(f"✅ Saved chat to MongoDB: {result.inserted_id}")
        return result.inserted_id
        
    except Exception as e:
        logger.error(f"❌ Error saving chat to MongoDB: {str(e)}")
        return None


def get_user_chat_history(student_id, limit=50):
    """
    Retrieve user's chat history from MongoDB
    
    Args:
        student_id: User ID
        limit: Maximum number of records to return
    
    Returns:
        List of chat history documents
    """
    try:
        db = get_mongo_db()
        chat_collection = db.chat_history
        
        chats = list(chat_collection.find(
            {'student_id': student_id}
        ).sort('created_at', -1).limit(limit))
        
        return chats
        
    except Exception as e:
        logger.error(f"❌ Error retrieving chat history: {str(e)}")
        return []


def create_indexes():
    """
    Create indexes for better query performance
    Run this once after setting up MongoDB
    """
    try:
        db = get_mongo_db()
        
        # User collection indexes
        db.users.create_index('django_id', unique=True)
        db.users.create_index('email', unique=True)
        db.users.create_index('role')
        
        # Chat history indexes
        db.chat_history.create_index('student_id')
        db.chat_history.create_index('created_at')
        db.chat_history.create_index([('student_id', 1), ('created_at', -1)])
        
        # Chat cache indexes
        db.chat_cache.create_index('question_hash', unique=True)
        db.chat_cache.create_index('expires_at')
        
        # Permanent memory indexes
        db.permanent_memory.create_index('student_id')
        db.permanent_memory.create_index([('student_id', 1), ('last_accessed', -1)])
        
        logger.info("✅ MongoDB indexes created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creating indexes: {str(e)}")
        return False
