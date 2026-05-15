"""
FeedbackAnalyzer — analyses learner responses for understanding gaps
and updates the long-term memory accordingly.
"""

import json
import logging
from django.conf import settings
from .prompts import GAP_DETECTION_PROMPT

logger = logging.getLogger(__name__)


class FeedbackAnalyzer:

    def __init__(self, long_memory):
        self.mem = long_memory

    async def analyse(self, user_response: str, session) -> dict:
        """
        Run gap detection via LLM. Returns structured analysis dict.
        Updates mastery and struggle areas in long-term memory.
        """
        topic_id = session.topic.slug if session.topic else "general"
        concept = session.topic.name if session.topic else "current concept"
        # correct answer would come from the quiz state; simplified here
        correct_answer = "(see session context)"

        prompt = GAP_DETECTION_PROMPT.format(
            concept=concept,
            correct_answer=correct_answer,
            learner_response=user_response,
        )

        raw = await self._call_llm(prompt)
        try:
            clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning(f"Gap detection JSON failed: {raw[:200]}")
            return {}

        score = data.get("score", 0.5)
        gap = data.get("gap_identified")
        misconception = data.get("misconception")

        # Update mastery with this data point
        self.mem.update_mastery(topic_id, score)

        if gap:
            self.mem.add_struggle(gap)
        if misconception:
            self.mem.add_struggle(misconception)

        logger.info(f"Feedback: score={score}, gap={gap}, action={data.get('next_action')}")
        return data

    async def _call_llm(self, prompt: str) -> str:
        if settings.LLM_PROVIDER == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            resp = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        else:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
            )
            return resp.choices[0].message.content
