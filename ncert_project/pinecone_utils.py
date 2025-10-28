"""
Pinecone DB utility for storing book chunks with proper labeling (Production-Ready)
Replaces ChromaDB for scalable cloud-based vector storage
Format: Class 5, Subject: Maths, Chapter: 1
"""
import os
from pinecone import Pinecone, ServerlessSpec
from django.conf import settings
from sentence_transformers import SentenceTransformer
import logging
from typing import List, Dict, Optional
import time

logger = logging.getLogger(__name__)

# Initialize sentence transformer for embeddings (same as ChromaDB for consistency)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2


class PineconeDBManager:
    """
    Pinecone DB manager with document organization
    Documents are stored with clear hierarchical metadata:
    - Class/Standard (e.g., "Class 5", "Class 6")
    - Subject (e.g., "Mathematics", "Science")
    - Chapter (e.g., "Chapter 1: Numbers", "Chapter 2: Fractions")
    """
    
    def __init__(self):
        try:
            # Get Pinecone credentials from environment
            api_key = os.getenv('PINECONE_API_KEY')
            index_name = os.getenv('PINECONE_INDEX_NAME', 'ncert-learning-rag')
            
            if not api_key or api_key == 'your_pinecone_api_key_here':
                raise ValueError("❌ PINECONE_API_KEY not set in .env file")
            
            # Initialize Pinecone (v7+ doesn't need environment parameter)
            self.pc = Pinecone(api_key=api_key)
            self.index_name = index_name
            
            # Create index if it doesn't exist
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]
            
            if index_name not in existing_indexes:
                logger.info(f"📦 Creating new Pinecone index: {index_name}")
                # For Pinecone v7+, use serverless spec with proper cloud/region
                self.pc.create_index(
                    name=index_name,
                    dimension=EMBEDDING_DIMENSION,
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region='us-east-1'  # Use standard AWS region format
                    )
                )
                # Wait for index to be ready
                logger.info(f"⏳ Waiting for index to be ready...")
                time.sleep(10)
            
            # Connect to index
            self.index = self.pc.Index(index_name)
            
            # Get stats
            stats = self.index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            
            logger.info(f"✅ Pinecone initialized: {index_name}")
            logger.info(f"📊 Current vector count: {total_vectors}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Pinecone: {str(e)}")
            raise
    
    def format_metadata(self, standard: str, subject: str, chapter: str, **extra) -> Dict:
        """
        Create properly formatted metadata for Pinecone storage
        
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
        Add document chunks to Pinecone with proper labeling
        
        Args:
            chunks: List of text chunks to add
            standard: Class/Grade number
            subject: Subject name
            chapter: Chapter name/number
            source_file: Original filename
            batch_size: Number of chunks to process at once (Pinecone allows up to 1000)
        
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
                vectors_to_upsert = []
                
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
                        'text': chunk['text'],  # Store text in metadata for retrieval
                        'char_count': len(chunk['text']),
                        'has_equations': chunk.get('has_equations', False),
                        'content_type': chunk.get('content_type', 'general')
                    })
                    
                    # Generate embedding
                    embedding = embedding_model.encode([chunk['text']])[0].tolist()
                    
                    # Prepare vector
                    vectors_to_upsert.append({
                        'id': chunk_id,
                        'values': embedding,
                        'metadata': chunk_metadata
                    })
                
                # Upsert to Pinecone
                self.index.upsert(vectors=vectors_to_upsert)
                
                total_added += len(batch)
                logger.info(f"✅ Added batch {i//batch_size + 1}: {len(batch)} chunks")
            
            logger.info(f"🎉 Successfully added {total_added} chunks to Pinecone")
            return total_added
            
        except Exception as e:
            logger.error(f"❌ Error adding chunks to Pinecone: {str(e)}")
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
        Query Pinecone with optional filters for class, subject, and chapter
        
        Args:
            query_text: The question/query text
            class_num: Filter by class (e.g., "5", "6", "Class 5")
            subject: Filter by subject (e.g., "Mathematics") - NOTE: This is advisory only, not strict
            chapter: Filter by chapter (e.g., "1", "Chapter 1")
            n_results: Number of results to return
        
        Returns:
            Query results with documents and metadata (ChromaDB-compatible format)
        """
        try:
            # Build filter for Pinecone
            # NOTE: We only filter by class and chapter, NOT subject
            # Reason: Subject names in uploaded books may differ from user's terminology
            # (e.g., "Our Wondrous World" vs "Arts", "Mathematics" vs "Maths")
            # The semantic search via embeddings will find the right subject automatically
            filter_dict = {}
            
            if class_num:
                if not str(class_num).lower().startswith('class'):
                    class_num = f"Class {class_num}"
                filter_dict['class'] = {'$eq': class_num}
            
            # REMOVED strict subject filter - let embeddings handle semantic matching
            # This allows finding content even if subject name doesn't match exactly
            
            if chapter:
                if not str(chapter).lower().startswith('chapter'):
                    filter_dict['chapter_raw'] = {'$eq': str(chapter)}
                else:
                    filter_dict['chapter'] = {'$eq': str(chapter)}
            
            # Combine filters with $and if multiple conditions
            if len(filter_dict) > 1:
                pinecone_filter = {'$and': [{k: v} for k, v in filter_dict.items()]}
            elif len(filter_dict) == 1:
                pinecone_filter = filter_dict
            else:
                pinecone_filter = None
            
            # Log what we're searching for (include subject in log even if not filtering)
            search_desc = f"class={class_num}" if class_num else "all classes"
            if subject:
                search_desc += f", looking for {subject} content (semantic)"
            if chapter:
                search_desc += f", chapter={chapter}"
            
            logger.info(f"🔍 Querying Pinecone ({search_desc})")
            logger.info(f"   Filter: {pinecone_filter}")
            
            # Generate query embedding
            query_embedding = embedding_model.encode([query_text])[0].tolist()
            
            # Query Pinecone with higher top_k to get more results for filtering
            # We'll filter by subject programmatically if needed
            query_top_k = n_results * 3 if subject else n_results
            
            results = self.index.query(
                vector=query_embedding,
                top_k=query_top_k,
                filter=pinecone_filter,
                include_metadata=True
            )
            
            # If subject was specified, do post-filtering by checking if subject name contains
            # the search term (case-insensitive partial match)
            matches = results['matches']
            
            if subject and matches:
                subject_lower = subject.lower()
                # Try to filter by subject, but if we get no results, return all
                filtered_matches = [
                    match for match in matches
                    if subject_lower in match['metadata'].get('subject', '').lower()
                ]
                
                if filtered_matches:
                    matches = filtered_matches
                    logger.info(f"✓ Filtered to {len(matches)} results matching subject '{subject}'")
                else:
                    logger.info(f"⚠️  No exact subject match for '{subject}', returning all results from class")
                    matches = matches[:n_results]  # Return top results anyway
            
            # Limit to requested number of results
            matches = matches[:n_results]
            
            # Convert to ChromaDB-compatible format
            documents = [[match['metadata'].get('text', '') for match in matches]]
            metadatas = [[match['metadata'] for match in matches]]
            distances = [[match.get('score', 0.0) for match in matches]]
            
            logger.info(f"🔍 Query returned {len(matches)} results")
            
            return {
                'documents': documents,
                'metadatas': metadatas,
                'distances': distances
            }
            
        except Exception as e:
            logger.error(f"❌ Error querying Pinecone: {str(e)}")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}
    
    def get_available_classes(self) -> List[str]:
        """Get list of all available classes in the database"""
        try:
            # Pinecone doesn't have a direct way to get unique values
            # We'll need to query and extract from results
            # This is a limitation - consider caching in MongoDB
            logger.warning("⚠️  get_available_classes() requires full scan in Pinecone - consider caching")
            return []  # Implement caching in MongoDB if needed
        except Exception as e:
            logger.error(f"❌ Error getting classes: {str(e)}")
            return []
    
    def get_subjects_by_class(self, class_num: str) -> List[str]:
        """Get all subjects available for a specific class"""
        try:
            logger.warning("⚠️  get_subjects_by_class() requires full scan - consider caching in MongoDB")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting subjects: {str(e)}")
            return []
    
    def get_chapters_by_class_subject(self, class_num: str, subject: str) -> List[str]:
        """Get all chapters for a specific class and subject"""
        try:
            logger.warning("⚠️  get_chapters_by_class_subject() requires full scan - consider caching in MongoDB")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting chapters: {str(e)}")
            return []
    
    def get_stats(self) -> Dict:
        """Get statistics about stored documents"""
        try:
            stats = self.index.describe_index_stats()
            
            return {
                'total_vectors': stats.get('total_vector_count', 0),
                'dimension': stats.get('dimension', EMBEDDING_DIMENSION),
                'index_fullness': stats.get('index_fullness', 0.0),
                'namespaces': stats.get('namespaces', {})
            }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {str(e)}")
            return {}
    
    def clear_collection(self):
        """Clear all vectors from the index (use with caution!)"""
        try:
            # Delete all vectors by deleting and recreating index
            self.pc.delete_index(self.index_name)
            logger.info(f"✅ Deleted Pinecone index: {self.index_name}")
            
            # Recreate
            self.pc.create_index(
                name=self.index_name,
                dimension=EMBEDDING_DIMENSION,
                metric='cosine',
                spec=ServerlessSpec(cloud='aws', region='us-east')
            )
            time.sleep(5)
            self.index = self.pc.Index(self.index_name)
            logger.info(f"✅ Recreated Pinecone index: {self.index_name}")
            
        except Exception as e:
            logger.error(f"❌ Error clearing index: {str(e)}")
    
    def delete_by_filter(self, filter_dict: Dict):
        """Delete vectors matching a filter (e.g., specific chapter)"""
        try:
            self.index.delete(filter=filter_dict)
            logger.info(f"✅ Deleted vectors with filter: {filter_dict}")
        except Exception as e:
            logger.error(f"❌ Error deleting by filter: {str(e)}")


# Singleton instance
_pinecone_manager = None


def get_pinecone_manager() -> PineconeDBManager:
    """Get the global Pinecone manager instance"""
    global _pinecone_manager
    if _pinecone_manager is None:
        _pinecone_manager = PineconeDBManager()
    return _pinecone_manager
