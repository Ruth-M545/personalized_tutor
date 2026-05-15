"""
TutorOrchestrator — the central agent brain.

Responsibilities:
  - Build the right system prompt from learner context
  - Call the LLM (streaming or non-streaming)
  - Parse LLM output to detect intent tags
  - Delegate to FeedbackAnalyzer and PedagogyEngine as needed
  - Write results back to memory
"""

import json
import logging
from typing import AsyncGenerator
from django.conf import settings

from .memory import ShortTermMemory, LongTermMemory
from .prompts import SYSTEM_BASE, GAP_DETECTION_PROMPT, SESSION_SUMMARY_PROMPT
from .feedback import FeedbackAnalyzer
from .pedagogy import PedagogyEngine

logger = logging.getLogger(__name__)


def _get_llm_client():
    if settings.LLM_PROVIDER == "anthropic":
        import anthropic
        return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    else:
        import openai
        return openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class TutorOrchestrator:

    def __init__(self, user, session):
        self.user = user
        self.session = session
        self.short_mem = ShortTermMemory(str(session.id))
        self.long_mem = LongTermMemory(user)
        self.feedback = FeedbackAnalyzer(self.long_mem)
        self.pedagogy = PedagogyEngine(self.long_mem)

    def _build_system_prompt(self) -> str:
        topic_name = self.session.topic.name if self.session.topic else "General"
        goal = self.session.title or f"Learn about {topic_name}"
        return SYSTEM_BASE.format(
            learner_context=self.long_mem.build_context_summary(),
            topic=topic_name,
            session_goal=goal,
        )

    async def _call_llm_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream tokens from Anthropic or OpenAI."""
        client = _get_llm_client()

        if settings.LLM_PROVIDER == "anthropic":
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]
            async with client.messages.stream(
                model=settings.LLM_MODEL,
                max_tokens=1024,
                system=system,
                messages=user_msgs,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        else:
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                max_tokens=1024,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    async def _call_llm(self, messages: list[dict]) -> str:
        """Non-streaming LLM call for structured JSON responses."""
        client = _get_llm_client()
        if settings.LLM_PROVIDER == "anthropic":
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]
            resp = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=1024,
                system=system,
                messages=user_msgs,
            )
            return resp.content[0].text
        else:
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                max_tokens=1024,
            )
            return resp.choices[0].message.content

    async def chat(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Main entry point for a user message.
        Streams the assistant response token by token.
        Also runs feedback analysis after the stream completes.
        """
        # 1. Add user message to short-term memory
        self.short_mem.append("user", user_message)

        # 2. Build full message list
        system_prompt = self._build_system_prompt()
        context = self.short_mem.get_context()
        # Inject system as first message (Anthropic format)
        messages = [{"role": "system", "content": system_prompt}] + [
            m for m in context if m["role"] != "system"
        ]

        # 3. Stream response to client
        full_response = []
        async for token in self._call_llm_stream(messages):
            full_response.append(token)
            yield token

        assistant_text = "".join(full_response)

        # 4. Persist assistant response
        self.short_mem.append("assistant", assistant_text)

        # 5. Background: parse intent tag & run feedback if it was a quiz answer
        await self._post_process(user_message, assistant_text)

    async def _post_process(self, user_msg: str, assistant_msg: str):
        """
        Extract intent tag from assistant response and run gap detection
        if the previous turn was a quiz question.
        """
        try:
            tag = None
            for candidate in ["[EXPLAIN]", "[QUIZ]", "[FEEDBACK]", "[NEXT_TOPIC]"]:
                if candidate in assistant_msg:
                    tag = candidate
                    break

            if tag == "[FEEDBACK]":
                # The previous assistant turn was a quiz — analyse the user's answer
                await self.feedback.analyse(
                    user_response=user_msg,
                    session=self.session,
                )
        except Exception as e:
            logger.warning(f"Post-process error: {e}")

    async def end_session(self):
        """
        Generate a session summary and persist mastery updates.
        Called when the user closes the chat or navigates away.
        """
        context = self.short_mem.get_context()
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in context[-30:]
        )
        topic = self.session.topic.name if self.session.topic else "General"

        prompt = SESSION_SUMMARY_PROMPT.format(
            n=len(context),
            transcript=transcript,
            topic=topic,
        )
        messages = [{"role": "user", "content": prompt}]
        raw = await self._call_llm(messages)

        try:
            # Strip potential markdown fences
            clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(clean)
        except json.JSONDecodeError:
            logger.error(f"Session summary JSON parse failed: {raw[:200]}")
            return

        # Update mastery
        for topic_id, score in data.get("mastery_updates", {}).items():
            self.long_mem.update_mastery(topic_id, score)

        # Update struggles
        for s in data.get("struggle_areas_new", []):
            self.long_mem.add_struggle(s)
        for s in data.get("struggle_areas_resolved", []):
            self.long_mem.resolve_struggle(s)

        # Save session record
        self.long_mem.save_session_summary(
            session=self.session,
            score=data.get("session_score", 0.0),
            concepts=data.get("concepts_covered", []),
            gaps=data.get("gaps_detected", []),
            notes=data.get("agent_notes", ""),
        )

        # Create spaced repetition cards
        await self._create_review_cards(data.get("recommended_review_cards", []))

        # Clear session context from Redis
        self.short_mem.clear()

    async def _create_review_cards(self, cards: list[dict]):
        from apps.learning.models import ReviewCard
        from datetime import date
        if not self.session.topic:
            return
        for card in cards[:10]:  # cap at 10 per session
            await ReviewCard.objects.acreate(
                user=self.user,
                topic=self.session.topic,
                question=card.get("question", ""),
                answer=card.get("answer", ""),
                next_review=date.today(),
            )
