from django.urls import path
from . import views

urlpatterns = [
    # --- Existing URLs ---
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload_audio, name='upload_audio'),

    # --- ✅ NEW ANALYSIS URLs ---
    
    # Default analysis page (will show the summary)
    path('analysis/<int:audio_id>/', views.summary_view, name='summary_view'),
    
    # Transcription Page
    path('analysis/<int:audio_id>/transcription/', views.transcription_view, name='transcription_view'),
    
    # To-Do List Page
    path('analysis/<int:audio_id>/todos/', views.todo_view, name='todo_view'),
    
    # Deadlines Page
    path('analysis/<int:audio_id>/deadlines/', views.deadlines_view, name='deadlines_view'),
    
    # Email Page
    path('analysis/<int:audio_id>/email/', views.email_view, name='email_view'),

    # Email draft actions
    path('analysis/<int:audio_id>/email/save', views.save_email_draft, name='save_email_draft'),
    path('analysis/<int:audio_id>/email/send', views.send_email_draft, name='send_email_draft'),

    # NAYA: URL to handle marking a task as done
    path('toggle-todo/<int:todo_id>/', views.toggle_todo, name='toggle_todo'),

    # ADD THIS LINE: URL for adding to calendar
    path('add-to-calendar/<int:point_id>/', views.add_to_calendar, name='add_to_calendar'),
]