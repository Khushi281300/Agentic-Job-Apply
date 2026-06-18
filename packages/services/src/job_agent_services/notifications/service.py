"""Notification service - send alerts via Telegram, Slack, or Email.

Notifies YOU about pipeline events (new matches, applications sent, errors).
This is separate from EmailApplicantService which sends emails TO employers.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NotificationService:
    """Multi-channel notification dispatcher."""

    def __init__(
        self,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        slack_webhook_url: str = "",
        email_smtp_host: str = "",
        email_from: str = "",
        email_to: str = "",
        email_password: str = "",
    ):
        self._telegram_token = telegram_token
        self._telegram_chat_id = telegram_chat_id
        self._slack_webhook = slack_webhook_url
        self._email_smtp_host = email_smtp_host
        self._email_from = email_from
        self._email_to = email_to
        self._email_password = email_password

    @property
    def has_telegram(self) -> bool:
        return bool(self._telegram_token and self._telegram_chat_id)

    @property
    def has_slack(self) -> bool:
        return bool(self._slack_webhook)

    @property
    def has_email(self) -> bool:
        return bool(self._email_smtp_host and self._email_from and self._email_to)

    @property
    def is_configured(self) -> bool:
        return self.has_telegram or self.has_slack or self.has_email

    async def notify(self, title: str, message: str, level: str = "info") -> None:
        """Send notification to all configured channels."""
        emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "📢")
        formatted = f"{emoji} *{title}*\n{message}"

        if self.has_telegram:
            await self._send_telegram(formatted)
        if self.has_slack:
            await self._send_slack(title, message, level)
        if self.has_email:
            await self._send_email(title, message)

    async def notify_new_matches(self, count: int, top_jobs: list[dict]) -> None:
        """Notify about new job matches found."""
        job_lines = "\n".join(
            f"• {j.get('title', '?')} at {j.get('company', '?')} ({j.get('score', 0):.0%})"
            for j in top_jobs[:5]
        )
        await self.notify(
            f"{count} New Job Matches",
            f"Found {count} matching jobs:\n{job_lines}",
            level="success",
        )

    async def notify_application_sent(self, job_title: str, company: str, method: str) -> None:
        """Notify about a successful application."""
        await self.notify(
            "Application Sent",
            f"Applied to {job_title} at {company} via {method}",
            level="success",
        )

    async def notify_error(self, context: str, error: str) -> None:
        """Notify about a pipeline error."""
        await self.notify(
            f"Pipeline Error: {context}",
            f"```{error[:500]}```",
            level="error",
        )

    async def _send_telegram(self, text: str) -> None:
        """Send message via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self._telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
        except Exception as e:
            logger.error("Telegram notification failed: %s", e)

    async def _send_slack(self, title: str, message: str, level: str) -> None:
        """Send message via Slack Incoming Webhook."""
        color = {"info": "#36a64f", "success": "#2eb886", "warning": "#daa038", "error": "#a30200"}.get(level, "#439FE0")
        payload = {
            "attachments": [{
                "color": color,
                "title": title,
                "text": message,
                "ts": None,
            }]
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self._slack_webhook, json=payload)
        except Exception as e:
            logger.error("Slack notification failed: %s", e)

    async def _send_email(self, subject: str, body: str) -> None:
        """Send notification email via SMTP."""
        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body)
            msg["Subject"] = f"[Job Agent] {subject}"
            msg["From"] = self._email_from
            msg["To"] = self._email_to

            await aiosmtplib.send(
                msg,
                hostname=self._email_smtp_host,
                port=587,
                start_tls=True,
                username=self._email_from,
                password=self._email_password,
            )
        except Exception as e:
            logger.error("Email notification failed: %s", e)
