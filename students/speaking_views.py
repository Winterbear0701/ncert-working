"""
Speaking Practice Views
AI-powered speaking practice room with real-time conversation and detailed analytics
"""
import os
import logging
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import openai
import google.generativeai as genai

from .models import SpeakingSession

logger = logging.getLogger('students')

# Configure API keys
openai.api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)


@login_required
def speaking_practice_room(request):
    """
    Main speaking practice room page
    Like Zoom meeting but audio-only for AI conversation
    """
    # Get student's previous sessions for progress tracking
    previous_sessions = SpeakingSession.objects.filter(
        student=request.user
    ).order_by('-created_at')[:5]
    
    context = {
        'user': request.user,
        'previous_sessions': previous_sessions,
    }
    
    return render(request, 'students/speaking_practice.html', context)


@login_required
@require_POST
def speaking_practice_respond(request):
    """
    Generate AI response during speaking practice session
    Maintains conversation context and provides appropriate responses
    """
    try:
        data = json.loads(request.body)
        student_message = data.get('student_message', '').strip()
        conversation_history = data.get('conversation_history', [])
        practice_type = data.get('practice_type', 'free')
        
        if not student_message:
            return JsonResponse({
                "status": "error",
                "error": "Message cannot be empty"
            }, status=400)
        
        # Build conversation context
        context_messages = []
        
        # System prompt based on practice type
        system_prompts = {
            'free': (
                "You are a friendly English tutor having a natural conversation with a student. "
                "Ask follow-up questions, show interest in their answers, and encourage them to speak more. "
                "Keep responses concise (2-3 sentences) to maintain conversation flow. "
                "Occasionally ask them to elaborate or explain concepts."
            ),
            'topic': (
                "You are an English tutor discussing educational topics with a student. "
                "Ask probing questions about the topic, encourage critical thinking, and "
                "help them articulate their thoughts clearly. Keep responses brief and engaging."
            ),
            'presentation': (
                "You are evaluating a student's presentation. Listen to their explanation, "
                "then ask clarifying questions about their topic. Challenge them respectfully "
                "and encourage them to defend their points. Keep responses brief."
            ),
            'interview': (
                "You are conducting a friendly interview with a student. Ask relevant questions "
                "about their interests, goals, and knowledge. Follow up on their answers and "
                "create a comfortable atmosphere. Keep responses brief."
            ),
        }
        
        system_prompt = system_prompts.get(practice_type, system_prompts['free'])
        context_messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        for turn in conversation_history[-10:]:  # Last 10 turns for context
            role = "assistant" if turn['speaker'] == 'ai' else "user"
            context_messages.append({"role": role, "content": turn['text']})
        
        # Add current message
        context_messages.append({"role": "user", "content": student_message})
        
        # Generate AI response
        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=context_messages,
                temperature=0.8,  # More creative for natural conversation
                max_tokens=150,  # Keep responses concise
            )
            ai_response = response.choices[0].message.content
            
        except Exception as openai_error:
            logger.error(f"OpenAI error in speaking practice: {openai_error}")
            
            # Fallback to Gemini
            try:
                model = genai.GenerativeModel("gemini-2.0-flash-exp")
                
                # Build prompt for Gemini
                full_prompt = f"{system_prompt}\n\nConversation so far:\n"
                for turn in conversation_history[-10:]:
                    speaker = "You" if turn['speaker'] == 'ai' else "Student"
                    full_prompt += f"{speaker}: {turn['text']}\n"
                full_prompt += f"\nStudent: {student_message}\nYou:"
                
                response = model.generate_content(full_prompt)
                ai_response = response.text
                
            except Exception as gemini_error:
                logger.error(f"Gemini error in speaking practice: {gemini_error}")
                return JsonResponse({
                    "status": "error",
                    "error": "AI service temporarily unavailable"
                }, status=500)
        
        return JsonResponse({
            "status": "success",
            "response": ai_response
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON"
        }, status=400)
    except Exception as e:
        logger.error(f"Error in speaking practice respond: {e}")
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@login_required
@require_POST
def analyze_speaking_session(request):
    """
    Comprehensive analysis of speaking practice session
    Provides grammar, fluency, vocabulary scores and detailed feedback
    """
    try:
        data = json.loads(request.body)
        conversation = data.get('conversation', [])
        duration = data.get('duration', 0)
        practice_type = data.get('practice_type', 'free')
        
        if not conversation or duration <= 0:
            return JsonResponse({
                "status": "error",
                "error": "Invalid session data"
            }, status=400)
        
        # Extract student's speech
        student_utterances = [
            turn['text'] for turn in conversation 
            if turn['speaker'] == 'student'
        ]
        
        student_text = "\n".join(student_utterances)
        word_count = len(student_text.split())
        exchange_count = len([t for t in conversation if t['speaker'] == 'student'])
        
        # Build analysis prompt
        analysis_prompt = f"""
Analyze this student's English speaking practice session and provide detailed feedback.

**Session Details:**
- Duration: {duration} seconds ({duration // 60} minutes)
- Total words spoken by student: {word_count}
- Number of speaking turns: {exchange_count}
- Practice type: {practice_type}

**Student's Complete Speech:**
{student_text}

**Full Conversation Context:**
{json.dumps(conversation, indent=2)}

**Task:** Provide a comprehensive analysis in the following JSON format:

{{
    "overall_score": <0-100>,
    "grammar_score": <0-100>,
    "fluency_score": <0-100>,
    "vocabulary_score": <0-100>,
    "pronunciation_score": <0-100>,
    "coherence_score": <0-100>,
    "confidence_score": <0-100>,
    
    "grammar_errors": [
        {{"error": "was went", "correction": "went", "count": 2, "rule": "Simple past tense"}},
        {{"error": "don't knows", "correction": "don't know", "count": 1, "rule": "Verb agreement"}}
    ],
    
    "filler_words": [
        {{"word": "um", "count": 5}},
        {{"word": "like", "count": 3}},
        {{"word": "you know", "count": 2}}
    ],
    
    "speaking_pace": {{
        "words_per_minute": <calculated WPM>,
        "ideal_range": "130-150",
        "assessment": "Too fast / Just right / Too slow",
        "feedback": "Brief feedback on speaking speed"
    }},
    
    "strengths": [
        "Clear pronunciation of technical terms",
        "Good use of transitional phrases",
        "Confident tone"
    ],
    
    "improvements": [
        "Work on past tense usage",
        "Reduce filler words",
        "Slow down speaking pace"
    ],
    
    "suggestions": [
        {{
            "category": "Grammar",
            "issue": "Past tense errors",
            "examples": [
                {{"wrong": "I was went to school", "correct": "I went to school"}},
                {{"wrong": "She was came yesterday", "correct": "She came yesterday"}}
            ],
            "tip": "Use simple past tense without 'was' for action verbs"
        }},
        {{
            "category": "Fluency",
            "issue": "Excessive filler words",
            "examples": [
                {{"filler": "um", "alternative": "Take a brief pause"}},
                {{"filler": "like", "alternative": "Remove entirely or use 'such as'"}}
            ],
            "tip": "Practice speaking with deliberate pauses instead of fillers"
        }}
    ],
    
    "vocabulary_enhancement": [
        {{"basic": "very important", "advanced": "crucial / essential / vital"}},
        {{"basic": "and also", "advanced": "furthermore / moreover / additionally"}},
        {{"basic": "a lot of", "advanced": "numerous / abundant / substantial"}}
    ],
    
    "best_exchanges": [
        {{
            "text": "Exact quote from student",
            "reason": "Perfect grammar and clear explanation"
        }}
    ],
    
    "needs_work": [
        {{
            "text": "Exact quote from student with error",
            "issue": "Subject-verb agreement error",
            "correction": "Corrected version"
        }}
    ],
    
    "progress_tips": [
        "Practice speaking for 10 minutes daily",
        "Record yourself and listen back",
        "Read aloud to improve fluency"
    ]
}}

**Important:**
- Be encouraging but honest
- Provide specific, actionable feedback
- Include exact quotes from the student's speech
- Consider the student's level and context
- Pronunciation score is estimated based on grammar and vocabulary (since we don't have audio)
"""
        
        # Get AI analysis
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert English language tutor specializing in speaking assessment and feedback."
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for consistent analysis
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
        except Exception as openai_error:
            logger.error(f"OpenAI analysis error: {openai_error}")
            
            # Fallback to Gemini
            try:
                model = genai.GenerativeModel("gemini-2.0-flash-exp")
                response = model.generate_content(analysis_prompt)
                # Extract JSON from response
                response_text = response.text
                # Find JSON in markdown code blocks if present
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                
                analysis = json.loads(response_text.strip())
                
            except Exception as gemini_error:
                logger.error(f"Gemini analysis error: {gemini_error}")
                return JsonResponse({
                    "status": "error",
                    "error": "Analysis service temporarily unavailable"
                }, status=500)
        
        # Save session to database
        try:
            session = SpeakingSession.objects.create(
                student=request.user,
                practice_type=practice_type,
                duration=duration,
                exchange_count=exchange_count,
                word_count=word_count,
                conversation_data=conversation,
                overall_score=analysis.get('overall_score', 0),
                grammar_score=analysis.get('grammar_score', 0),
                fluency_score=analysis.get('fluency_score', 0),
                vocabulary_score=analysis.get('vocabulary_score', 0),
                pronunciation_score=analysis.get('pronunciation_score', 0),
                coherence_score=analysis.get('coherence_score', 0),
                confidence_score=analysis.get('confidence_score', 0),
                grammar_errors=analysis.get('grammar_errors', []),
                filler_words=analysis.get('filler_words', []),
                speaking_pace=analysis.get('speaking_pace', {}),
                strengths=analysis.get('strengths', []),
                improvements=analysis.get('improvements', []),
                suggestions=analysis.get('suggestions', []),
                vocabulary_enhancement=analysis.get('vocabulary_enhancement', []),
                best_exchanges=analysis.get('best_exchanges', []),
                needs_work=analysis.get('needs_work', []),
            )
            
            logger.info(f"[OK] Speaking session saved: {session.id} - Score: {session.overall_score}/100")
            
        except Exception as db_error:
            logger.error(f"Error saving speaking session: {db_error}")
            # Continue anyway - return analysis even if save fails
        
        # Add session ID to response
        analysis['session_id'] = session.id if session else None
        analysis['status'] = 'success'
        
        return JsonResponse(analysis)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "error": "Invalid JSON"
        }, status=400)
    except Exception as e:
        logger.error(f"Error analyzing speaking session: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


@login_required
def speaking_practice_history(request):
    """
    View student's speaking practice history with progress tracking
    """
    sessions = SpeakingSession.objects.filter(
        student=request.user
    ).order_by('-created_at')
    
    # Calculate progress statistics
    if sessions.exists():
        total_sessions = sessions.count()
        avg_score = sum(s.overall_score for s in sessions) / total_sessions
        total_practice_time = sum(s.duration for s in sessions)
        
        # Get recent improvement trend
        recent_sessions = list(sessions[:5])
        if len(recent_sessions) >= 2:
            recent_avg = sum(s.overall_score for s in recent_sessions[:3]) / min(3, len(recent_sessions))
            older_avg = sum(s.overall_score for s in recent_sessions) / len(recent_sessions)
            improvement = recent_avg - older_avg
        else:
            improvement = 0
        
        progress_stats = {
            'total_sessions': total_sessions,
            'avg_score': round(avg_score, 1),
            'total_practice_time': total_practice_time,
            'total_practice_hours': round(total_practice_time / 3600, 1),
            'improvement_trend': round(improvement, 1),
        }
    else:
        progress_stats = None
    
    context = {
        'sessions': sessions[:20],  # Last 20 sessions
        'progress_stats': progress_stats,
    }
    
    return render(request, 'students/speaking_practice_history.html', context)


@login_required
def speaking_practice_detail(request, session_id):
    """
    View detailed analysis of a specific speaking session
    """
    try:
        session = SpeakingSession.objects.get(
            id=session_id,
            student=request.user
        )
    except SpeakingSession.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "error": "Session not found"
        }, status=404)
    
    context = {
        'session': session,
    }
    
    return render(request, 'students/speaking_practice_detail.html', context)
