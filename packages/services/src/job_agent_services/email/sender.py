"""SMTP email sender - implements the EmailSender interface.

Supports:
- SMTP (any provider: Gmail, Outlook, custom)
- TLS/STARTTLS
- HTML + plain text multipart
- File attachments (resume, cover letter)
"""

import logging
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from pathlib import Path

import aiosmtplib

from job_agent_contracts.interfaces import EmailSender
from job_agent_contracts.errors import EmailError

logger = logging.getLogger(__name__)


class SMTPEmailSender(EmailSender):
    """SMTP-based email sender for job applications and notifications."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        from_email: str = "",
        display_name: str = "",
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email or username
        self.display_name = display_name
        self.use_tls = use_tls

    async def send(
        self,
        to: str,
        subject: str,
        body_html: str,
        attachments: list[tuple[str, bytes]] | None = None,
        reply_to: str = "",
    ) -> str:
        """Send an email and return the Message-ID.

        Args:
            to: Recipient email address
            subject: Email subject line
            body_html: HTML body content
            attachments: List of (filename, file_bytes) tuples
            reply_to: Reply-To header (defaults to from_email)

        Returns:
            Message-ID for tracking

        Raises:
            EmailError: If sending fails
        """
        msg_id = make_msgid(domain=self.from_email.split("@")[-1] if "@" in self.from_email else "local")

        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((self.display_name, self.from_email))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = msg_id
        msg["Reply-To"] = reply_to or self.from_email

        # HTML body
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        # Attachments
        if attachments:
            for filename, file_bytes in attachments:
                part = MIMEApplication(file_bytes, Name=filename)
                part["Content-Disposition"] = f'attachment; filename="{filename}"'
                msg.attach(part)

        try:
            kwargs = {
                "hostname": self.smtp_host,
                "port": self.smtp_port,
                "username": self.username,
                "password": self.password,
            }
            if self.use_tls:
                kwargs["start_tls"] = True

            await aiosmtplib.send(msg, **kwargs)
            logger.info("Email sent to %s (Message-ID: %s)", to, msg_id)
            return msg_id

        except aiosmtplib.SMTPException as e:
            raise EmailError(f"SMTP error sending to {to}: {e}", recoverable=True) from e
        except Exception as e:
            raise EmailError(f"Failed to send email to {to}: {e}") from e

    async def is_available(self) -> bool:
        """Check if SMTP server is reachable."""
        try:
            smtp = aiosmtplib.SMTP(hostname=self.smtp_host, port=self.smtp_port, timeout=10)
            await smtp.connect()
            await smtp.quit()
            return True
        except Exception:
            return False
