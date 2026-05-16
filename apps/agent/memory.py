"""
Memory system for the personalized tutor agent.

Short-term  → Redis (current session context window)
Long-term   → PostgreSQL (LearnerProfile.mastery_map, struggle_areas, session analytics)
"""

import json
from datetime import datetime
from django.core.cache import cache
from django.conf import settings


class ShortTermMemory:
    """
    Manages the in-session conversation context stored in Redis.
    Implements a sliding window so the LLM never exceeds token limits.
    """

    TTL = 3600 * 4  # 4 hours

    def __init__(self, session_id: str):
        self.key = f"session_ctx:{session_id}"
        self.max_messages = settings.MAX_CONTEXT_MESSAGES

    def append(self, role: str, content: str):
        messages = self._load()
        messages.append({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
        # sliding window
        if len(messages) > self.max_messages:
            # keep system prompt (index 0) + last N-1 messages
            system = [m for m in messages if m["role"] == "system"]
            rest = [m for m in messages if m["role"] != "system"]
            messages = system + rest[-(self.max_messages - len(system)):]
        cache.set(self.key, json.dumps(messages), timeout=self.TTL)

    def get_context(self) -> list[dict]:
        """Return messages in Anthropic/OpenAI format (no 'ts' field)."""
        raw = self._load()
        return [{"role": m["role"], "content": m["content"]} for m in raw]

    def clear(self):
        cache.delete(self.key)

    def _load(self) -> list[dict]:
        raw = cache.get(self.key)
        return json.loads(raw) if raw else []


class LongTermMemory:
    """
    Reads and writes durable learner state from the database.
    All heavy DB I/O is isolated here so the orchestrator stays clean.
    """

    def __init__(self, user):
        self.user = user
        self._profile = None   # lazy-loaded

    @property
    def profile(self):
        if self._profile is None:
            from apps.accounts.models import LearnerProfile
            self._profile, _ = LearnerProfile.objects.get_or_create(user=self.user)
        return self._profile

    # ── Mastery ──────────────────────────────────────────────
    def get_mastery(self, topic_id: str) -> float:
        return self.profile.get_mastery(topic_id)

    def update_mastery(self, topic_id: str, score: float):
        self.profile.update_mastery(topic_id, score)

    def get_weak_topics(self, threshold=0.6) -> list[str]:
        return [t for t, m in self.profile.mastery_map.items() if m < threshold]

    def get_strong_topics(self, threshold=0.8) -> list[str]:
        return [t for t, m in self.profile.mastery_map.items() if m >= threshold]

    # ── Struggle areas ───────────────────────────────────────
    def add_struggle(self, concept: str):
        if concept not in self.profile.struggle_areas:
            self.profile.struggle_areas.append(concept)
            self.profile.save(update_fields=["struggle_areas", "updated_at"])

    def resolve_struggle(self, concept: str):
        if concept in self.profile.struggle_areas:
            self.profile.struggle_areas.remove(concept)
            self.profile.save(update_fields=["struggle_areas", "updated_at"])

    # ── Session summary ──────────────────────────────────────
    def save_session_summary(self, session, score: float, concepts: list, gaps: list, notes: str):
        from django.utils import timezone
        session.session_score = score
        session.concepts_covered = concepts
        session.gaps_detected = gaps
        session.agent_notes = notes
        session.ended_at = timezone.now()
        session.save()

        self.profile.total_sessions += 1
        self.profile.last_active = timezone.now()
        self.profile.save(update_fields=["total_sessions", "last_active", "updated_at"])

    # ── Learner context for system prompt ────────────────────
    def build_context_summary(self) -> str:
        p = self.profile
        weak = self.get_weak_topics()
        strong = self.get_strong_topics()
        goals = list(p.goals.filter(status="active").values_list("title", flat=True))
        return (
            f"Learner level: {p.preferred_difficulty}. "
            f"Pace: {p.preferred_pace}. "
            f"Current subject: {p.current_subject or 'not set'}. "
            f"Goals: {', '.join(goals) or 'none set'}. "
            f"Strong topics: {', '.join(strong[:5]) or 'none yet'}. "
            f"Weak topics: {', '.join(weak[:5]) or 'none yet'}. "
            f"Known struggles: {', '.join(p.struggle_areas[:5]) or 'none'}. "
            f"Sessions completed: {p.total_sessions}."
        )
