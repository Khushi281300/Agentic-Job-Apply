"""Application Agent - routes applications via browser OR email.

For abroad jobs that expose an email address, sends a composed email
with resume attachment and tailored cover letter. Otherwise uses
browser automation for form filling.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from job_agent_agents.base import BaseAgent
from job_agent_agents.llm_utils import SafeLLMCaller
from job_agent_contracts.events import EventType
from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.models import (
    ApplicationConfig, ApplicationMethod, FormMappingResponse,
    JobListing, JobStatus, MatchResult, TailoredResume, UserProfile,
)
from job_agent_agents.prompts import render
from job_agent_services.stores.sqlite import Database
from job_agent_services.stores.rag import RAGService

logger = logging.getLogger(__name__)


class ApplicationAgent(BaseAgent):
    """Fills and submits job applications via browser or email."""

    def __init__(self, llm: LLMProvider, db: Database, rag: RAGService | None = None,
                 user_profile: UserProfile | None = None, app_config: ApplicationConfig | None = None,
                 resume_path: str = "", email_applicant=None):
        super().__init__("applicator", llm=llm, rag=rag)
        self.db = db
        self.user = user_profile or UserProfile()
        self._config = app_config or ApplicationConfig()
        self.resume_path = resume_path or self.user.resume_path
        self._email_applicant = email_applicant
        self._llm_caller = SafeLLMCaller(llm, self.logger)

    def _capabilities(self) -> list[str]:
        return ["form_filling", "browser_automation", "email_application", "application_submission"]

    def _skills(self) -> list[str]:
        return ["fill_application", "upload_resume", "submit_form", "send_email_application"]

    async def run(self, job: JobListing = None, match: MatchResult = None,
                  resume: TailoredResume = None, **kwargs: Any) -> bool:
        """Apply to a job listing - routes to email or browser based on method."""
        job = job or kwargs.get("job")
        match = match or kwargs.get("match")
        resume = resume or kwargs.get("resume")
        if not job:
            raise ValueError("Job listing required")

        self.logger.info("Applying to: %s at %s", job.title, job.company)
        await self.db.update_status(job.id, JobStatus.APPLYING)
        await self._emit(EventType.JOB_APPLYING, {"job_id": job.id})

        # Determine application method
        method = await self._detect_method(job)

        if method == ApplicationMethod.EMAIL and self._email_applicant:
            return await self._apply_via_email(job, match, resume)
        else:
            return await self._apply_via_browser(job, match, resume)

    async def _detect_method(self, job: JobListing) -> ApplicationMethod:
        """Detect the best application method for this job."""
        # If job already has a contact_email, prefer email
        if job.contact_email:
            return ApplicationMethod.EMAIL

        # Use LLM to detect from description
        if job.description:
            prompt = render("detect_apply_method.j2", job=job)
            try:
                result = await self.llm.generate_json(prompt, system=(
                    "You detect the application method from job postings. "
                    "Return JSON with 'method' (EMAIL/FORM/LINK_ONLY) and 'email' if found."
                ))
                method_str = result.get("method", "FORM").upper()
                if method_str == "EMAIL" and result.get("email"):
                    job.contact_email = result["email"]
                    return ApplicationMethod.EMAIL
            except Exception as e:
                self.logger.debug("Method detection failed, defaulting to FORM: %s", e)

        return ApplicationMethod.FORM

    # ─── Email Application Path ──────────────────────────────────────────────

    async def _apply_via_email(self, job: JobListing, match: MatchResult | None,
                               resume: TailoredResume | None) -> bool:
        """Send application via email with resume attachment."""
        if not self._email_applicant:
            self.logger.warning("Email applicant not configured, falling back to browser")
            return await self._apply_via_browser(job, match, resume)

        try:
            # Compose email subject and body using LLM
            cover_text = resume.cover_letter if resume else ""
            if not cover_text:
                cover_text = await self._generate_quick_cover(job)

            subject = f"Application: {job.title} - {self.user.name}"

            # Send via email applicant service
            result = await self._email_applicant.send_application(
                to_email=job.contact_email,
                subject=subject,
                body_html=cover_text,
                resume_path=self.resume_path,
            )

            if result.success:
                await self.db.update_status(job.id, JobStatus.APPLIED)
                await self._emit(EventType.JOB_EMAILED, {"job_id": job.id, "to": job.contact_email})

                if self.rag:
                    await self.rag.index_application(
                        job.id, job.company, "emailed",
                        f"Email application sent to {job.contact_email} for {job.title}",
                    )
                self.log_action("apply_email", input_data={"job_id": job.id}, output_data={"emailed": True})
                # Auto-schedule follow-up in 7 days
                await self.db.set_follow_up(job.id, datetime.now() + timedelta(days=7))
                return True
            else:
                await self.db.update_status(job.id, JobStatus.FAILED, error="Email send failed")
                return False

        except Exception as e:
            self.logger.error("Email application failed for %s: %s", job.id, e)
            await self.db.update_status(job.id, JobStatus.FAILED, error=str(e))
            await self._emit(EventType.JOB_FAILED, {"job_id": job.id, "error": str(e)})
            return False

    async def _generate_quick_cover(self, job: JobListing) -> str:
        """Generate a quick cover letter when none was pre-tailored."""
        prompt = render("application_email.j2",
                        user=self.user.model_dump(), job=job)
        return await self.llm.generate(
            prompt, system="Write a concise, professional application email body."
        )

    # ─── Browser Application Path ────────────────────────────────────────────

    async def _apply_via_browser(self, job: JobListing, match: MatchResult | None,
                                 resume: TailoredResume | None) -> bool:
        """Apply via browser automation (form filling)."""
        from job_agent_services.automation.browser import PlaywrightBrowser

        browser = PlaywrightBrowser(headless=self._config.headless)

        try:
            await browser.start()
            await browser.navigate(job.url)

            clicked = await browser.find_and_click(["Apply", "Easy Apply", "Apply Now"])
            if not clicked:
                self.logger.warning("No apply button found for: %s", job.url)
                await self.db.update_status(job.id, JobStatus.FAILED, error="No apply button")
                return False

            form_html = await browser.get_form_html()
            field_mapping = await self._map_form_fields(form_html, resume)
            await browser.fill_form(field_mapping)

            if self.resume_path:
                await browser.upload_file('input[type="file"]', self.resume_path)

            if self._config.auto_submit:
                submitted = await browser.find_and_click(["Submit", "Send Application", "Apply"])
                if submitted:
                    await self.db.update_status(job.id, JobStatus.APPLIED)
                    await self._emit(EventType.JOB_APPLIED, {"job_id": job.id})
                    if self.rag:
                        await self.rag.index_application(
                            job.id, job.company, "applied", f"Applied to {job.title}"
                        )
                    self.log_action("apply", input_data={"job_id": job.id}, output_data={"submitted": True})
                    await self.db.set_follow_up(job.id, datetime.now() + timedelta(days=7))
                    return True
            else:
                await browser.screenshot(f"data/screenshots/{job.id}.png")
                await self.db.update_status(job.id, JobStatus.APPLIED)
                self.log_action("apply", input_data={"job_id": job.id}, output_data={"screenshot": True})
                await self.db.set_follow_up(job.id, datetime.now() + timedelta(days=7))
                return True

            await self.db.update_status(job.id, JobStatus.FAILED, error="Submit button not found")
            return False

        except Exception as e:
            await self.db.update_status(job.id, JobStatus.FAILED, error=str(e))
            await self._emit(EventType.JOB_FAILED, {"job_id": job.id, "error": str(e)})
            self.log_action("apply", input_data={"job_id": job.id}, success=False, error=str(e))
            return False

        finally:
            await browser.stop()

    async def _map_form_fields(self, form_html: str, resume: TailoredResume | None) -> dict[str, str]:
        """Use LLM to map form fields to user data."""
        cover_excerpt = resume.cover_letter[:500] if resume else ""
        prompt = render("form_mapping.j2",
                        user=self.user.model_dump(),
                        form_html=form_html,
                        cover_letter_excerpt=cover_excerpt)

        # Try validated response first, fall back to raw JSON
        result = await self._llm_caller.validated(
            prompt, FormMappingResponse, context_label="form_mapping"
        )
        if result is not None:
            return result.field_mappings

        raw = await self._llm_caller.json(prompt, context_label="form_mapping_fallback")
        return {k: str(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
