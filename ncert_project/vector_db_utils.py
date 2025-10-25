"""
Unified Vector Database Interface
Automatically switches between ChromaDB and Pinecone based on VECTOR_DB environment variable
"""
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Determine which vector database to use
VECTOR_DB = os.getenv('VECTOR_DB', 'chromadb').lower()


def get_vector_db_manager():
    """
    Get the appropriate vector database manager based on configuration
    
    Returns:
        ChromaDBManager or PineconeDBManager instance
    """
    if VECTOR_DB == 'pinecone':
        logger.info("🔧 Using Pinecone for vector storage")
        from .pinecone_utils import get_pinecone_manager
        return get_pinecone_manager()
    else:
        logger.info("🔧 Using ChromaDB for vector storage")
        from .chromadb_utils import get_chromadb_manager
        return get_chromadb_manager()


class VectorDBManager:
    """
    Unified interface for vector database operations
    Provides consistent API regardless of underlying database
    """
    
    def __init__(self):
        self.manager = get_vector_db_manager()
        self.db_type = VECTOR_DB
        logger.info(f"✅ Vector DB Manager initialized with: {self.db_type}")
    
    def add_document_chunks(
        self,
        chunks: List[Dict],
        standard: str,
        subject: str,
        chapter: str,
        source_file: str,
        batch_size: int = 100
    ) -> int:
        """Add document chunks to vector database"""
        return self.manager.add_document_chunks(
            chunks=chunks,
            standard=standard,
            subject=subject,
            chapter=chapter,
            source_file=source_file,
            batch_size=batch_size
        )
    
    def query_by_class_subject_chapter(
        self,
        query_text: str,
        class_num: Optional[str] = None,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        n_results: int = 5
    ) -> Dict:
        """Query vector database with filters"""
        return self.manager.query_by_class_subject_chapter(
            query_text=query_text,
            class_num=class_num,
            subject=subject,
            chapter=chapter,
            n_results=n_results
        )
    
    def get_available_classes(self) -> List[str]:
        """Get list of available classes"""
        return self.manager.get_available_classes()
    
    def get_subjects_by_class(self, class_num: str) -> List[str]:
        """Get subjects for a specific class"""
        return self.manager.get_subjects_by_class(class_num)
    
    def get_chapters_by_class_subject(self, class_num: str, subject: str) -> List[str]:
        """Get chapters for a specific class and subject"""
        return self.manager.get_chapters_by_class_subject(class_num, subject)
    
    def get_stats(self) -> Dict:
        """Get statistics about stored documents/vectors"""
        return self.manager.get_stats()
    
    def clear_collection(self):
        """Clear all data (use with caution!)"""
        return self.manager.clear_collection()
    
    def format_metadata(self, standard: str, subject: str, chapter: str, **extra) -> Dict:
        """Format metadata consistently"""
        return self.manager.format_metadata(standard, subject, chapter, **extra)
    
    @property
    def db_name(self) -> str:
        """Get the name of the underlying database"""
        return self.db_type


# Global instance
_vector_db_manager = None


def get_unified_vector_db():
    """Get the unified vector database manager instance"""
    global _vector_db_manager
    if _vector_db_manager is None:
        _vector_db_manager = VectorDBManager()
    return _vector_db_manager
