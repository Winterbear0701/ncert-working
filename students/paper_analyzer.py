"""
Previous Year Paper Analyzer
Extracts questions from uploaded PDFs and analyzes them using RAG
to identify important chapters, topics, and questions for exam preparation
"""
import logging
import re
import time
from typing import Dict, List, Tuple
from collections import Counter, defaultdict
import PyPDF2
import openai
import google.generativeai as genai
import os

from django.conf import settings
from ncert_project.chromadb_utils import get_chromadb_manager

logger = logging.getLogger('students')


class PaperAnalyzer:
    """
    Analyzes previous year question papers using RAG
    """
    
    def __init__(self):
        self.chromadb_manager = None
        # Configure AI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            genai.configure(api_key=gemini_key)
    
    def get_chromadb_manager(self):
        """Lazy load ChromaDB"""
        if not self.chromadb_manager:
            self.chromadb_manager = get_chromadb_manager()
        return self.chromadb_manager
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        try:
            logger.info(f"📄 Extracting text from PDF: {pdf_path}")
            
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n\n"
                
                logger.info(f"✅ Extracted {len(text)} characters from {len(pdf_reader.pages)} pages")
                return text.strip()
                
        except Exception as e:
            logger.error(f"❌ Error extracting PDF text: {str(e)}")
            return ""
    
    def extract_questions_with_ai(self, text: str, standard: str, subject: str) -> List[Dict]:
        """
        Use AI to extract individual questions from the paper text
        Returns list of questions with metadata
        """
        logger.info(f"🤖 Extracting questions using AI for {standard} {subject}")
        
        prompt = f"""You are analyzing a previous year question paper for Class {standard} {subject}.

Extract ALL questions from this paper. For each question, identify:
1. Question number
2. Question text (full question)
3. Marks allocated
4. Topic/concept being tested
5. Question type (MCQ, Short Answer, Long Answer, Numerical, etc.)

Paper text:
{text[:8000]}  # Limit to avoid token limits

Return a JSON array of questions in this exact format:
[
  {{
    "question_number": "1",
    "question_text": "Define photosynthesis...",
    "marks": 2,
    "topic": "Photosynthesis",
    "question_type": "Short Answer",
    "estimated_difficulty": "Easy"
  }},
  ...
]

Be thorough and extract ALL questions. Return ONLY the JSON array, no other text."""

        try:
            # Try Gemini first (free)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Extract JSON from response
            import json
            
            # Try to find JSON array in response
            if result_text.startswith('['):
                questions = json.loads(result_text)
            else:
                # Try to extract JSON from markdown code block
                match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', result_text, re.DOTALL)
                if match:
                    questions = json.loads(match.group(1))
                else:
                    # Last resort: find array in text
                    match = re.search(r'\[.*\]', result_text, re.DOTALL)
                    if match:
                        questions = json.loads(match.group(0))
                    else:
                        logger.error("Could not find JSON array in AI response")
                        return []
            
            logger.info(f"✅ Extracted {len(questions)} questions using AI")
            return questions
            
        except Exception as e:
            logger.error(f"❌ Error extracting questions with AI: {str(e)}")
            return self._fallback_question_extraction(text)
    
    def _fallback_question_extraction(self, text: str) -> List[Dict]:
        """Fallback: Simple pattern-based question extraction"""
        logger.info("⚠️ Using fallback question extraction")
        
        questions = []
        # Look for common question patterns
        patterns = [
            r'(?:Q|Question|^\d+[\.\):])\s*(.+?)(?=(?:Q|Question|\d+[\.\):])|$)',
            r'^\d+[\.\)]\s*(.+?)(?=\n\d+[\.\)]|\Z)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE)
            for i, match in enumerate(matches, 1):
                question_text = match.group(1).strip()
                if len(question_text) > 10:  # Filter out too short matches
                    questions.append({
                        'question_number': str(i),
                        'question_text': question_text[:500],  # Limit length
                        'marks': 0,
                        'topic': 'Unknown',
                        'question_type': 'Unknown',
                        'estimated_difficulty': 'Medium'
                    })
        
        return questions[:50]  # Limit to 50 questions
    
    def analyze_questions_with_rag(self, questions: List[Dict], standard: str, subject: str) -> Dict:
        """
        Analyze questions against RAG database to identify important chapters/topics
        Fast probability-based scoring
        """
        start_time = time.time()
        logger.info(f"📊 Analyzing {len(questions)} questions with RAG")
        
        chromadb = self.get_chromadb_manager()
        
        # Initialize counters
        chapter_scores = defaultdict(lambda: {
            'frequency': 0,
            'total_marks': 0,
            'questions': [],
            'topics': set(),
            'importance_score': 0
        })
        
        topic_scores = defaultdict(lambda: {
            'frequency': 0,
            'total_marks': 0,
            'questions': [],
            'chapters': set(),
            'importance_score': 0
        })
        
        question_types = Counter()
        
        # Analyze each question
        for question in questions:
            q_text = question.get('question_text', '')
            q_marks = question.get('marks', 0)
            q_topic = question.get('topic', 'Unknown')
            q_type = question.get('question_type', 'Unknown')
            
            question_types[q_type] += 1
            
            # Query RAG to find matching chapter/topic
            try:
                # Search in ChromaDB
                results = chromadb.query_documents(
                    query=q_text,
                    top_k=3,
                    filters={
                        'standard': standard,
                        'subject': subject
                    }
                )
                
                if results and results.get('metadatas'):
                    for metadata in results['metadatas'][0][:1]:  # Take top match
                        chapter_name = metadata.get('chapter_name', 'Unknown')
                        
                        # Update chapter scores
                        chapter_scores[chapter_name]['frequency'] += 1
                        chapter_scores[chapter_name]['total_marks'] += q_marks
                        chapter_scores[chapter_name]['questions'].append({
                            'number': question.get('question_number'),
                            'text': q_text[:200],
                            'marks': q_marks
                        })
                        chapter_scores[chapter_name]['topics'].add(q_topic)
                        
                        # Update topic scores
                        topic_scores[q_topic]['frequency'] += 1
                        topic_scores[q_topic]['total_marks'] += q_marks
                        topic_scores[q_topic]['chapters'].add(chapter_name)
                        topic_scores[q_topic]['questions'].append(question.get('question_number'))
            
            except Exception as e:
                logger.warning(f"Error querying RAG for question: {str(e)}")
                continue
        
        # Calculate importance scores
        self._calculate_importance_scores(chapter_scores, len(questions))
        self._calculate_importance_scores(topic_scores, len(questions))
        
        # Convert sets to lists for JSON serialization
        for chapter in chapter_scores.values():
            chapter['topics'] = list(chapter['topics'])
        
        for topic in topic_scores.values():
            topic['chapters'] = list(topic['chapters'])
        
        # Sort by importance
        sorted_chapters = sorted(
            chapter_scores.items(),
            key=lambda x: x[1]['importance_score'],
            reverse=True
        )
        
        sorted_topics = sorted(
            topic_scores.items(),
            key=lambda x: x[1]['importance_score'],
            reverse=True
        )
        
        processing_time = time.time() - start_time
        
        logger.info(f"✅ Analysis complete in {processing_time:.2f}s")
        logger.info(f"📚 Found {len(chapter_scores)} chapters, {len(topic_scores)} topics")
        
        return {
            'chapter_importance': dict(sorted_chapters),
            'topic_importance': dict(sorted_topics),
            'question_frequency': dict(question_types),
            'total_questions': len(questions),
            'processing_time': processing_time,
            'priority_chapters': self._get_priority_list(sorted_chapters, 10),
            'priority_topics': self._get_priority_list(sorted_topics, 15),
        }
    
    def _calculate_importance_scores(self, scores_dict: Dict, total_questions: int):
        """Calculate importance score (0-100) for each item"""
        for item_name, data in scores_dict.items():
            frequency = data['frequency']
            marks = data['total_marks']
            
            # Frequency score (0-50 points)
            frequency_score = min((frequency / total_questions) * 100, 50)
            
            # Marks score (0-30 points)
            marks_score = min((marks / (total_questions * 5)) * 100, 30) if marks > 0 else 0
            
            # Question coverage (0-20 points)
            coverage_score = min((len(data['questions']) / total_questions) * 100, 20)
            
            data['importance_score'] = round(frequency_score + marks_score + coverage_score, 2)
    
    def _get_priority_list(self, sorted_items: List[Tuple], limit: int) -> List[Dict]:
        """Get top priority items with details"""
        priority = []
        for name, data in sorted_items[:limit]:
            priority.append({
                'name': name,
                'importance_score': data['importance_score'],
                'frequency': data['frequency'],
                'total_marks': data['total_marks'],
                'priority': self._classify_priority(data['importance_score']),
            })
        return priority
    
    def _classify_priority(self, score: float) -> str:
        """Classify priority level"""
        if score >= 70:
            return 'Critical'
        elif score >= 50:
            return 'High'
        elif score >= 30:
            return 'Medium'
        else:
            return 'Low'
    
    def generate_study_strategy(self, analysis_results: Dict, available_days: int = 30) -> Dict:
        """
        Generate personalized study strategy based on analysis
        """
        logger.info(f"📝 Generating study strategy for {available_days} days")
        
        priority_chapters = analysis_results.get('priority_chapters', [])
        priority_topics = analysis_results.get('priority_topics', [])
        
        # Estimate study time per chapter
        total_importance = sum(ch['importance_score'] for ch in priority_chapters)
        
        study_plan = []
        for chapter in priority_chapters:
            if total_importance > 0:
                time_percentage = chapter['importance_score'] / total_importance
                days_needed = round(available_days * time_percentage, 1)
                
                study_plan.append({
                    'chapter': chapter['name'],
                    'priority': chapter['priority'],
                    'importance_score': chapter['importance_score'],
                    'estimated_days': max(1, days_needed),
                    'study_approach': self._get_study_approach(chapter),
                })
        
        return {
            'total_chapters_to_cover': len(priority_chapters),
            'critical_chapters': len([ch for ch in priority_chapters if ch['priority'] == 'Critical']),
            'high_priority_chapters': len([ch for ch in priority_chapters if ch['priority'] == 'High']),
            'available_days': available_days,
            'study_plan': study_plan,
            'daily_hours_needed': self._estimate_daily_hours(priority_chapters, available_days),
            'success_probability': self._estimate_success_probability(priority_chapters, available_days),
        }
    
    def _get_study_approach(self, chapter: Dict) -> str:
        """Recommend study approach based on chapter data"""
        if chapter['frequency'] >= 5:
            return "Deep study - High frequency in papers. Master all concepts and practice extensively."
        elif chapter['total_marks'] >= 20:
            return "Focus on high-mark questions. Understand key concepts and practice typical questions."
        elif chapter['priority'] == 'Critical':
            return "Priority study - Very important. Cover all major topics and practice past questions."
        else:
            return "Quick revision - Cover main concepts and key formulas/definitions."
    
    def _estimate_daily_hours(self, chapters: List[Dict], days: int) -> float:
        """Estimate daily study hours needed"""
        total_chapters = len([ch for ch in chapters if ch['priority'] in ['Critical', 'High']])
        hours_per_chapter = 4  # Average
        total_hours = total_chapters * hours_per_chapter
        return round(total_hours / days, 1) if days > 0 else 0
    
    def _estimate_success_probability(self, chapters: List[Dict], days: int) -> int:
        """Estimate success probability percentage"""
        critical_count = len([ch for ch in chapters if ch['priority'] == 'Critical'])
        high_count = len([ch for ch in chapters if ch['priority'] == 'High'])
        
        total_important = critical_count + high_count
        days_per_chapter = days / total_important if total_important > 0 else 0
        
        if days_per_chapter >= 3:
            return 90
        elif days_per_chapter >= 2:
            return 75
        elif days_per_chapter >= 1:
            return 60
        else:
            return 40
    
    def process_paper(self, paper_path: str, standard: str, subject: str, 
                     available_days: int = 30) -> Dict:
        """
        Complete workflow: Extract → Analyze → Strategize
        """
        logger.info(f"🚀 Starting paper analysis for {standard} {subject}")
        
        # Step 1: Extract text
        text = self.extract_text_from_pdf(paper_path)
        if not text:
            return {'error': 'Failed to extract text from PDF'}
        
        # Step 2: Extract questions
        questions = self.extract_questions_with_ai(text, standard, subject)
        if not questions:
            return {'error': 'Failed to extract questions from paper'}
        
        # Step 3: Analyze with RAG
        analysis = self.analyze_questions_with_rag(questions, standard, subject)
        
        # Step 4: Generate study strategy
        strategy = self.generate_study_strategy(analysis, available_days)
        analysis['study_strategy'] = strategy
        analysis['questions_list'] = questions
        analysis['extracted_text'] = text[:5000]  # Store first 5000 chars
        
        return analysis


def analyze_multiple_papers(paper_paths: List[str], standard: str, subject: str, 
                            available_days: int = 30) -> Dict:
    """
    Analyze multiple papers together for comprehensive analysis
    """
    analyzer = PaperAnalyzer()
    
    combined_questions = []
    combined_chapter_scores = defaultdict(lambda: {
        'frequency': 0, 'total_marks': 0, 'questions': [], 
        'topics': set(), 'importance_score': 0
    })
    combined_topic_scores = defaultdict(lambda: {
        'frequency': 0, 'total_marks': 0, 'questions': [], 
        'chapters': set(), 'importance_score': 0
    })
    
    logger.info(f"📚 Analyzing {len(paper_paths)} papers together")
    
    # Process each paper
    for paper_path in paper_paths:
        result = analyzer.process_paper(paper_path, standard, subject, available_days)
        
        if 'error' not in result:
            combined_questions.extend(result.get('questions_list', []))
            
            # Merge chapter scores
            for chapter, data in result.get('chapter_importance', {}).items():
                combined_chapter_scores[chapter]['frequency'] += data.get('frequency', 0)
                combined_chapter_scores[chapter]['total_marks'] += data.get('total_marks', 0)
                combined_chapter_scores[chapter]['questions'].extend(data.get('questions', []))
                combined_chapter_scores[chapter]['topics'].update(data.get('topics', []))
    
    # Recalculate scores
    analyzer._calculate_importance_scores(combined_chapter_scores, len(combined_questions))
    
    # Sort and format
    sorted_chapters = sorted(
        combined_chapter_scores.items(),
        key=lambda x: x[1]['importance_score'],
        reverse=True
    )
    
    # Generate combined strategy
    analysis = {
        'chapter_importance': dict(sorted_chapters),
        'total_questions': len(combined_questions),
        'total_papers': len(paper_paths),
        'priority_chapters': analyzer._get_priority_list(sorted_chapters, 10),
    }
    
    strategy = analyzer.generate_study_strategy(analysis, available_days)
    analysis['study_strategy'] = strategy
    
    return analysis
