"""Skill definitions - declarative configs for all AI skills.

Each skill is a SkillConfig that defines WHAT the LLM should do.
The SkillExecutor handles HOW (agentic loop, retries, validation).
"""

from job_agent_contracts.skills import (
    LLM_ANALYTICAL,
    LLM_BALANCED,
    LLM_CREATIVE,
    LLM_PRECISE,
    SkillConfig,
    SkillPrefetch,
)


SKILL_MATCH_JOB = SkillConfig(
    name="match_job",
    description="Score a job listing against user profile",
    system_prompt=(
        "You are a job matching expert. Evaluate the candidate's fit for this role. "
        "Score each dimension from 0.0 to 1.0. Be realistic and critical. "
        "Consider skills overlap, experience level, location preferences, and salary expectations."
    ),
    user_prompt_template="match_job.j2",
    output_schema="MatchLLMResponse",
    llm_config=LLM_ANALYTICAL,
    prefetch=SkillPrefetch(
        rag_query_template="{{job.title}} {{job.company}} {{job.requirements[:5]|join(' ')}}"
    ),
    tags=["matching", "scoring"],
)

SKILL_FORM_MAPPING = SkillConfig(
    name="form_mapping",
    description="Map HTML form fields to user profile data",
    system_prompt=(
        "You are a form-filling assistant. Given an HTML form and user data, "
        "map each form field to the correct user data value. "
        "Return a JSON object with field_mappings: {selector: value}. "
        "Only map fields you are confident about. Never fabricate data."
    ),
    user_prompt_template="form_mapping.j2",
    output_schema="FormMappingResponse",
    llm_config=LLM_PRECISE,
    tags=["automation", "forms"],
)

SKILL_TAILOR_SUMMARY = SkillConfig(
    name="tailor_summary",
    description="Generate a tailored resume summary for a specific job",
    system_prompt=(
        "You are an expert resume writer. Write concise, impactful summaries "
        "that highlight the candidate's most relevant experience for this specific role. "
        "Keep it under 4 sentences."
    ),
    user_prompt_template="tailor_summary.j2",
    llm_config=LLM_BALANCED,
    prefetch=SkillPrefetch(
        rag_query_template="resume summary {{job.title}} {{job.company}}"
    ),
    tags=["resume", "writing"],
)

SKILL_COVER_LETTER = SkillConfig(
    name="cover_letter",
    description="Write a personalized cover letter",
    system_prompt=(
        "You are an expert cover letter writer. Write compelling, personalized letters "
        "that connect the candidate's experience to the role's requirements. "
        "Be specific about why this company and role is a good fit."
    ),
    user_prompt_template="cover_letter.j2",
    llm_config=LLM_CREATIVE,
    prefetch=SkillPrefetch(
        rag_query_template="cover letter {{job.title}} {{job.company}} {{matched_skills[:3]|join(' ')}}"
    ),
    tags=["resume", "writing", "creative"],
)

SKILL_CLASSIFY_JOB = SkillConfig(
    name="classify_job",
    description="Classify job type, seniority, and domain",
    system_prompt=(
        "You are a job classification expert. Analyze the job listing and determine: "
        "job_type (full-time/contract/part-time), seniority (junior/mid/senior/lead/principal), "
        "domain (backend/frontend/fullstack/data/devops/mobile/other), "
        "remote_type (remote/hybrid/onsite). Return JSON."
    ),
    user_prompt_template="classify_job.j2",
    llm_config=LLM_PRECISE,
    tags=["classification"],
)

SKILL_PLAN_APPLICATION = SkillConfig(
    name="plan_application",
    description="Decide execution strategy for a job application",
    system_prompt=(
        "You are an application strategy planner. Given a matched job and user profile, "
        "decide: should we apply directly, or is additional research needed? "
        "Consider: application complexity, required documents, custom questions. "
        "Return a plan with steps."
    ),
    user_prompt_template="plan_application.j2",
    llm_config=LLM_ANALYTICAL,
    tags=["planning", "strategy"],
)

# ─── NEW: Email Application Skills ──────────────────────────────────────────

SKILL_DETECT_APPLICATION_METHOD = SkillConfig(
    name="detect_application_method",
    description="Detect how to apply for a job (form, email, link-only)",
    system_prompt=(
        "You are an expert at analyzing job postings. Determine the best application method. "
        "Look for patterns like: 'send your CV to hr@company.com', 'apply via our portal', "
        "'email your resume to...', 'click Apply Now'. "
        "Return JSON with: method (form/email/link), contact_email (if found), "
        "instructions (any specific instructions), confidence (0.0-1.0)."
    ),
    user_prompt_template="detect_apply_method.j2",
    output_schema="ApplicationMethodDetection",
    llm_config=LLM_PRECISE,
    tags=["classification", "email"],
)

SKILL_COMPOSE_APPLICATION_EMAIL = SkillConfig(
    name="compose_application_email",
    description="Compose a professional job application email",
    system_prompt=(
        "You are an expert at writing professional job application emails for international roles. "
        "The email should be concise, professional, and tailored to the specific role. "
        "Include: greeting, brief intro (who you are), why you're applying (1-2 sentences), "
        "key qualifications (3-4 bullets), call to action, professional sign-off. "
        "Return JSON with: subject (professional subject line), body_html (HTML formatted email), "
        "body_plain (plain text version)."
    ),
    user_prompt_template="application_email.j2",
    output_schema="EmailComposition",
    llm_config=LLM_CREATIVE,
    prefetch=SkillPrefetch(
        rag_query_template="cover letter {{job.title}} {{job.company}}"
    ),
    tags=["email", "writing", "creative"],
)
