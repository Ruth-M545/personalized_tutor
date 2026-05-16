from django.contrib.auth.models import AbstractUser
from django.db import models
import json


class User(AbstractUser):
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class LearnerProfile(models.Model):
    """Extended profile holding all personalisation data."""

    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    PACE_CHOICES = [
        ("slow", "Slow & Thorough"),
        ("normal", "Normal"),
        ("fast", "Fast-Paced"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    # Preferences
    preferred_difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="beginner")
    preferred_pace = models.CharField(max_length=10, choices=PACE_CHOICES, default="normal")
    subjects_of_interest = models.JSONField(default=list)
    learning_goals = models.TextField(blank=True)
    # Adaptive state — updated by the agent after every session
    current_subject = models.CharField(max_length=200, blank=True)
    mastery_map = models.JSONField(default=dict)   # {topic_id: 0.0..1.0}
    struggle_areas = models.JSONField(default=list)
    streak_days = models.PositiveIntegerField(default=0)
    total_sessions = models.PositiveIntegerField(default=0)
    last_active = models.DateTimeField(null=True, blank=True)
    # Spaced repetition metadata
    daily_review_time = models.TimeField(null=True, blank=True)
    review_email_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_mastery(self, topic_id: str) -> float:
        return self.mastery_map.get(topic_id, 0.0)

    def update_mastery(self, topic_id: str, score: float):
        """Exponential moving average: new = 0.7*old + 0.3*score."""
        old = self.mastery_map.get(topic_id, 0.0)
        self.mastery_map[topic_id] = round(0.7 * old + 0.3 * score, 3)
        self.save(update_fields=["mastery_map", "updated_at"])

    def __str__(self):
        return f"{self.user.email} — profile"


class LearningGoal(models.Model):
    """A specific, measurable goal the learner sets."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("achieved", "Achieved"),
        ("paused", "Paused"),
    ]

    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    progress_percent = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.status})"
