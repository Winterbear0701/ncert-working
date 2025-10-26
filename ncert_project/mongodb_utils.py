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
        
        # Quiz attempts indexes
        db.quiz_attempts.create_index('django_id', unique=True)
        db.quiz_attempts.create_index('student_id')
        db.quiz_attempts.create_index('chapter_id')
        db.quiz_attempts.create_index([('student_id', 1), ('started_at', -1)])
        
        # Student progress indexes
        db.student_progress.create_index([('student_id', 1), ('chapter_id', 1)], unique=True)
        db.student_progress.create_index('student_id')
        
        logger.info("✅ MongoDB indexes created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creating indexes: {str(e)}")
        return False


def sync_quiz_attempt_to_mongo(attempt_obj):
    """
    Sync quiz attempt to MongoDB for analytics and backup
    
    Args:
        attempt_obj: QuizAttempt Django model instance
    
    Returns:
        MongoDB document ID
    """
    try:
        db = get_mongo_db()
        quiz_attempts_collection = db.quiz_attempts
        
        # Prepare quiz attempt data
        attempt_data = {
            'django_id': attempt_obj.id,
            'student_id': attempt_obj.student.id,
            'student_email': attempt_obj.student.email,
            'chapter_id': attempt_obj.chapter.chapter_id,
            'chapter_name': attempt_obj.chapter.chapter_name,
            'class_number': attempt_obj.chapter.class_number,
            'subject': attempt_obj.chapter.subject,
            'attempt_number': attempt_obj.attempt_number,
            'status': attempt_obj.status,
            'current_question_number': attempt_obj.current_question_number,
            'total_questions': attempt_obj.total_questions,
            'correct_answers': attempt_obj.correct_answers,
            'score_percentage': attempt_obj.score_percentage,
            'is_passed': attempt_obj.is_passed,
            'started_at': attempt_obj.started_at,
            'submitted_at': attempt_obj.submitted_at,
            'total_time_seconds': attempt_obj.total_time_seconds,
            'topic_performance': attempt_obj.topic_performance,
            'feedback_message': attempt_obj.feedback_message,
        }
        
        # Upsert: Update if exists, insert if not
        result = quiz_attempts_collection.update_one(
            {'django_id': attempt_obj.id},
            {'$set': attempt_data},
            upsert=True
        )
        
        logger.info(f"✅ Synced quiz attempt {attempt_obj.id} to MongoDB")
        return result.upserted_id or result.modified_count
        
    except Exception as e:
        logger.error(f"❌ Error syncing quiz attempt to MongoDB: {str(e)}")
        return None


def sync_student_progress_to_mongo(progress_obj):
    """
    Sync student chapter progress to MongoDB
    
    Args:
        progress_obj: StudentChapterProgress Django model instance
    
    Returns:
        MongoDB document ID
    """
    try:
        db = get_mongo_db()
        progress_collection = db.student_progress
        
        progress_data = {
            'django_id': progress_obj.id,
            'student_id': progress_obj.student.id,
            'student_email': progress_obj.student.email,
            'chapter_id': progress_obj.chapter.chapter_id,
            'chapter_name': progress_obj.chapter.chapter_name,
            'class_number': progress_obj.chapter.class_number,
            'subject': progress_obj.chapter.subject,
            'is_unlocked': progress_obj.is_unlocked,
            'is_completed': progress_obj.is_completed,
            'best_score': progress_obj.best_score,
            'total_attempts': progress_obj.total_attempts,
            'last_attempt_date': progress_obj.last_attempt_date,
            'unlocked_at': progress_obj.unlocked_at,
            'completed_at': progress_obj.completed_at,
        }
        
        # Upsert
        result = progress_collection.update_one(
            {'student_id': progress_obj.student.id, 'chapter_id': progress_obj.chapter.chapter_id},
            {'$set': progress_data},
            upsert=True
        )
        
        logger.info(f"✅ Synced student progress to MongoDB")
        return result.upserted_id or result.modified_count
        
    except Exception as e:
        logger.error(f"❌ Error syncing student progress to MongoDB: {str(e)}")
        return None


def get_student_quiz_analytics(student_id):
    """
    Get comprehensive quiz analytics for a student from MongoDB
    
    Args:
        student_id: Django user ID
    
    Returns:
        Dict with analytics data
    """
    try:
        db = get_mongo_db()
        quiz_attempts = db.quiz_attempts
        
        # Get all quiz attempts for student
        attempts = list(quiz_attempts.find(
            {'student_id': student_id, 'status': {'$in': ['submitted', 'verified']}}
        ).sort('started_at', -1))
        
        if not attempts:
            return {
                'total_attempts': 0,
                'average_score': 0,
                'best_score': 0,
                'total_quizzes_completed': 0,
                'chapters_completed': [],
            }
        
        # Calculate analytics
        total_attempts = len(attempts)
        average_score = sum(a['score_percentage'] for a in attempts) / total_attempts
        best_score = max(a['score_percentage'] for a in attempts)
        
        # Get unique chapters completed
        chapters_completed = list(set(a['chapter_id'] for a in attempts if a.get('is_passed', False)))
        
        return {
            'total_attempts': total_attempts,
            'average_score': round(average_score, 2),
            'best_score': best_score,
            'total_quizzes_completed': total_attempts,
            'chapters_completed': chapters_completed,
            'recent_attempts': attempts[:10],  # Last 10 attempts
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting student analytics: {str(e)}")
        return None

