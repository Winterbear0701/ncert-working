"""
Adaptive Difficulty System for Chatbot
Adjusts response complexity based on user's comprehension level
Detects confusion signals and simplifies explanations
"""
import re
import logging
from typing import Tuple

logger = logging.getLogger('students')


def detect_confusion_signals(message: str) -> bool:
    """
    Detect if user is confused or needs simpler explanation
    Returns True if confusion signals found
    """
    confusion_patterns = [
        r'\b(don\'t|dont|do not) understand\b',
        r'\bconfuse(d)?\b',
        r'\bexplain (simpler|simple|easier|easy|basic|clearly)\b',
        r'\bI\'m lost\b',
        r'\btoo (hard|difficult|complex|complicated)\b',
        r'\bcan you (simplify|make it simple|explain better)\b',
        r'\bnot clear\b',
        r'\bwhat (do|does) (that|this|it) mean\b',
        r'\bin simple (words|terms|language)\b',
        r'\blike I\'m \d+( years old)?\b',  # "explain like I'm 5"
        r'\bstep by step\b',
        r'\bbreak it down\b',
    ]
    
    message_lower = message.lower()
    
    for pattern in confusion_patterns:
        if re.search(pattern, message_lower):
            logger.info(f"Confusion detected: {pattern}")
            return True
    
    return False


def detect_advanced_request(message: str) -> bool:
    """
    Detect if user wants more advanced/detailed explanation
    Returns True if advanced signals found
    """
    advanced_patterns = [
        r'\b(more|further) detail(s)?\b',
        r'\b(deeper|in depth)\b',
        r'\btechnical(ly)?\b',
        r'\badvanced (explanation|concept)\b',
        r'\bprofessional\b',
        r'\bscientific (terms|explanation)\b',
        r'\bprecise(ly)?\b',
        r'\bexact definition\b',
    ]
    
    message_lower = message.lower()
    
    for pattern in advanced_patterns:
        if re.search(pattern, message_lower):
            logger.info(f"Advanced request detected: {pattern}")
            return True
    
    return False


def infer_difficulty_from_history(user_questions: list) -> str:
    """
    Infer user's comprehension level from their question history
    Analyzes vocabulary complexity and question patterns
    """
    if not user_questions:
        return 'normal'
    
    # Simple heuristics
    recent_questions = user_questions[-5:]  # Last 5 questions
    
    simple_count = 0
    advanced_count = 0
    
    for q in recent_questions:
        if any(word in q.lower() for word in ['what', 'simple', 'easy', 'basic']):
            simple_count += 1
        if any(word in q.lower() for word in ['advanced', 'complex', 'detailed', 'technical']):
            advanced_count += 1
    
    if advanced_count > simple_count:
        return 'advanced'
    elif simple_count > advanced_count:
        return 'simple'
    else:
        return 'normal'


def determine_difficulty_level(current_message: str, chat_history: list = None) -> str:
    """
    Determine the appropriate difficulty level for the response
    Returns: 'simple', 'normal', or 'advanced'
    """
    # Check explicit confusion signals first
    if detect_confusion_signals(current_message):
        return 'simple'
    
    # Check for advanced request
    if detect_advanced_request(current_message):
        return 'advanced'
    
    # Infer from history if available
    if chat_history:
        inferred = infer_difficulty_from_history(chat_history)
        if inferred != 'normal':
            return inferred
    
    # Default to normal
    return 'normal'


def adjust_prompt_for_difficulty(base_prompt: str, difficulty: str, user_context: str = "") -> str:
    """
    Adjust the AI prompt based on difficulty level
    Adds instructions to simplify or elaborate
    """
    difficulty_instructions = {
        'simple': """
🎯 IMPORTANT: The user is confused or needs a simpler explanation.
- Use very simple language (like explaining to a 5th grader)
- Break down complex concepts into small, easy steps
- Use everyday examples and analogies
- Avoid technical jargon
- Use short sentences
- Add emoji to make it friendly 😊
- Explain one concept at a time
        """,
        
        'normal': """
📚 Provide a clear, balanced explanation suitable for NCERT students.
- Use grade-appropriate language
- Include relevant examples
- Balance detail with clarity
        """,
        
        'advanced': """
🎓 The user wants a detailed, advanced explanation.
- Use proper technical terminology
- Provide in-depth analysis
- Include scientific/mathematical precision
- Reference advanced concepts
- Assume higher comprehension level
        """
    }
    
    instruction = difficulty_instructions.get(difficulty, difficulty_instructions['normal'])
    
    adjusted_prompt = f"""{instruction}

{base_prompt}

{user_context if user_context else ""}
"""
    
    return adjusted_prompt


def format_response_by_difficulty(content: str, difficulty: str) -> str:
    """
    Post-process response to match difficulty level
    Adds helpful formatting based on complexity
    """
    if difficulty == 'simple':
        # Add step numbers if not present
        if 'step' not in content.lower():
            # Simple formatting
            formatted = f"Let me explain this simply:\n\n{content}\n\n💡 **Key Point:** Remember, take it one step at a time!"
        else:
            formatted = content + "\n\n😊 Does this make sense now?"
    
    elif difficulty == 'advanced':
        formatted = f"**Detailed Explanation:**\n\n{content}\n\n📖 **Further Reading:** Explore related advanced topics for deeper understanding."
    
    else:
        # Normal - no special formatting
        formatted = content
    
    return formatted


def generate_simplification_prompt(original_answer: str) -> str:
    """
    Generate a prompt to simplify an existing answer
    Used when user says "explain simpler"
    """
    prompt = f"""
The student didn't understand this explanation and asked for a simpler version:

Original Explanation:
{original_answer}

Please rewrite this in VERY SIMPLE language that a younger student can understand:
- Use short sentences
- Avoid difficult words
- Give easy examples
- Break it into small steps
- Use analogies with everyday things
"""
    return prompt


def extract_key_concepts(text: str) -> list:
    """
    Extract key concepts/terms from text for glossary
    """
    # Simple extraction based on capitalized words and common patterns
    concepts = []
    
    # Find capitalized phrases
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    concepts.extend(capitalized)
    
    # Find terms in quotes
    quoted = re.findall(r'"([^"]+)"', text)
    concepts.extend(quoted)
    
    # Remove duplicates and common words
    common_words = {'The', 'This', 'That', 'These', 'Those', 'A', 'An'}
    concepts = list(set([c for c in concepts if c not in common_words]))
    
    return concepts[:5]  # Return top 5
