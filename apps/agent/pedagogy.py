"""
Pedagogy engine placeholder for adaptive tutoring strategies.
This module is intentionally lightweight for initial app startup.
"""

from typing import List


class PedagogyEngine:
    def __init__(self, long_memory):
        self.long_memory = long_memory

    def suggest_next_step(self, current_topic: str) -> str:
        """Return a short suggestion about what the learner should do next."""
        weak = self.long_memory.get_weak_topics()
        if weak:
            return f"Focus on {weak[0]} next."
        return f"Continue with {current_topic}."

    def summarize_progress(self, recent_messages: List[str]) -> str:
        return "The learner is progressing through the current topic." if recent_messages else "No progress yet."
