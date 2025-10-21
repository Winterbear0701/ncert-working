"""
Smart Test Analysis System
Analyzes student's previous test papers using probability-based algorithms
Identifies important chapters and topics using RAG data
Fast computation without chatbot format
"""
import logging
from typing import Dict, List, Tuple
from collections import defaultdict, Counter
from django.db.models import Avg, Count, Q, Sum, F
from django.utils import timezone
from datetime import timedelta
import numpy as np

from .models import (
    QuizAttempt, QuizAnswer, QuizQuestion, QuizChapter,
    UnitTestAttempt, UnitTestAnswer, StudentChapterProgress
)
from ncert_project.chromadb_utils import get_chromadb_manager

logger = logging.getLogger('students')


class TestAnalyzer:
    """
    Fast probability-based test analyzer
    """
    
    def __init__(self, student):
        self.student = student
        self.chromadb_manager = None
        
    def get_chromadb_manager(self):
        """Lazy load ChromaDB manager"""
        if not self.chromadb_manager:
            self.chromadb_manager = get_chromadb_manager()
        return self.chromadb_manager
    
    def analyze_student_performance(self) -> Dict:
        """
        Main analysis method - fast computation
        Returns comprehensive analysis without chatbot format
        """
        logger.info(f"📊 Analyzing performance for student: {self.student.email}")
        
        # Get all test data
        quiz_data = self._analyze_quiz_attempts()
        unit_test_data = self._analyze_unit_test_attempts()
        
        # Combine and analyze
        chapter_importance = self._calculate_chapter_importance(quiz_data, unit_test_data)
        topic_importance = self._calculate_topic_importance(quiz_data, unit_test_data)
        
        # Get weak areas
        weak_chapters = self._identify_weak_chapters(chapter_importance)
        weak_topics = self._identify_weak_topics(topic_importance)
        
        # Get trend analysis
        performance_trend = self._calculate_performance_trend(quiz_data, unit_test_data)
        
        # Study recommendations based on RAG data
        study_recommendations = self._generate_study_recommendations(
            weak_chapters, weak_topics, chapter_importance
        )
        
        return {
            'summary': {
                'total_quiz_attempts': quiz_data['total_attempts'],
                'total_unit_test_attempts': unit_test_data['total_attempts'],
                'overall_quiz_avg': quiz_data['overall_avg'],
                'overall_unit_test_avg': unit_test_data['overall_avg'],
                'total_chapters_attempted': len(chapter_importance),
                'total_topics_covered': len(topic_importance),
            },
            'chapter_analysis': chapter_importance,
            'topic_analysis': topic_importance,
            'weak_areas': {
                'chapters': weak_chapters,
                'topics': weak_topics,
            },
            'performance_trend': performance_trend,
            'study_recommendations': study_recommendations,
            'analysis_timestamp': timezone.now().isoformat(),
        }
    
    def _analyze_quiz_attempts(self) -> Dict:
        """Analyze all quiz attempts with probability calculations"""
        attempts = QuizAttempt.objects.filter(
            student=self.student,
            status='verified'
        ).select_related('chapter').prefetch_related('answers__question')
        
        total_attempts = attempts.count()
        if total_attempts == 0:
            return {
                'total_attempts': 0,
                'overall_avg': 0,
                'by_chapter': {},
                'by_topic': {},
                'recent_attempts': []
            }
        
        # Calculate overall average
        overall_avg = attempts.aggregate(avg=Avg('score_percentage'))['avg'] or 0
        
        # Group by chapter
        by_chapter = defaultdict(lambda: {
            'attempts': 0,
            'scores': [],
            'avg_score': 0,
            'best_score': 0,
            'worst_score': 100,
            'trend': 'stable',
            'success_rate': 0,
        })
        
        # Group by topic
        by_topic = defaultdict(lambda: {
            'correct': 0,
            'total': 0,
            'accuracy': 0,
            'chapters': set(),
            'difficulty_distribution': {'easy': 0, 'medium': 0, 'hard': 0},
        })
        
        for attempt in attempts:
            chapter_key = f"{attempt.chapter.chapter_id}"
            
            # Chapter stats
            by_chapter[chapter_key]['attempts'] += 1
            by_chapter[chapter_key]['scores'].append(attempt.score_percentage)
            by_chapter[chapter_key]['best_score'] = max(
                by_chapter[chapter_key]['best_score'], 
                attempt.score_percentage
            )
            by_chapter[chapter_key]['worst_score'] = min(
                by_chapter[chapter_key]['worst_score'], 
                attempt.score_percentage
            )
            by_chapter[chapter_key]['chapter_name'] = attempt.chapter.chapter_name
            by_chapter[chapter_key]['subject'] = attempt.chapter.subject
            
            # Topic stats from answers
            answers = attempt.answers.select_related('question').all()
            for answer in answers:
                topic = answer.question.topic
                by_topic[topic]['total'] += 1
                if answer.is_correct:
                    by_topic[topic]['correct'] += 1
                by_topic[topic]['chapters'].add(chapter_key)
                by_topic[topic]['difficulty_distribution'][answer.question.difficulty] += 1
        
        # Calculate derived metrics
        for chapter_key, data in by_chapter.items():
            scores = data['scores']
            data['avg_score'] = np.mean(scores)
            data['success_rate'] = len([s for s in scores if s >= 70]) / len(scores) * 100
            
            # Calculate trend
            if len(scores) >= 3:
                recent_avg = np.mean(scores[-3:])
                older_avg = np.mean(scores[:-3])
                if recent_avg > older_avg + 5:
                    data['trend'] = 'improving'
                elif recent_avg < older_avg - 5:
                    data['trend'] = 'declining'
        
        for topic, data in by_topic.items():
            data['accuracy'] = (data['correct'] / data['total'] * 100) if data['total'] > 0 else 0
            data['chapters'] = list(data['chapters'])
        
        # Recent attempts
        recent_attempts = list(attempts.order_by('-submitted_at')[:5].values(
            'chapter__chapter_name', 'score_percentage', 'submitted_at', 
            'attempt_number', 'chapter__subject'
        ))
        
        return {
            'total_attempts': total_attempts,
            'overall_avg': round(overall_avg, 2),
            'by_chapter': dict(by_chapter),
            'by_topic': dict(by_topic),
            'recent_attempts': recent_attempts,
        }
    
    def _analyze_unit_test_attempts(self) -> Dict:
        """Analyze unit test attempts"""
        attempts = UnitTestAttempt.objects.filter(
            student=self.student,
            status='evaluated'
        ).select_related('unit_test').prefetch_related('answers__question')
        
        total_attempts = attempts.count()
        if total_attempts == 0:
            return {
                'total_attempts': 0,
                'overall_avg': 0,
                'by_chapter': {},
                'by_topic': {},
            }
        
        overall_avg = attempts.aggregate(avg=Avg('overall_score'))['avg'] or 0
        
        by_chapter = defaultdict(lambda: {
            'attempts': 0,
            'scores': [],
            'avg_score': 0,
            'content_scores': [],
            'grammar_scores': [],
        })
        
        by_topic = defaultdict(lambda: {
            'total_marks': 0,
            'obtained_marks': 0,
            'accuracy': 0,
            'attempts': 0,
        })
        
        for attempt in attempts:
            # Get chapter info from unit test
            chapters = attempt.unit_test.chapters.all()
            for chapter in chapters:
                chapter_key = f"{chapter.standard}-{chapter.subject}-{chapter.chapter_number}"
                
                by_chapter[chapter_key]['attempts'] += 1
                by_chapter[chapter_key]['scores'].append(attempt.overall_score)
                by_chapter[chapter_key]['content_scores'].append(attempt.content_score)
                by_chapter[chapter_key]['grammar_scores'].append(attempt.grammar_score)
                by_chapter[chapter_key]['chapter_name'] = chapter.chapter_name
                by_chapter[chapter_key]['subject'] = chapter.subject
            
            # Topic performance
            if attempt.topic_performance:
                for topic, perf in attempt.topic_performance.items():
                    by_topic[topic]['total_marks'] += perf.get('total_marks', 0)
                    by_topic[topic]['obtained_marks'] += perf.get('obtained_marks', 0)
                    by_topic[topic]['attempts'] += 1
        
        # Calculate averages
        for chapter_key, data in by_chapter.items():
            data['avg_score'] = np.mean(data['scores']) if data['scores'] else 0
            data['avg_content'] = np.mean(data['content_scores']) if data['content_scores'] else 0
            data['avg_grammar'] = np.mean(data['grammar_scores']) if data['grammar_scores'] else 0
        
        for topic, data in by_topic.items():
            if data['total_marks'] > 0:
                data['accuracy'] = (data['obtained_marks'] / data['total_marks'] * 100)
        
        return {
            'total_attempts': total_attempts,
            'overall_avg': round(overall_avg, 2),
            'by_chapter': dict(by_chapter),
            'by_topic': dict(by_topic),
        }
    
    def _calculate_chapter_importance(self, quiz_data: Dict, unit_test_data: Dict) -> List[Dict]:
        """
        Calculate chapter importance using probability-based scoring
        Factors: frequency, difficulty, performance, recency
        """
        chapter_scores = {}
        
        # Combine data from both quiz and unit tests
        all_chapters = set(quiz_data['by_chapter'].keys()) | set(unit_test_data['by_chapter'].keys())
        
        for chapter_key in all_chapters:
            quiz_info = quiz_data['by_chapter'].get(chapter_key, {})
            unit_info = unit_test_data['by_chapter'].get(chapter_key, {})
            
            # Calculate importance score (0-100)
            frequency_score = min((quiz_info.get('attempts', 0) + unit_info.get('attempts', 0)) * 10, 30)
            
            # Performance score (inverse - lower performance = higher importance)
            quiz_perf = quiz_info.get('avg_score', 100)
            unit_perf = unit_info.get('avg_score', 100)
            avg_perf = (quiz_perf + unit_perf) / 2 if quiz_perf and unit_perf else (quiz_perf or unit_perf or 100)
            performance_score = (100 - avg_perf) * 0.4  # Max 40 points
            
            # Trend score (declining trend = higher importance)
            trend = quiz_info.get('trend', 'stable')
            trend_score = 20 if trend == 'declining' else (10 if trend == 'stable' else 0)
            
            # Recency score (attempted recently = higher importance)
            recency_score = 10  # Base score if attempted
            
            total_importance = frequency_score + performance_score + trend_score + recency_score
            
            chapter_scores[chapter_key] = {
                'chapter_key': chapter_key,
                'chapter_name': quiz_info.get('chapter_name') or unit_info.get('chapter_name', 'Unknown'),
                'subject': quiz_info.get('subject') or unit_info.get('subject', 'Unknown'),
                'importance_score': round(total_importance, 2),
                'quiz_attempts': quiz_info.get('attempts', 0),
                'unit_test_attempts': unit_info.get('attempts', 0),
                'quiz_avg': round(quiz_info.get('avg_score', 0), 2),
                'unit_test_avg': round(unit_info.get('avg_score', 0), 2),
                'trend': trend,
                'difficulty_level': self._classify_difficulty(avg_perf),
                'priority': self._classify_priority(total_importance),
            }
        
        # Sort by importance score descending
        sorted_chapters = sorted(
            chapter_scores.values(), 
            key=lambda x: x['importance_score'], 
            reverse=True
        )
        
        return sorted_chapters
    
    def _calculate_topic_importance(self, quiz_data: Dict, unit_test_data: Dict) -> List[Dict]:
        """Calculate topic importance scores"""
        topic_scores = {}
        
        # Combine topics
        all_topics = set(quiz_data['by_topic'].keys()) | set(unit_test_data['by_topic'].keys())
        
        for topic in all_topics:
            quiz_info = quiz_data['by_topic'].get(topic, {})
            unit_info = unit_test_data['by_topic'].get(topic, {})
            
            # Frequency score
            quiz_attempts = quiz_info.get('total', 0)
            unit_attempts = unit_info.get('attempts', 0)
            frequency_score = min((quiz_attempts + unit_attempts) * 2, 30)
            
            # Accuracy score (inverse)
            quiz_acc = quiz_info.get('accuracy', 100)
            unit_acc = unit_info.get('accuracy', 100)
            avg_acc = (quiz_acc + unit_acc) / 2 if quiz_acc and unit_acc else (quiz_acc or unit_acc or 100)
            accuracy_score = (100 - avg_acc) * 0.5
            
            # Difficulty distribution
            diff_dist = quiz_info.get('difficulty_distribution', {})
            difficulty_score = (diff_dist.get('hard', 0) * 2 + diff_dist.get('medium', 0)) * 2
            
            total_importance = frequency_score + accuracy_score + difficulty_score
            
            topic_scores[topic] = {
                'topic': topic,
                'importance_score': round(total_importance, 2),
                'quiz_attempts': quiz_attempts,
                'unit_test_attempts': unit_attempts,
                'quiz_accuracy': round(quiz_acc, 2),
                'unit_test_accuracy': round(unit_acc, 2),
                'chapters': quiz_info.get('chapters', []),
                'priority': self._classify_priority(total_importance),
            }
        
        sorted_topics = sorted(
            topic_scores.values(),
            key=lambda x: x['importance_score'],
            reverse=True
        )
        
        return sorted_topics
    
    def _identify_weak_chapters(self, chapter_importance: List[Dict]) -> List[Dict]:
        """Identify chapters needing attention"""
        weak = []
        for chapter in chapter_importance:
            # Weak if: low average OR high importance OR declining trend
            is_weak = (
                chapter['quiz_avg'] < 70 or 
                chapter['unit_test_avg'] < 70 or
                chapter['importance_score'] > 60 or
                chapter['trend'] == 'declining'
            )
            
            if is_weak:
                weak.append({
                    'chapter_name': chapter['chapter_name'],
                    'subject': chapter['subject'],
                    'reason': self._get_weakness_reason(chapter),
                    'recommended_action': self._get_recommended_action(chapter),
                    'priority': chapter['priority'],
                })
        
        return weak[:10]  # Top 10 weak chapters
    
    def _identify_weak_topics(self, topic_importance: List[Dict]) -> List[Dict]:
        """Identify topics needing attention"""
        weak = []
        for topic_data in topic_importance:
            is_weak = (
                topic_data['quiz_accuracy'] < 60 or
                topic_data['unit_test_accuracy'] < 60 or
                topic_data['importance_score'] > 50
            )
            
            if is_weak:
                weak.append({
                    'topic': topic_data['topic'],
                    'quiz_accuracy': topic_data['quiz_accuracy'],
                    'unit_test_accuracy': topic_data['unit_test_accuracy'],
                    'priority': topic_data['priority'],
                    'chapters': topic_data['chapters'],
                })
        
        return weak[:15]  # Top 15 weak topics
    
    def _calculate_performance_trend(self, quiz_data: Dict, unit_test_data: Dict) -> Dict:
        """Calculate overall performance trend"""
        recent_attempts = quiz_data.get('recent_attempts', [])
        
        if len(recent_attempts) < 2:
            return {
                'trend': 'insufficient_data',
                'message': 'Need more attempts to calculate trend',
            }
        
        scores = [att['score_percentage'] for att in recent_attempts]
        scores.reverse()  # Chronological order
        
        # Simple linear regression
        x = np.arange(len(scores))
        slope = np.polyfit(x, scores, 1)[0]
        
        if slope > 2:
            trend = 'improving'
            message = f'Performance improving by ~{abs(slope):.1f}% per attempt'
        elif slope < -2:
            trend = 'declining'
            message = f'Performance declining by ~{abs(slope):.1f}% per attempt'
        else:
            trend = 'stable'
            message = 'Performance is stable'
        
        return {
            'trend': trend,
            'slope': round(slope, 2),
            'message': message,
            'recent_scores': scores[-5:],
        }
    
    def _generate_study_recommendations(self, weak_chapters: List[Dict], 
                                       weak_topics: List[Dict], 
                                       chapter_importance: List[Dict]) -> List[Dict]:
        """Generate smart study recommendations using RAG data"""
        recommendations = []
        
        # Top 5 priority chapters
        priority_chapters = [ch for ch in chapter_importance if ch['priority'] in ['Critical', 'High']][:5]
        
        for chapter in priority_chapters:
            rec = {
                'type': 'chapter',
                'chapter_name': chapter['chapter_name'],
                'subject': chapter['subject'],
                'priority': chapter['priority'],
                'reason': f"Importance score: {chapter['importance_score']:.0f}/100",
                'study_time_minutes': self._estimate_study_time(chapter),
                'focus_areas': [],
            }
            
            # Get topics for this chapter
            chapter_topics = [t for t in weak_topics if chapter['chapter_key'] in t.get('chapters', [])]
            rec['focus_areas'] = [t['topic'] for t in chapter_topics[:3]]
            
            recommendations.append(rec)
        
        # Top 5 topics that appear across multiple chapters
        cross_chapter_topics = [t for t in weak_topics if len(t.get('chapters', [])) > 1][:5]
        
        for topic_data in cross_chapter_topics:
            recommendations.append({
                'type': 'topic',
                'topic': topic_data['topic'],
                'priority': topic_data['priority'],
                'chapters_affected': len(topic_data['chapters']),
                'reason': f"Low accuracy: {topic_data['quiz_accuracy']:.0f}%",
                'study_time_minutes': 30,
            })
        
        return recommendations
    
    def _classify_difficulty(self, avg_score: float) -> str:
        """Classify difficulty based on performance"""
        if avg_score >= 80:
            return 'Easy'
        elif avg_score >= 60:
            return 'Medium'
        else:
            return 'Hard'
    
    def _classify_priority(self, importance_score: float) -> str:
        """Classify priority level"""
        if importance_score >= 70:
            return 'Critical'
        elif importance_score >= 50:
            return 'High'
        elif importance_score >= 30:
            return 'Medium'
        else:
            return 'Low'
    
    def _get_weakness_reason(self, chapter: Dict) -> str:
        """Get human-readable reason for weakness"""
        reasons = []
        if chapter['quiz_avg'] < 70:
            reasons.append(f"Quiz average {chapter['quiz_avg']:.0f}%")
        if chapter['unit_test_avg'] < 70:
            reasons.append(f"Unit test average {chapter['unit_test_avg']:.0f}%")
        if chapter['trend'] == 'declining':
            reasons.append("Declining performance trend")
        if chapter['importance_score'] > 60:
            reasons.append("High importance score")
        
        return "; ".join(reasons) if reasons else "Needs attention"
    
    def _get_recommended_action(self, chapter: Dict) -> str:
        """Get recommended action"""
        if chapter['quiz_avg'] < 50:
            return "Re-study fundamentals, review notes, take practice quiz"
        elif chapter['trend'] == 'declining':
            return "Review recent mistakes, practice more problems"
        else:
            return "Regular practice, focus on weak topics"
    
    def _estimate_study_time(self, chapter: Dict) -> int:
        """Estimate required study time in minutes"""
        base_time = 45
        
        # Adjust based on performance
        if chapter['quiz_avg'] < 50:
            return base_time + 30
        elif chapter['quiz_avg'] < 70:
            return base_time + 15
        
        return base_time


def get_student_analysis(student) -> Dict:
    """
    Quick function to get student analysis
    Usage: analysis = get_student_analysis(request.user)
    """
    analyzer = TestAnalyzer(student)
    return analyzer.analyze_student_performance()
