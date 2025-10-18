from django.urls import path
from . import views
from . import quiz_views

urlpatterns = [
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path("chatbot/", views.chatbot_page, name="chatbot_page"),
    path("ask_chatbot/", views.ask_chatbot, name="ask_chatbot"),
    
    # Quiz URLs
    path("quiz/", quiz_views.quiz_dashboard, name="quiz_dashboard"),
    path("quiz/start/<str:chapter_id>/", quiz_views.start_quiz, name="start_quiz"),
    path("quiz/submit/<int:attempt_id>/", quiz_views.submit_quiz, name="submit_quiz"),
    path("quiz/results/<int:attempt_id>/", quiz_views.quiz_results, name="quiz_results"),
    path("quiz/history/", quiz_views.quiz_history, name="quiz_history"),
    path("quiz/analytics/<str:chapter_id>/", quiz_views.quiz_analytics, name="quiz_analytics"),
]
