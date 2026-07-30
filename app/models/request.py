"""Pydantic request models for the Syllabus-to-Career Mapper API."""

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EducationLevel(str, Enum):
    school = "school"
    undergraduate = "undergraduate"
    postgraduate = "postgraduate"
    other = "other"


# A syllabus that is "only links, repeated text, or meaningless characters"
# should be rejected. These heuristics catch the obvious cases cheaply,
# before we ever spend an OpenAI call on garbage input.
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")


def _looks_like_gibberish_or_links(text: str) -> Optional[str]:
    """Return a human-readable reason if the text fails a basic sanity check, else None."""
    stripped = text.strip()

    # Mostly URLs: if links make up more than half the character count, reject.
    url_chars = sum(len(m.group(0)) for m in _URL_PATTERN.finditer(stripped))
    if len(stripped) > 0 and url_chars / len(stripped) > 0.5:
        return "syllabus_text appears to be mostly links rather than course content"

    # Needs a reasonable number of real words, not just symbols/numbers.
    words = _WORD_PATTERN.findall(stripped)
    if len(words) < 20:
        return "syllabus_text does not contain enough real words to analyze"

    # Low vocabulary diversity: catches single-word or few-word spam repeated
    # many times (e.g. "asdf asdf asdf ..."), which passes the word-count check
    # above but has no real informational content.
    lowered_words = [w.lower() for w in words]
    unique_ratio = len(set(lowered_words)) / len(lowered_words)
    if len(lowered_words) >= 20 and unique_ratio < 0.15:
        return "syllabus_text appears to be repeated words rather than real course content"

    # Repeated text: if a single non-trivial line/sentence is repeated many times,
    # treat it as low-effort/junk input.
    lines = [ln.strip().lower() for ln in re.split(r"[\n.]", stripped) if len(ln.strip()) > 8]
    if lines:
        most_common_count = max(lines.count(ln) for ln in set(lines))
        if most_common_count >= 5 and most_common_count / len(lines) > 0.4:
            return "syllabus_text appears to be repeated text rather than real course content"

    return None


class CareerMapRequest(BaseModel):
    course_name: str = Field(..., min_length=3, max_length=100, description="Name of the course")
    target_career: str = Field(..., min_length=2, max_length=100, description="Career the student is targeting")
    education_level: EducationLevel = Field(..., description="Student's current education level")
    syllabus_text: str = Field(
        ...,
        min_length=200,
        max_length=20_000,
        description="Full syllabus text for the course",
    )
    study_hours_per_week: int = Field(..., ge=1, le=40, description="Hours per week the student can study")
    plan_duration_weeks: int = Field(..., ge=2, le=12, description="Length of the learning plan, in weeks")
    known_skills: Optional[list[str]] = Field(
        default=None, max_length=20, description="Skills the student already claims to have"
    )

    @field_validator("course_name", "target_career", "syllabus_text", mode="before")
    @classmethod
    def _trim_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v.strip())
        return v

    @field_validator("known_skills")
    @classmethod
    def _dedupe_known_skills(cls, v):
        if v is None:
            return v
        cleaned = [re.sub(r"\s+", " ", s.strip()) for s in v if s and s.strip()]
        lowered_seen = set()
        deduped = []
        for skill in cleaned:
            key = skill.lower()
            if key in lowered_seen:
                raise ValueError(f"duplicate skill found in known_skills: '{skill}'")
            lowered_seen.add(key)
            deduped.append(skill)
        return deduped

    @model_validator(mode="after")
    def _validate_syllabus_quality(self):
        reason = _looks_like_gibberish_or_links(self.syllabus_text)
        if reason:
            raise ValueError(reason)
        return self


class CareerMapCompareRequest(BaseModel):
    """Same syllabus, two target careers, compared side by side."""

    course_name: str = Field(..., min_length=3, max_length=100)
    syllabus_text: str = Field(..., min_length=200, max_length=20_000)
    education_level: EducationLevel
    study_hours_per_week: int = Field(..., ge=1, le=40)
    plan_duration_weeks: int = Field(..., ge=2, le=12)
    target_career_a: str = Field(..., min_length=2, max_length=100)
    target_career_b: str = Field(..., min_length=2, max_length=100)
    known_skills: Optional[list[str]] = Field(default=None, max_length=20)

    @field_validator("course_name", "syllabus_text", "target_career_a", "target_career_b", mode="before")
    @classmethod
    def _trim_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v.strip())
        return v

    @model_validator(mode="after")
    def _validate(self):
        reason = _looks_like_gibberish_or_links(self.syllabus_text)
        if reason:
            raise ValueError(reason)
        if self.target_career_a.strip().lower() == self.target_career_b.strip().lower():
            raise ValueError("target_career_a and target_career_b must be different careers")
        return self
