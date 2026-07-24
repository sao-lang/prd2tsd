"""集成生态 — Webhook 通知。"""

from app.integrations.webhook import IntegrationHub, WebhookSender

__all__ = [
    "WebhookSender",
    "IntegrationHub",
]
