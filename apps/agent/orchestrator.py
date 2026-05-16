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
from asgiref.sync import sync_to_async
from django.conf import settings

from .memory import ShortTermMemory, LongTermMemory
from .prompts import SYSTEM_BASE, GAP_DETECTION_PROMPT, SESSION_SUMMARY_PROMPT
from .feedback import FeedbackAnalyzer
from .pedagogy import PedagogyEngine

logger = logging.getLogger(__name__)


def _get_llm_client(provider: str | None = None):
    provider = (provider or settings.LLM_PROVIDER).lower()
    if provider == "anthropic":
        import anthropic
        return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    elif provider == "openai":
        import openai
        return openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    elif provider == "xai":
        from xai_sdk import AsyncClient
        return AsyncClient(api_key=settings.XAI_API_KEY)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def _get_alternative_provider(primary: str) -> str | None:
    primary = primary.lower()
    if primary == "xai":
        if settings.OPENAI_API_KEY:
            return "openai"
        if settings.ANTHROPIC_API_KEY:
            return "anthropic"
    elif primary == "openai":
        if settings.XAI_API_KEY:
            return "xai"
        if settings.ANTHROPIC_API_KEY:
            return "anthropic"
    elif primary == "anthropic":
        if settings.OPENAI_API_KEY:
            return "openai"
        if settings.XAI_API_KEY:
            return "xai"
    return None


class TutorOrchestrator:

    def __init__(self, user, session):
        self.user = user
        self.session = session
        self.short_mem = ShortTermMemory(str(session.id))
        self.long_mem = LongTermMemory(user)
        self.feedback = FeedbackAnalyzer(self.long_mem)
        self.pedagogy = PedagogyEngine(self.long_mem)

    async def _build_system_prompt(self) -> str:
        topic_name = self.session.topic.name if self.session.topic else "General"
        goal = self.session.title or f"Learn about {topic_name}"
        learner_context = await sync_to_async(
            self.long_mem.build_context_summary,
            thread_sensitive=True,
        )()
        return SYSTEM_BASE.format(
            learner_context=learner_context,
            topic=topic_name,
            session_goal=goal,
        )

    async def _call_llm_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream tokens from the configured provider, with fallback support."""
        provider = settings.LLM_PROVIDER.lower()
        try:
            async for token in self._call_llm_stream_for_provider(provider, messages):
                yield token
        except Exception as exc:
            fallback = _get_alternative_provider(provider)
            if fallback:
                logger.warning(
                    f"{provider} stream failed, falling back to {fallback}: {exc}"
                )
                async for token in self._call_llm_stream_for_provider(fallback, messages):
                    yield token
            else:
                raise

    async def _call_llm_stream_for_provider(self, provider: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        client = _get_llm_client(provider)

        if provider == "anthropic":
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
        elif provider == "openai":
            model = getattr(settings, 'OPENAI_MODEL', settings.LLM_MODEL)
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        elif provider == "xai":
            from xai_sdk.chat import system as xai_system, user as xai_user, text as xai_text

            xai_messages = []
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    xai_messages.append(xai_system(xai_text(content)))
                elif role == "user":
                    xai_messages.append(xai_user(xai_text(content)))
                elif role == "assistant":
                    pass

            model = getattr(settings, 'XAI_MODEL', 'grok-3')
            chat = client.chat.create(
                model=model,
                messages=xai_messages,
                max_tokens=1024,
            )

            async for response, chunk in chat.stream():
                if hasattr(chunk, 'content'):
                    chunk_content = chunk.content
                    if isinstance(chunk_content, str):
                        yield chunk_content
                    elif hasattr(chunk_content, 'text') and chunk_content.text:
                        yield chunk_content.text
                    elif isinstance(chunk_content, (list, tuple)) and len(chunk_content) > 0:
                        for item in chunk_content:
                            if isinstance(item, str):
                                yield item
                            elif hasattr(item, 'text') and item.text:
                                yield item.text
        else:
            raise ValueError(f"Unknown provider for streaming: {provider}")

    async def _call_llm(self, messages: list[dict]) -> str:
        """Non-streaming LLM call for structured JSON responses."""
        provider = settings.LLM_PROVIDER.lower()
        try:
            return await self._call_llm_for_provider(provider, messages)
        except Exception as exc:
            fallback = _get_alternative_provider(provider)
            if fallback:
                logger.warning(
                    f"{provider} non-stream call failed, falling back to {fallback}: {exc}"
                )
                return await self._call_llm_for_provider(fallback, messages)
            raise

    async def _call_llm_for_provider(self, provider: str, messages: list[dict]) -> str:
        client = _get_llm_client(provider)
        if provider == "anthropic":
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]
            resp = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=1024,
                system=system,
                messages=user_msgs,
            )
            return resp.content[0].text
        elif provider == "openai":
            model = getattr(settings, 'OPENAI_MODEL', settings.LLM_MODEL)
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
            )
            return resp.choices[0].message.content
        elif provider == "xai":
            from xai_sdk.chat import system as xai_system, user as xai_user, text as xai_text

            xai_messages = []
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    xai_messages.append(xai_system(xai_text(content)))
                elif role == "user":
                    xai_messages.append(xai_user(xai_text(content)))
                elif role == "assistant":
                    pass

            model = getattr(settings, 'XAI_MODEL', 'grok-3')
            chat = client.chat.create(
                model=model,
                messages=xai_messages,
                max_tokens=1024,
            )
            response = await chat.sample()
            if hasattr(response, 'content') and response.content:
                resp_content = response.content
                if isinstance(resp_content, str):
                    return resp_content
                elif hasattr(resp_content, 'text') and resp_content.text:
                    return resp_content.text
                elif isinstance(resp_content, (list, tuple)) and len(resp_content) > 0:
                    for item in resp_content:
                        if isinstance(item, str):
                            return item
                        elif hasattr(item, 'text') and item.text:
                            return item.text
            return ""
        else:
            raise ValueError(f"Unknown provider for non-stream call: {provider}")

    async def chat(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Main entry point for a user message.
        Streams the assistant response token by token.
        Also runs feedback analysis after the stream completes.
        """
        # 1. Add user message to short-term memory
        await sync_to_async(self.short_mem.append, thread_sensitive=True)("user", user_message)

        # 2. Build full message list
        system_prompt = await self._build_system_prompt()
        context = await sync_to_async(self.short_mem.get_context, thread_sensitive=True)()
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
        await sync_to_async(self.short_mem.append, thread_sensitive=True)("assistant", assistant_text)

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
        context = await sync_to_async(self.short_mem.get_context, thread_sensitive=True)()
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
            await sync_to_async(self.long_mem.update_mastery, thread_sensitive=True)(topic_id, score)

        # Update struggles
        for s in data.get("struggle_areas_new", []):
            await sync_to_async(self.long_mem.add_struggle, thread_sensitive=True)(s)
        for s in data.get("struggle_areas_resolved", []):
            await sync_to_async(self.long_mem.resolve_struggle, thread_sensitive=True)(s)

        # Save session record
        await sync_to_async(self.long_mem.save_session_summary, thread_sensitive=True)(
            session=self.session,
            score=data.get("session_score", 0.0),
            concepts=data.get("concepts_covered", []),
            gaps=data.get("gaps_detected", []),
            notes=data.get("agent_notes", ""),
        )

        # Create spaced repetition cards
        await self._create_review_cards(data.get("recommended_review_cards", []))

        # Clear session context from Redis
        await sync_to_async(self.short_mem.clear, thread_sensitive=True)()

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
