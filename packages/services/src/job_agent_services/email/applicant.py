"""Email applicant service - sends job applications via email.

This is a HIGHER-LEVEL service that:
1. Composes a professional application email (subject + body)
2. Attaches resume PDF
3. Optionally attaches cover letter PDF
4. Sends via EmailSender interface
5. Tracks sent applications (Message-ID for bounce/read-receipt monitoring)

Separate from NotificationService — this sends TO employers, not TO you.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from job_agent_contracts.interfaces import EmailSender
from job_agent_contracts.errors import EmailError
from job_agent_services.resilience import RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class EmailApplicationResult:
    """Result of sending an application email."""
    success: bool
    message_id: str = ""
    to_email: str = ""
    subject: str = ""
    sent_at: datetime | None = None
    error: str = ""


class EmailApplicantService:
    """High-level service for sending job application emails.

    Features:
    - Rate limiting (configurable max emails per hour)
    - Professional email formatting
    - Resume + cover letter attachment
    - Tracking via Message-ID
    """

    def __init__(
        self,
        sender: EmailSender,
        max_per_hour: int = 10,
        signature_html: str = "",
    ):
        self._sender = sender
        self._rate_limiter = RateLimiter(requests_per_minute=max_per_hour // 60 or 1)
        self._signature_html = signature_html
        self._sent_history: list[EmailApplicationResult] = []

    async def send_application(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        resume_path: Path | str,
        cover_letter_path: Path | str | None = None,
    ) -> EmailApplicationResult:
        """Send a job application email with resume attached.

        Args:
            to_email: HR/recruiter email address
            subject: Professional subject line
            body_html: Email body (cover letter content)
            resume_path: Path to resume PDF
            cover_letter_path: Optional path to cover letter PDF

        Returns:
            EmailApplicationResult with success/failure info
        """
        # Rate limit
        await self._rate_limiter.acquire("email_applications")

        # Build attachments
        attachments: list[tuple[str, bytes]] = []

        resume_file = Path(resume_path)
        if not resume_file.exists():
            return EmailApplicationResult(
                success=False, to_email=to_email, subject=subject,
                error=f"Resume file not found: {resume_path}",
            )

        attachments.append((resume_file.name, resume_file.read_bytes()))

        if cover_letter_path:
            cl_file = Path(cover_letter_path)
            if cl_file.exists():
                attachments.append((cl_file.name, cl_file.read_bytes()))

        # Append signature if configured
        final_body = body_html
        if self._signature_html:
            final_body += f"\n<br/><br/>---<br/>{self._signature_html}"

        try:
            message_id = await self._sender.send(
                to=to_email,
                subject=subject,
                body_html=final_body,
                attachments=attachments,
            )

            result = EmailApplicationResult(
                success=True,
                message_id=message_id,
                to_email=to_email,
                subject=subject,
                sent_at=datetime.now(),
            )
            self._sent_history.append(result)
            logger.info("Application email sent to %s: %s", to_email, subject)
            return result

        except EmailError as e:
            result = EmailApplicationResult(
                success=False, to_email=to_email, subject=subject, error=str(e),
            )
            self._sent_history.append(result)
            logger.error("Failed to send application email to %s: %s", to_email, e)
            return result

    @property
    def sent_count_today(self) -> int:
        """Number of emails sent today."""
        today = datetime.now().date()
        return sum(
            1 for r in self._sent_history
            if r.sent_at and r.sent_at.date() == today and r.success
        )

    @property
    def history(self) -> list[EmailApplicationResult]:
        """Get sent email history."""
        return self._sent_history.copy()
