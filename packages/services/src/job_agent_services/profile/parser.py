"""Resume PDF parser - extracts structured data from user's resume."""

import logging
from pathlib import Path
from typing import Any

from job_agent_contracts.interfaces import LLMProvider

logger = logging.getLogger(__name__)


class ResumeParser:
    """Parses PDF/text resumes and extracts structured profile data."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def parse_file(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume not found: {file_path}")

        text = self._extract_text(path)
        if not text:
            raise ValueError(f"Could not extract text from: {file_path}")

        return await self._parse_with_llm(text)

    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf(path)
        elif suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8")
        else:
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return self._extract_pdf(path)

    def _extract_pdf(self, path: Path) -> str:
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(path))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        except ImportError:
            logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
            return ""
        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            return ""

    async def _parse_with_llm(self, resume_text: str) -> dict[str, Any]:
        prompt = f"""Extract structured information from this resume.
Return a JSON object with these fields:

{{
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "+1234567890",
    "location": "City, State/Country",
    "linkedin_url": "linkedin profile URL or empty string",
    "portfolio_url": "portfolio/website URL or empty string",
    "years_of_experience": number,
    "education": "Highest degree, University, Year",
    "summary": "2-3 sentence professional summary",
    "skills": ["skill1", "skill2", ...],
    "job_titles": ["Current/recent job titles"],
    "experience": [
        {{
            "title": "Job Title",
            "company": "Company Name",
            "duration": "Start - End",
            "highlights": ["achievement 1", "achievement 2"]
        }}
    ]
}}

Resume Text:
{resume_text[:5000]}"""

        return await self.llm.generate_json(prompt, system=(
            "You are an expert resume parser. Extract ALL information accurately. "
            "For skills, include both technical and soft skills. "
            "For years_of_experience, calculate from work history dates."
        ))
