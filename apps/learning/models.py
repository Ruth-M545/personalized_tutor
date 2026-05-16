from django.db import models
from django.conf import settings
import uuid


class Topic(models.Model):
    """A node in the knowledge graph."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    subject = models.CharField(max_length=100)  # e.g. "Python", "Calculus"
    description = models.TextField(blank=True)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")
    difficulty_level = models.PositiveSmallIntegerField(default=1)   # 1–5
    estimated_minutes = models.PositiveIntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject} → {self.name}"


class LearningSession(models.Model):
    """One tutor conversation session."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Post-session analytics filled in by the agent
    session_score = models.FloatField(null=True, blank=True)   # 0.0–1.0
    concepts_covered = models.JSONField(default=list)
    gaps_detected = models.JSONField(default=list)
    agent_notes = models.TextField(blank=True)  # internal notes for next session

    def __str__(self):
        return f"{self.user.email} — {self.started_at:%Y-%m-%d %H:%M}"


class Message(models.Model):
    """Individual chat message within a session."""

    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant"), ("system", "System")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    # Agent metadata
    is_question = models.BooleanField(default=False)
    is_explanation = models.BooleanField(default=False)
    difficulty_tag = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}…"


class ReviewCard(models.Model):
    """Spaced-repetition flashcard — SM-2 algorithm."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_cards")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    # SM-2 fields
    easiness = models.FloatField(default=2.5)     # E-Factor, min 1.3
    interval = models.PositiveIntegerField(default=1)   # days
    repetitions = models.PositiveIntegerField(default=0)
    next_review = models.DateField()
    last_quality = models.PositiveSmallIntegerField(null=True, blank=True)  # 0-5
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_review"]

    def __str__(self):
        return f"Card: {self.question[:60]}"


class ProgressSnapshot(models.Model):
    """Daily snapshot of the learner's mastery for trend charts."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="snapshots")
    date = models.DateField()
    subject = models.CharField(max_length=100)
    mastery_score = models.FloatField()   # avg across topics in subject
    topics_practiced = models.PositiveIntegerField(default=0)
    questions_answered = models.PositiveIntegerField(default=0)
    correct_rate = models.FloatField(default=0.0)

    class Meta:
        unique_together = ("user", "date", "subject")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.email} — {self.date} — {self.subject}: {self.mastery_score:.0%}"
