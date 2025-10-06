from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
   path("chatbot/", views.chatbot_page, name="chatbot_page"),
   path("ask_chatbot/", views.ask_chatbot, name="ask_chatbot"),
]
