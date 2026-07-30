"""Pydantic response models. These are the exact schema OpenAI's JSON must satisfy
(after we parse it) and the exact schema returned to the client."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MatchedSkill(BaseModel):
    skill: str = Field(..., description="The career-relevant skill identified")
    syllabus_evidence: str = Field(..., description="Exact topic/wording from the syllabus supporting this match")
    career_relevance: str = Field(..., description="Why this skill matters for the target career")


class SkillGap(BaseModel):
    skill: str = Field(..., description="The missing or under-developed skill")
    importance: str = Field(..., description="Why this skill matters for the target career")
    priority: str = Field(..., description="e.g. high, medium, low")
    next_step: str = Field(..., description="A single, beginner-friendly next action")


class ProjectRecommendation(BaseModel):
    title: str
    outcome: str = Field(..., description="What the student will be able to show/prove after finishing")
    mapped_skills: list[str] = Field(..., description="Skills this project demonstrates or builds")
    difficulty: str = Field(..., description="e.g. beginner, intermediate, advanced")
    success_criteria: str = Field(..., description="How the student knows the project is complete")


class LearningWeek(BaseModel):
    week_number: int = Field(..., ge=1)
    focus: str = Field(..., description="Main theme for the week")
    tasks: list[str] = Field(..., description="Concrete tasks for the week")
    estimated_hours: float = Field(..., ge=0)


class TokenUsage(BaseModel):
    provider_model: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)


class ResponseMeta(BaseModel):
    request_id: str
    processing_time_ms: float = Field(..., ge=0)


class CareerMapResponse(BaseModel):
    analysis_id: UUID
    course_summary: str = Field(..., description="Short description based only on the submitted syllabus")
    readiness_score: int = Field(..., ge=0, le=100)
    readiness_explanation: str = Field(..., description="Plain-language explanation of the readiness score")
    matched_skills: list[MatchedSkill]
    skill_gaps: list[SkillGap]
    project_recommendations: list[ProjectRecommendation] = Field(..., min_length=2, max_length=3)
    learning_plan: list[LearningWeek]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: TokenUsage
    meta: ResponseMeta


class CareerMapSide(BaseModel):
    """One side of a two-career comparison — same shape as the core map, minus usage/meta."""

    target_career: str
    readiness_score: int = Field(..., ge=0, le=100)
    readiness_explanation: str
    matched_skills: list[MatchedSkill]
    skill_gaps: list[SkillGap]
    project_recommendations: list[ProjectRecommendation] = Field(..., min_length=2, max_length=3)
    learning_plan: list[LearningWeek]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CareerMapCompareResponse(BaseModel):
    analysis_id: UUID
    course_summary: str
    career_a: CareerMapSide
    career_b: CareerMapSide
    recommendation: str = Field(..., description="Plain-language guidance on which path the syllabus supports better")
    usage: TokenUsage
    meta: ResponseMeta


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    error_code: str = Field(..., description="Machine-readable error identifier, e.g. 'VALIDATION_ERROR'")
    message: str = Field(..., description="Safe, human-readable message. Never a raw stack trace.")
    request_id: str
    details: Optional[list[ErrorDetail]] = None
