"""
Enhanced ChromaDB utility for storing book chunks with proper labeling
Format: Class 5, Subject: Maths, Chapter: 1
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from django.conf import settings
from sentence_transformers import SentenceTransformer
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Initialize sentence transformer for embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


class ChromaDBManager:
    """
    Enhanced ChromaDB manager with proper document organization
    Documents are stored with clear hierarchical metadata:
    - Class/Standard (e.g., "Class 5", "Class 6")
    - Subject (e.g., "Mathematics", "Science")
    - Chapter (e.g., "Chapter 1: Numbers", "Chapter 2: Fractions")
    """
    
    def __init__(self):
        try:
            self.client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIRECTORY
            )
            
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={
                    "description": "NCERT textbook content organized by Class, Subject, and Chapter",
                    "hnsw:space": "cosine"
                }
            )
            
            logger.info(f"✅ ChromaDB initialized: {settings.CHROMA_COLLECTION_NAME}")
            logger.info(f"📊 Current document count: {self.collection.count()}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromaDB: {str(e)}")
            raise
    
    def format_metadata(self, standard: str, subject: str, chapter: str, **extra) -> Dict:
        """
        Create properly formatted metadata for ChromaDB storage
        
        Args:
            standard: Class/Grade (e.g., "5", "6", "10")
            subject: Subject name (e.g., "Mathematics", "Science")
            chapter: Chapter name or number (e.g., "Chapter 1: Numbers")
            **extra: Additional metadata fields
        
        Returns:
            Dictionary with formatted metadata
        """
        # Ensure standard has "Class" prefix
        if not str(standard).lower().startswith('class'):
            standard_label = f"Class {standard}"
        else:
            standard_label = str(standard)
        
        # Ensure chapter has proper format
        if not str(chapter).lower().startswith('chapter'):
            chapter_label = f"Chapter {chapter}"
        else:
            chapter_label = str(chapter)
        
        metadata = {
            "class": standard_label,           # "Class 5", "Class 6", etc.
            "subject": str(subject).title(),   # "Mathematics", "Science", etc.
            "chapter": chapter_label,          # "Chapter 1", "Chapter 2: Name", etc.
            "standard": str(standard),         # Original value for filtering
            "chapter_raw": str(chapter),       # Original value for filtering
        }
        
        # Add any extra metadata
        metadata.update(extra)
        
        return metadata
    
    def add_document_chunks(
        self,
        chunks: List[Dict],
        standard: str,
        subject: str,
        chapter: str,
        source_file: str,
        batch_size: int = 100
    ) -> int:
        """
        Add document chunks to ChromaDB with proper labeling
        
        Args:
            chunks: List of text chunks to add
            standard: Class/Grade number
            subject: Subject name
            chapter: Chapter name/number
            source_file: Original filename
            batch_size: Number of chunks to process at once
        
        Returns:
            Total number of chunks added
        """
        try:
            total_added = 0
            
            # Format metadata template
            base_metadata = self.format_metadata(standard, subject, chapter)
            base_metadata['source_file'] = source_file
            
            logger.info(f"📚 Adding chunks for {base_metadata['class']} - "
                       f"{base_metadata['subject']} - {base_metadata['chapter']}")
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                
                # Prepare batch data
                ids = []
                documents = []
                metadatas = []
                
                for chunk in batch:
                    # Create unique ID with clear labeling
                    chunk_id = (
                        f"class_{standard}_"
                        f"subject_{subject.lower().replace(' ', '_')}_"
                        f"chapter_{chunk.get('chapter_num', chapter)}_"
                        f"page_{chunk.get('page', 0)}_"
                        f"chunk_{chunk.get('chunk_index', 0)}"
                    )
                    
                    # Merge metadata
                    chunk_metadata = base_metadata.copy()
                    chunk_metadata.update({
                        'page': chunk.get('page', 0),
                        'chunk_index': chunk.get('chunk_index', 0),
                        'char_count': len(chunk['text']),
                        'has_equations': chunk.get('has_equations', False),
                        'content_type': chunk.get('content_type', 'general')
                    })
                    
                    ids.append(chunk_id)
                    documents.append(chunk['text'])
                    metadatas.append(chunk_metadata)
                
                # Generate embeddings
                embeddings = embedding_model.encode(documents).tolist()
                
                # Add to collection
                self.collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                
                total_added += len(batch)
                logger.info(f"✅ Added batch {i//batch_size + 1}: {len(batch)} chunks")
            
            logger.info(f"🎉 Successfully added {total_added} chunks to ChromaDB")
            return total_added
            
        except Exception as e:
            logger.error(f"❌ Error adding chunks to ChromaDB: {str(e)}")
            raise
    
    def query_by_class_subject_chapter(
        self,
        query_text: str,
        class_num: Optional[str] = None,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        n_results: int = 5
    ) -> Dict:
        """
        Query ChromaDB with optional filters for class, subject, and chapter
        
        Args:
            query_text: The question/query text
            class_num: Filter by class (e.g., "5", "6", "Class 5")
            subject: Filter by subject (e.g., "Mathematics")
            chapter: Filter by chapter (e.g., "1", "Chapter 1")
            n_results: Number of results to return
        
        Returns:
            Query results with documents and metadata
        """
        try:
            # Build where clause for filtering
            where_clause = {}
            
            if class_num:
                if not str(class_num).lower().startswith('class'):
                    class_num = f"Class {class_num}"
                where_clause['class'] = class_num
            
            if subject:
                where_clause['subject'] = str(subject).title()
            
            if chapter:
                if not str(chapter).lower().startswith('chapter'):
                    where_clause['chapter_raw'] = str(chapter)
                else:
                    where_clause['chapter'] = str(chapter)
            
            # Generate query embedding
            query_embedding = embedding_model.encode([query_text]).tolist()[0]
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_clause if where_clause else None
            )
            
            logger.info(f"🔍 Query returned {len(results['documents'][0])} results")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error querying ChromaDB: {str(e)}")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}
    
    def get_available_classes(self) -> List[str]:
        """Get list of all available classes in the database"""
        try:
            # Get sample of all documents to extract unique classes
            results = self.collection.get(limit=1000)
            classes = set()
            
            for metadata in results['metadatas']:
                if 'class' in metadata:
                    classes.add(metadata['class'])
            
            return sorted(list(classes))
        except Exception as e:
            logger.error(f"❌ Error getting classes: {str(e)}")
            return []
    
    def get_subjects_by_class(self, class_num: str) -> List[str]:
        """Get all subjects available for a specific class"""
        try:
            if not str(class_num).lower().startswith('class'):
                class_num = f"Class {class_num}"
            
            results = self.collection.get(
                where={'class': class_num},
                limit=1000
            )
            
            subjects = set()
            for metadata in results['metadatas']:
                if 'subject' in metadata:
                    subjects.add(metadata['subject'])
            
            return sorted(list(subjects))
        except Exception as e:
            logger.error(f"❌ Error getting subjects: {str(e)}")
            return []
    
    def get_chapters_by_class_subject(self, class_num: str, subject: str) -> List[str]:
        """Get all chapters for a specific class and subject"""
        try:
            if not str(class_num).lower().startswith('class'):
                class_num = f"Class {class_num}"
            
            results = self.collection.get(
                where={
                    '$and': [
                        {'class': {'$eq': class_num}},
                        {'subject': {'$eq': str(subject).title()}}
                    ]
                },
                limit=1000
            )
            
            chapters = set()
            for metadata in results['metadatas']:
                if 'chapter' in metadata:
                    chapters.add(metadata['chapter'])
            
            return sorted(list(chapters))
        except Exception as e:
            logger.error(f"❌ Error getting chapters: {str(e)}")
            return []
    
    def get_stats(self) -> Dict:
        """Get statistics about stored documents"""
        try:
            total_docs = self.collection.count()
            classes = self.get_available_classes()
            
            stats = {
                'total_documents': total_docs,
                'total_classes': len(classes),
                'classes': classes,
                'subjects_by_class': {}
            }
            
            for class_num in classes:
                subjects = self.get_subjects_by_class(class_num)
                stats['subjects_by_class'][class_num] = subjects
            
            return stats
        except Exception as e:
            logger.error(f"❌ Error getting stats: {str(e)}")
            return {}
    
    def clear_collection(self):
        """Clear all documents from the collection (use with caution!)"""
        try:
            self.client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={
                    "description": "NCERT textbook content organized by Class, Subject, and Chapter",
                    "hnsw:space": "cosine"
                }
            )
            logger.info("✅ Collection cleared successfully")
        except Exception as e:
            logger.error(f"❌ Error clearing collection: {str(e)}")


# Global ChromaDB manager instance
chroma_manager = ChromaDBManager()


def get_chromadb_manager() -> ChromaDBManager:
    """Get the global ChromaDB manager instance"""
    return chroma_manager
