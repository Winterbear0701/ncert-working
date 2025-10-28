from django.urls import path
from . import views
from . import quiz_views

app_name = 'students'

urlpatterns = [
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path("chatbot/", views.chatbot_page, name="chatbot_page"),
    path("ask_chatbot/", views.ask_chatbot, name="ask_chatbot"),
    path("report-wrong-answer/", views.report_wrong_answer, name="report_wrong_answer"),  # NEW: Feedback endpoint
    
    # Smart Analysis
    path("smart-analysis/", views.smart_test_analysis, name="smart_test_analysis"),
    
    # Previous Year Papers Analysis
    path("papers/upload/", views.previous_papers_upload, name="previous_papers_upload"),
    path("papers/analyze/", views.analyze_papers, name="analyze_papers"),
    path("papers/results/<int:analysis_id>/", views.paper_analysis_results, name="paper_analysis_results"),
    
    # Quiz URLs
    path("quiz/", quiz_views.quiz_dashboard, name="quiz_dashboard"),
    path("quiz/start/<str:chapter_id>/", quiz_views.start_quiz, name="start_quiz"),
    path("quiz/submit/<int:attempt_id>/", quiz_views.submit_quiz, name="submit_quiz"),
    path("quiz/results/<int:attempt_id>/", quiz_views.quiz_results, name="quiz_results"),
    path("quiz/history/", quiz_views.quiz_history, name="quiz_history"),
    path("quiz/analytics/<str:chapter_id>/", quiz_views.quiz_analytics, name="quiz_analytics"),
    
    # Unit Test URLs
    path("unit-tests/", views.unit_test_list, name="unit_test_list"),
    path("unit-tests/<int:test_id>/start/", views.unit_test_start, name="unit_test_start"),
    path("unit-tests/take/<int:attempt_id>/", views.unit_test_take, name="unit_test_take"),
    path("unit-tests/submit/<int:attempt_id>/", views.unit_test_submit, name="unit_test_submit"),
    path("unit-tests/save-draft/<int:attempt_id>/", views.unit_test_save_draft, name="unit_test_save_draft"),
    path("unit-tests/results/<int:attempt_id>/", views.unit_test_results, name="unit_test_results"),
    path("unit-tests/analytics/<int:test_id>/", views.unit_test_analytics, name="unit_test_analytics"),
]
