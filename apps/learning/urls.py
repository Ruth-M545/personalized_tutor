from django.urls import path
from . import views

urlpatterns = [
    # Template views
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/start/", views.start_session, name="start_session"),
    path("dashboard/review/", views.review_view, name="review_view"),
    path("chat/<uuid:session_id>/", views.chat_view, name="chat_view"),
    # REST API
    path("api/sessions/start/", views.api_start_session),
    path("api/sessions/review/<uuid:card_id>/", views.api_review_card),
    path("api/progress/", views.api_progress),
    path("api/cards/due/", views.api_due_cards),
]
