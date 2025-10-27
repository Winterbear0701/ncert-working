"""
Helpers for saving and searching centralized question bank in MongoDB Atlas.

This module expects a Django settings value MONGODB_URI or the environment
variable MONGODB_URI to be set to a valid MongoDB connection string. It uses
pymongo and keeps the interface minimal: save_question and search_questions.

Document format saved in collection `saved_questions`:
{
  "class": "Class 6",
  "subject": "Science",
  "chapter_id": 123,
  "chapter_title": "Motion",
  "question": "...",
  "answer": "...",
  "marks": 2,
  "created_by": "admin@example.com",
  "created_at": ISODate(...)
}
"""
from datetime import datetime
import os
from typing import List, Dict, Any, Optional

from django.conf import settings

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None


def _get_client() -> Optional[MongoClient]:
    if MongoClient is None:
        return None
    uri = getattr(settings, 'MONGODB_URI', None) or os.environ.get('MONGODB_URI')
    if not uri:
        return None
    return MongoClient(uri)


def save_question(payload: Dict[str, Any]) -> bool:
    """Save a question document to the centralized MongoDB collection.

    payload must include: class (e.g., 'Class 6'), subject, chapter_id (optional),
    chapter_title (optional), question, answer, marks, created_by
    """
    client = _get_client()
    if client is None:
        return False
    db_name = getattr(settings, 'MONGODB_DB_NAME', 'ncert_central')
    db = client[db_name]
    col = db.get_collection('saved_questions')
    doc = payload.copy()
    doc.setdefault('created_at', datetime.utcnow())
    # Upsert prevention: don't dedupe here (allow multiple similar questions)
    try:
        col.insert_one(doc)
        return True
    except Exception:
        return False


def search_questions(class_name: str = '', subject: str = '', chapter_id: Optional[int] = None, query: str = '', limit: int = 50) -> List[Dict[str, Any]]:
    """Search saved questions. Filters by class, subject, chapter_id and text query.

    Returns list of dicts with keys: _id, class, subject, chapter_id, chapter_title, question, answer, marks
    """
    client = _get_client()
    if client is None:
        return []
    db_name = getattr(settings, 'MONGODB_DB_NAME', 'ncert_central')
    db = client[db_name]
    col = db.get_collection('saved_questions')

    filt: Dict[str, Any] = {}
    if class_name:
        filt['class'] = class_name
    if subject:
        filt['subject'] = subject
    if chapter_id:
        filt['chapter_id'] = int(chapter_id)

    if query:
        # simple $text search if text index exists, else regex on question and answer
        try:
            cursor = col.find({**filt, '$text': {'$search': query}}).limit(limit)
        except Exception:
            import re
            regex = re.compile(re.escape(query), re.IGNORECASE)
            cursor = col.find({**filt, '$or': [{'question': regex}, {'answer': regex}]}).limit(limit)
    else:
        cursor = col.find(filt).limit(limit)

    results = []
    for doc in cursor:
        doc['_id'] = str(doc.get('_id'))
        results.append({
            'id': doc['_id'],
            'class': doc.get('class'),
            'subject': doc.get('subject'),
            'chapter_id': doc.get('chapter_id'),
            'chapter_title': doc.get('chapter_title'),
            'question': doc.get('question'),
            'answer': doc.get('answer'),
            'marks': doc.get('marks')
        })
    return results
