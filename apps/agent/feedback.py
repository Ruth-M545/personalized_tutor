"""
FeedbackAnalyzer — analyses learner responses for understanding gaps
and updates the long-term memory accordingly.
"""

import json
import logging
from asgiref.sync import sync_to_async
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
        await sync_to_async(self.mem.update_mastery, thread_sensitive=True)(topic_id, score)

        if gap:
            await sync_to_async(self.mem.add_struggle, thread_sensitive=True)(gap)
        if misconception:
            await sync_to_async(self.mem.add_struggle, thread_sensitive=True)(misconception)

        logger.info(f"Feedback: score={score}, gap={gap}, action={data.get('next_action')}")
        return data

    async def _call_llm(self, prompt: str) -> str:
        provider = settings.LLM_PROVIDER.lower()
        try:
            return await self._call_llm_for_provider(provider, prompt)
        except Exception as exc:
            fallback = self._get_alternative_provider(provider)
            if fallback:
                logger.warning(
                    f"{provider} feedback call failed, falling back to {fallback}: {exc}"
                )
                return await self._call_llm_for_provider(fallback, prompt)
            raise

    def _get_alternative_provider(self, primary: str) -> str | None:
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

    async def _call_llm_for_provider(self, provider: str, prompt: str) -> str:
        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            resp = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        elif provider == "openai":
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            model = getattr(settings, 'OPENAI_MODEL', settings.LLM_MODEL)
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
            )
            return resp.choices[0].message.content
        elif provider == "xai":
            from xai_sdk import AsyncClient
            from xai_sdk.chat import user as xai_user, text as xai_text

            client = AsyncClient(api_key=settings.XAI_API_KEY)
            model = getattr(settings, 'XAI_MODEL', 'grok-3')
            xai_messages = [xai_user(xai_text(prompt))]
            chat = client.chat.create(
                model=model,
                messages=xai_messages,
                max_tokens=512,
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
            raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
