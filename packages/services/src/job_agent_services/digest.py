"""Email digest — sends periodic summaries of job activity.

Compiles daily/weekly reports of new matches, applications sent,
follow-up reminders, and outcome updates into a single email.

Usage:
    digest = DigestService(db=db, notifier=notifier)
    await digest.send_daily_digest()
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from job_agent_services.stores.sqlite import Database

logger = logging.getLogger(__name__)


class DigestService:
    """Compiles and sends email/notification digests of pipeline activity."""

    def __init__(self, db: Database, notifier: Any = None):
        self._db = db
        self._notifier = notifier

    async def compile_digest(self, hours: int = 24) -> dict[str, Any]:
        """Compile activity data for the given time period.

        Returns a structured dict suitable for rendering into email/notification.
        """
        stats = await self._db.get_stats()
        follow_ups = await self._db.get_due_follow_ups()
        analytics = await self._db.get_success_analytics()

        # Get recently discovered high-match jobs
        all_jobs = await self._db.get_all_jobs_detailed()
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_matches = [
            j for j in all_jobs
            if j.get("match_score", 0) >= 0.7
            and j.get("discovered_at")
            and datetime.fromisoformat(j["discovered_at"]) >= cutoff
        ]

        recent_applications = [
            j for j in all_jobs
            if j.get("applied_at")
            and datetime.fromisoformat(j["applied_at"]) >= cutoff
        ]

        return {
            "period_hours": hours,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "new_matches": len(recent_matches),
                "applications_sent": len(recent_applications),
                "follow_ups_due": len(follow_ups),
                "total_tracked": stats.get("total_discovered", 0),
            },
            "top_matches": sorted(
                recent_matches, key=lambda j: j.get("match_score", 0), reverse=True
            )[:5],
            "recent_applications": recent_applications[:5],
            "follow_ups": follow_ups[:10],
            "analytics_snapshot": {
                "overall_applied": analytics.get("total_applied", 0),
                "success_rate": analytics.get("overall_success_rate", 0),
            },
        }

    def format_text(self, digest: dict[str, Any]) -> str:
        """Format digest as plain text for notifications."""
        summary = digest["summary"]
        lines = [
            f"📊 Job Agent Digest ({digest['period_hours']}h)",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"🆕 New matches: {summary['new_matches']}",
            f"📨 Applications sent: {summary['applications_sent']}",
            f"⏰ Follow-ups due: {summary['follow_ups_due']}",
            "",
        ]

        if digest["top_matches"]:
            lines.append("🎯 Top Matches:")
            for job in digest["top_matches"][:3]:
                score = job.get("match_score", 0)
                lines.append(f"  • {job['title']} @ {job['company']} ({score:.0%})")
            lines.append("")

        if digest["follow_ups"]:
            lines.append("⏰ Follow Up:")
            for fu in digest["follow_ups"][:3]:
                lines.append(f"  • {fu['title']} @ {fu['company']}")

        return "\n".join(lines)

    async def send_daily_digest(self) -> bool:
        """Compile and send a 24-hour activity digest.

        Returns True if notification was sent successfully.
        """
        digest = await self.compile_digest(hours=24)

        # Skip if nothing happened
        if (digest["summary"]["new_matches"] == 0
                and digest["summary"]["applications_sent"] == 0
                and digest["summary"]["follow_ups_due"] == 0):
            logger.debug("Digest: no activity in last 24h, skipping")
            return False

        text = self.format_text(digest)

        if self._notifier and hasattr(self._notifier, "notify"):
            await self._notifier.notify(text)
            logger.info("Daily digest sent: %d matches, %d apps",
                        digest["summary"]["new_matches"],
                        digest["summary"]["applications_sent"])
            return True

        logger.warning("Digest compiled but no notifier configured")
        return False
