"""Orchestrates a career-map request: build prompt -> call OpenAI -> validate
JSON with Pydantic -> one corrective retry on failure -> assemble the final
response. Route handlers should only call into this module, never touch
OpenAIClient or prompts.py directly.
"""

import json
import time
import uuid
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import ProviderBadResponseError
from app.models.request import CareerMapCompareRequest, CareerMapRequest
from app.models.response import (
    CareerMapCompareResponse,
    CareerMapResponse,
    CareerMapSide,
    ResponseMeta,
    TokenUsage,
)
from app.services.openai_client import OpenAIClient
from app.services.prompts import (
    build_career_map_prompt,
    build_compare_prompt,
    build_correction_prompt,
)


def _strip_code_fences(text: str) -> str:
    """OpenAI is instructed not to use markdown fences, but models sometimes do
    anyway. Strip them defensively before attempting JSON parsing."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1] if stripped.count("```") >= 2 else stripped
        if stripped.startswith("json"):
            stripped = stripped[4:]
    return stripped.strip("` \n")


async def _get_validated_json(
    client: OpenAIClient, system_prompt: str, user_prompt: str, validate_fn
) -> tuple[dict[str, Any], int, int, str]:
    """Calls OpenAI, attempts to parse+validate JSON, and retries once with a
    correction prompt if validation fails. Raises ProviderBadResponseError if
    the second attempt also fails. Returns (validated_dict, input_tokens, output_tokens, model)."""

    result = await client.chat_completion_json(system_prompt, user_prompt)
    raw_text = result.content
    input_tokens = result.input_tokens
    output_tokens = result.output_tokens

    try:
        parsed = json.loads(_strip_code_fences(raw_text))
        validate_fn(parsed)
        return parsed, input_tokens, output_tokens, result.model
    except (json.JSONDecodeError, ValidationError) as first_error:
        correction_prompt = build_correction_prompt(raw_text, str(first_error))
        retry_result = await client.chat_completion_json(system_prompt, correction_prompt)
        input_tokens += retry_result.input_tokens
        output_tokens += retry_result.output_tokens

        try:
            parsed = json.loads(_strip_code_fences(retry_result.content))
            validate_fn(parsed)
            return parsed, input_tokens, output_tokens, retry_result.model
        except (json.JSONDecodeError, ValidationError) as second_error:
            raise ProviderBadResponseError(
                "The AI provider could not produce a valid, schema-compliant response."
            ) from second_error


def _validate_single_map_shape(parsed: dict) -> None:
    """Raises ValidationError-compatible errors if the shape doesn't match
    what CareerMapResponse expects, ignoring fields we compute ourselves
    (analysis_id, usage, meta)."""
    required = {
        "course_summary",
        "readiness_score",
        "readiness_explanation",
        "matched_skills",
        "skill_gaps",
        "project_recommendations",
        "learning_plan",
    }
    missing = required - parsed.keys()
    if missing:
        raise ValidationError.from_exception_data(
            "CareerMapResponse", [{"type": "missing", "loc": (f,), "input": None} for f in missing]
        )
    if not (2 <= len(parsed["project_recommendations"]) <= 3):
        raise ValueError("project_recommendations must contain 2 or 3 items")


def _validate_compare_shape(parsed: dict) -> None:
    required = {"course_summary", "career_a", "career_b", "recommendation"}
    missing = required - parsed.keys()
    if missing:
        raise ValidationError.from_exception_data(
            "CareerMapCompareResponse", [{"type": "missing", "loc": (f,), "input": None} for f in missing]
        )
    for side_key in ("career_a", "career_b"):
        side = parsed[side_key]
        for field in ("readiness_score", "matched_skills", "skill_gaps", "project_recommendations", "learning_plan"):
            if field not in side:
                raise ValueError(f"{side_key} is missing required field '{field}'")


async def create_career_map(client: OpenAIClient, req: CareerMapRequest, request_id: str) -> CareerMapResponse:
    start = time.perf_counter()
    system_prompt, user_prompt = build_career_map_prompt(req)

    parsed, input_tokens, output_tokens, model = await _get_validated_json(
        client, system_prompt, user_prompt, _validate_single_map_shape
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return CareerMapResponse(
        analysis_id=uuid.uuid4(),
        course_summary=parsed["course_summary"],
        readiness_score=parsed["readiness_score"],
        readiness_explanation=parsed["readiness_explanation"],
        matched_skills=parsed["matched_skills"],
        skill_gaps=parsed["skill_gaps"],
        project_recommendations=parsed["project_recommendations"],
        learning_plan=parsed["learning_plan"],
        assumptions=parsed.get("assumptions", []),
        warnings=parsed.get("warnings", []),
        usage=TokenUsage(
            provider_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        meta=ResponseMeta(request_id=request_id, processing_time_ms=elapsed_ms),
    )


async def create_career_map_comparison(
    client: OpenAIClient, req: CareerMapCompareRequest, request_id: str
) -> CareerMapCompareResponse:
    start = time.perf_counter()
    system_prompt, user_prompt = build_compare_prompt(req)

    parsed, input_tokens, output_tokens, model = await _get_validated_json(
        client, system_prompt, user_prompt, _validate_compare_shape
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    def _build_side(side_data: dict, career_name: str) -> CareerMapSide:
        return CareerMapSide(
            target_career=career_name,
            readiness_score=side_data["readiness_score"],
            readiness_explanation=side_data["readiness_explanation"],
            matched_skills=side_data["matched_skills"],
            skill_gaps=side_data["skill_gaps"],
            project_recommendations=side_data["project_recommendations"],
            learning_plan=side_data["learning_plan"],
            assumptions=side_data.get("assumptions", []),
            warnings=side_data.get("warnings", []),
        )

    return CareerMapCompareResponse(
        analysis_id=uuid.uuid4(),
        course_summary=parsed["course_summary"],
        career_a=_build_side(parsed["career_a"], req.target_career_a),
        career_b=_build_side(parsed["career_b"], req.target_career_b),
        recommendation=parsed["recommendation"],
        usage=TokenUsage(
            provider_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        meta=ResponseMeta(request_id=request_id, processing_time_ms=elapsed_ms),
    )
