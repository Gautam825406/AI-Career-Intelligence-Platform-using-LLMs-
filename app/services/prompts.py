"""Prompt construction for the career-mapping task.

Kept separate from orchestration logic so the prompt wording can be tuned
without touching retry/validation code, and so it's easy to unit test that
the prompt always includes the evidence-grounding rules.
"""

from app.models.request import CareerMapCompareRequest, CareerMapRequest

_SYSTEM_PROMPT = """You are an expert academic and career advisor. You analyze a course \
syllabus against a target career and produce a structured, evidence-based career map.

Rules you must always follow:
- Do not invent syllabus topics. Only reference topics that actually appear in the \
provided syllabus text.
- Do not claim that any course guarantees a job or outcome.
- Every matched skill must cite the exact syllabus wording or topic that supports it.
- Clearly separate facts from assumptions. If the syllabus is missing detail needed to \
answer confidently, note it in "assumptions" or "warnings" instead of guessing silently.
- Every project recommendation must produce something the student can show, test, or \
demonstrate (a repo, an app, a report, a dataset, etc.) -- not passive reading.
- Recommendations must fit the student's stated education level and available weekly \
study time.
- Use simple, plain language. Briefly explain any career-jargon term you use.
- Return ONLY a single JSON object. No markdown, no code fences, no commentary before \
or after the JSON.
"""

_SINGLE_MAP_SCHEMA_HINT = """Return a JSON object with exactly these top-level keys:
{
  "course_summary": string,
  "readiness_score": integer 0-100,
  "readiness_explanation": string,
  "matched_skills": [ { "skill": string, "syllabus_evidence": string, "career_relevance": string } ],
  "skill_gaps": [ { "skill": string, "importance": string, "priority": "high"|"medium"|"low", "next_step": string } ],
  "project_recommendations": [ { "title": string, "outcome": string, "mapped_skills": [string], "difficulty": "beginner"|"intermediate"|"advanced", "success_criteria": string } ],
  "learning_plan": [ { "week_number": integer, "focus": string, "tasks": [string], "estimated_hours": number } ],
  "assumptions": [string],
  "warnings": [string]
}
Provide 2 or 3 project_recommendations. Provide exactly plan_duration_weeks entries in learning_plan, \
one per week, numbered starting at 1, with total weekly hours not exceeding study_hours_per_week."""


def build_career_map_prompt(req: CareerMapRequest) -> tuple[str, str]:
    known_skills_line = (
        f"Skills the student already claims to know: {', '.join(req.known_skills)}."
        if req.known_skills
        else "The student did not list any known skills."
    )

    user_prompt = f"""Course name: {req.course_name}
Target career: {req.target_career}
Student education level: {req.education_level.value}
Available study time: {req.study_hours_per_week} hours/week
Learning plan length: {req.plan_duration_weeks} weeks
{known_skills_line}

Syllabus text:
\"\"\"
{req.syllabus_text}
\"\"\"

{_SINGLE_MAP_SCHEMA_HINT}"""

    return _SYSTEM_PROMPT, user_prompt


def build_correction_prompt(previous_output: str, validation_error: str) -> str:
    """Used when the first OpenAI response fails Pydantic validation. Asks OpenAI
    to fix its own output rather than starting over, to save tokens and stay
    grounded in the same syllabus evidence it already extracted."""

    return f"""Your previous JSON response failed schema validation with this error:
{validation_error}

Your previous response was:
{previous_output}

Return a corrected JSON object that fixes this error. Follow the exact schema and rules \
from the original instructions. Return ONLY the corrected JSON object, nothing else."""


_COMPARE_SCHEMA_HINT = """Return a JSON object with exactly these top-level keys:
{
  "course_summary": string,
  "career_a": { "readiness_score": integer 0-100, "readiness_explanation": string, "matched_skills": [...], "skill_gaps": [...], "project_recommendations": [...], "learning_plan": [...], "assumptions": [string], "warnings": [string] },
  "career_b": { same shape as career_a },
  "recommendation": string
}
Each of career_a / career_b must use the same matched_skills / skill_gaps / project_recommendations / \
learning_plan item shapes described for the single career-map task. Provide 2 or 3 \
project_recommendations per career and exactly plan_duration_weeks weekly entries in each learning_plan. \
"recommendation" should compare the two paths in plain language based only on syllabus evidence, without \
declaring one career objectively "better" as a life choice."""


def build_compare_prompt(req: CareerMapCompareRequest) -> tuple[str, str]:
    known_skills_line = (
        f"Skills the student already claims to know: {', '.join(req.known_skills)}."
        if req.known_skills
        else "The student did not list any known skills."
    )

    user_prompt = f"""Course name: {req.course_name}
Student education level: {req.education_level.value}
Available study time: {req.study_hours_per_week} hours/week
Learning plan length: {req.plan_duration_weeks} weeks
{known_skills_line}

Compare how well this syllabus supports two different target careers:
Career A: {req.target_career_a}
Career B: {req.target_career_b}

Syllabus text:
\"\"\"
{req.syllabus_text}
\"\"\"

{_COMPARE_SCHEMA_HINT}"""

    return _SYSTEM_PROMPT, user_prompt
