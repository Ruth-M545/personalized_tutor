"""
Celery background tasks for the personalized tutor.

Schedule via django-celery-beat in Django Admin → Periodic Tasks.
"""

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from datetime import date
import logging

logger = logging.getLogger(__name__)


@shared_task(name="scheduler.daily_review_reminder")
def daily_review_reminder():
    """
    Send daily review email to users who have cards due today.
    Run via celery-beat at their preferred review time.
    """
    from django.contrib.auth import get_user_model
    from apps.scheduler.spaced_repetition import get_due_cards

    User = get_user_model()
    users = User.objects.filter(
        profile__review_email_enabled=True,
        profile__last_active__isnull=False,
    ).select_related("profile")

    for user in users:
        due_cards = get_due_cards(user)
        count = due_cards.count()
        if count == 0:
            continue

        subject = f"📚 You have {count} review{'s' if count > 1 else ''} due today"
        body = (
            f"Hi {user.first_name or 'there'},\n\n"
            f"You have {count} spaced-repetition card{'s' if count > 1 else ''} to review today.\n\n"
            f"Topics: {', '.join(set(c.topic.name for c in due_cards[:5]))}\n\n"
            f"Log in to continue: http://localhost:8000/dashboard/review/\n\n"
            "— Your personal tutor"
        )
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
            logger.info(f"Review email sent to {user.email} ({count} cards)")
        except Exception as e:
            logger.error(f"Failed to send review email to {user.email}: {e}")


@shared_task(name="scheduler.take_progress_snapshot")
def take_progress_snapshot():
    """
    Nightly: snapshot each learner's mastery score per subject.
    Used for trend charts on the dashboard.
    """
    from django.contrib.auth import get_user_model
    from apps.accounts.models import LearnerProfile
    from apps.learning.models import ProgressSnapshot, LearningSession, Message

    today = date.today()
    User = get_user_model()

    for profile in LearnerProfile.objects.select_related("user").all():
        # Group mastery by subject (topic subject prefix in mastery_map keys)
        subject_scores: dict[str, list[float]] = {}
        for topic_slug, score in profile.mastery_map.items():
            subject = topic_slug.split("-")[0] if "-" in topic_slug else topic_slug
            subject_scores.setdefault(subject, []).append(score)

        for subject, scores in subject_scores.items():
            avg = sum(scores) / len(scores)
            ProgressSnapshot.objects.update_or_create(
                user=profile.user,
                date=today,
                subject=subject,
                defaults={"mastery_score": avg},
            )


@shared_task(name="scheduler.detect_dormant_learners")
def detect_dormant_learners():
    """
    Flag learners who haven't practiced in 3+ days
    and send a gentle nudge email.
    """
    from django.contrib.auth import get_user_model
    from datetime import timedelta

    User = get_user_model()
    cutoff = timezone.now() - timedelta(days=3)
    dormant = User.objects.filter(
        profile__last_active__lt=cutoff,
        profile__total_sessions__gt=0,
    ).select_related("profile")

    for user in dormant:
        days_away = (timezone.now() - user.profile.last_active).days
        subject = f"We miss you! {days_away} days without practice 📖"
        body = (
            f"Hi {user.first_name or 'there'},\n\n"
            f"It's been {days_away} days since your last session. "
            f"Even 10 minutes of review today will keep your streak alive.\n\n"
            f"Continue here: http://localhost:8000/dashboard/\n\n"
            "— Your personal tutor"
        )
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        except Exception as e:
            logger.error(f"Nudge email failed for {user.email}: {e}")


@shared_task(name="scheduler.end_session_cleanup", bind=True, max_retries=3)
def end_session_cleanup(self, session_id: str, user_id: int):
    """
    Called when a session ends (WebSocket disconnect or explicit end).
    Generates session summary asynchronously.
    """
    import asyncio
    from django.contrib.auth import get_user_model
    from apps.learning.models import LearningSession
    from apps.agent.orchestrator import TutorOrchestrator

    try:
        User = get_user_model()
        user = User.objects.get(pk=user_id)
        session = LearningSession.objects.get(pk=session_id)
        orchestrator = TutorOrchestrator(user, session)
        asyncio.run(orchestrator.end_session())
        logger.info(f"Session {session_id} summarised.")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
