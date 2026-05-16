from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .models import LearningSession, Topic, ReviewCard, ProgressSnapshot
from apps.scheduler.spaced_repetition import record_review, get_due_cards
from apps.accounts.utils import get_agent_user, ensure_learner_profile


# ─── Template views ──────────────────────────────────────────────────────────


def dashboard(request):
    user = get_agent_user(request)
    profile = ensure_learner_profile(user)
    recent_sessions = user.sessions.order_by("-started_at")[:5]
    due_cards_count = get_due_cards(user).count()
    snapshots = ProgressSnapshot.objects.filter(user=user).order_by("-date")[:30]
    active_goals = profile.goals.filter(status="active")

    return render(request, "dashboard/home.html", {
        "profile": profile,
        "recent_sessions": recent_sessions,
        "due_cards_count": due_cards_count,
        "snapshots": list(snapshots.values("date", "subject", "mastery_score")),
        "active_goals": active_goals,
    })



def chat_view(request, session_id):
    user = get_agent_user(request)
    session = get_object_or_404(LearningSession, pk=session_id, user=user)
    messages = session.messages.filter(role__in=["user", "assistant"])
    return render(request, "chat/chat.html", {
        "session": session,
        "messages": messages,
    })



def start_session(request):
    """Create a new session and redirect to the chat view."""
    user = get_agent_user(request)
    if request.method == "POST":
        topic_slug = request.POST.get("topic_slug")
        custom_topic = request.POST.get("custom_topic", "").strip()
        title = request.POST.get("title", f"Session {timezone.now():%b %d}")
        
        # Use selected topic or custom input
        topic = None
        if topic_slug:
            topic = get_object_or_404(Topic, slug=topic_slug)
        elif custom_topic:
            # For custom topics, update title to reflect the topic
            title = custom_topic
        
        session = LearningSession.objects.create(
            user=user,
            topic=topic,
            title=title,
        )
        return redirect("chat_view", session_id=str(session.id))
    topics = Topic.objects.all().order_by("subject", "difficulty_level")
    return render(request, "dashboard/start.html", {"topics": topics})



def review_view(request):
    """Spaced repetition review interface."""
    user = get_agent_user(request)
    cards = get_due_cards(user).select_related("topic")
    return render(request, "dashboard/review.html", {"cards": cards})


# ─── REST API views ───────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([AllowAny])
def api_start_session(request):
    user = get_agent_user(request)
    topic_slug = request.data.get("topic_slug")
    custom_topic = request.data.get("custom_topic", "").strip()
    title = request.data.get("title", "New Session")
    
    # Use selected topic or custom input
    topic = None
    if topic_slug:
        topic = get_object_or_404(Topic, slug=topic_slug)
    elif custom_topic:
        title = custom_topic
    
    session = LearningSession.objects.create(
        user=user,
        topic=topic,
        title=title,
    )
    return Response({"session_id": str(session.id), "ws_url": f"/ws/session/{session.id}/"})


@api_view(["POST"])
@permission_classes([AllowAny])
def api_review_card(request, card_id):
    """Submit a quality score (0–5) for a review card."""
    user = get_agent_user(request)
    card = get_object_or_404(ReviewCard, pk=card_id, user=user)
    quality = int(request.data.get("quality", 3))
    if not 0 <= quality <= 5:
        return Response({"error": "Quality must be 0–5"}, status=status.HTTP_400_BAD_REQUEST)
    record_review(card, quality)
    return Response({
        "card_id": str(card.id),
        "next_review": card.next_review.isoformat(),
        "new_interval": card.interval,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def api_progress(request):
    """Return mastery data for the progress chart."""
    user = get_agent_user(request)
    profile = ensure_learner_profile(user)
    snapshots = ProgressSnapshot.objects.filter(user=user).order_by("date", "subject")[:90]
    return Response({
        "mastery_map": profile.mastery_map,
        "struggle_areas": profile.struggle_areas,
        "streak_days": profile.streak_days,
        "total_sessions": profile.total_sessions,
        "snapshots": list(snapshots.values("date", "subject", "mastery_score")),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def api_due_cards(request):
    user = get_agent_user(request)
    cards = get_due_cards(user).values(
        "id", "question", "answer", "topic__name", "next_review", "repetitions"
    )
    return Response({"cards": list(cards)})
