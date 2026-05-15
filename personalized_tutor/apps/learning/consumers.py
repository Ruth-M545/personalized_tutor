"""
Django Channels WebSocket consumer.
Handles real-time bidirectional communication for the chat interface.
Streams LLM tokens to the browser as they arrive.
"""

import json
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from apps.accounts.utils import get_guest_user

logger = logging.getLogger(__name__)


class TutorConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser):
            user = await database_sync_to_async(get_guest_user)()

        self.user = user
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group = f"tutor_{self.session_id}"

        # Load session and initialise orchestrator
        try:
            from apps.learning.models import LearningSession
            self.session = await LearningSession.objects.aget(
                pk=self.session_id, user=user
            )
        except LearningSession.DoesNotExist:
            await self.close(code=4004)
            return

        from apps.agent.orchestrator import TutorOrchestrator
        self.orchestrator = TutorOrchestrator(user, self.session)

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()
        logger.info(f"WS connected: user={user.email} session={self.session_id}")

    async def disconnect(self, close_code):
        if hasattr(self, "orchestrator"):
            # Trigger async session summary via Celery
            from apps.scheduler.tasks import end_session_cleanup
            end_session_cleanup.delay(str(self.session_id), self.user.pk)
        if hasattr(self, "room_group"):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
            return

        msg_type = data.get("type", "message")

        if msg_type == "message":
            user_text = data.get("content", "").strip()
            if not user_text:
                return

            # Persist user message to DB asynchronously
            await self._save_message("user", user_text)

            # Send typing indicator
            await self.send(text_data=json.dumps({"type": "typing_start"}))

            # Stream assistant response
            full_response = []
            async for token in self.orchestrator.chat(user_text):
                full_response.append(token)
                await self.send(text_data=json.dumps({
                    "type": "token",
                    "content": token,
                }))

            assistant_text = "".join(full_response)
            await self.send(text_data=json.dumps({"type": "message_complete"}))

            # Persist assistant message
            await self._save_message("assistant", assistant_text)

        elif msg_type == "end_session":
            await self.close()

    async def _save_message(self, role: str, content: str):
        from apps.learning.models import Message
        await Message.objects.acreate(
            session=self.session,
            role=role,
            content=content,
        )

    async def send_error(self, message: str):
        await self.send(text_data=json.dumps({
            "type": "error",
            "content": message,
        }))
