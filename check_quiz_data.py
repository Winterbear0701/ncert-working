import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
django.setup()

from students.models import QuizChapter, QuizQuestion

# Check the math Chapter 1
chapter = QuizChapter.objects.filter(
    class_number='Class 5',
    subject='Mathematics',
    chapter_order=1
).first()

if chapter:
    print("="*70)
    print(f'Chapter: {chapter.chapter_name}')
    print(f'ID: {chapter.chapter_id}')
    print(f'Subject: {chapter.subject}')
    print(f'Questions: {chapter.total_questions}')
    print()
    
    # Get questions
    questions = QuizQuestion.objects.filter(chapter=chapter)[:3]
    print(f'Sample Questions:')
    for i, q in enumerate(questions, 1):
        variant = q.variants.first()
        print(f'\n{i}. {q.topic} ({q.difficulty})')
        if variant:
            print(f'   Q: {variant.question_text[:120]}')
        print(f'   RAG: {q.rag_context[:150]}')
