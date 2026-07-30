# Syllabus-to-Career Mapper

A FastAPI service that answers one question for a student: **"How well does my
course prepare me for the career I want?"**

It takes a syllabus and a target career, sends a structured prompt to the
OpenAI API, validates the AI's JSON response with
Pydantic, and returns a career map: matched skills (each backed by evidence
from the syllabus), skill gaps, project ideas, and a week-by-week learning
plan.

## Contents

```
app/
  main.py                 FastAPI app, routes, middleware, error handlers
  config.py                Environment-driven settings (pydantic-settings)
  models/
    request.py              Request schemas + input-quality validation
    response.py              Response schemas (career map, compare, errors)
  services/
    openai_client.py         Reusable async OpenAI HTTP client (timeouts, retries)
    prompts.py                Prompt construction for OpenAI
    career_mapper.py         Orchestration: prompt -> OpenAI -> validate -> respond
  core/
    exceptions.py            Custom exception types mapped to HTTP status codes
    logging.py                Structured JSON request logging
    rate_limit.py             In-memory per-client rate limiter
sample_syllabi/             Two sample syllabi + sample request/response JSON
requirements.txt
.env.example
Syllabus-to-Career-Mapper.postman_collection.json
```

## Setup

1. **Install dependencies** (Python 3.11+ recommended):
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and set at minimum:
   ```
   OPENAI_API_KEY=your_real_openai_api_key
   ```
   `OPENAI_BASE_URL` and `OPENAI_MODEL` default to OpenAI's API and
   `gpt-5-nano`, the lowest-cost GPT model.

3. **Run the server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

4. **Open the interactive docs**: http://localhost:8000/docs
   Swagger UI shows every request/response model, including error shapes.

## API Contract

### `GET /health`
Confirms the service is running. Never exposes secrets or internal state.

```json
{ "status": "ok", "app_name": "Syllabus-to-Career Mapper", "environment": "development" }
```

### `POST /career-map`
Creates a career map from one syllabus and one target career.

**Request fields**

| Field | Type | Constraints |
|---|---|---|
| `course_name` | string | 3–100 chars |
| `target_career` | string | 2–100 chars |
| `education_level` | enum | `school` \| `undergraduate` \| `postgraduate` \| `other` |
| `syllabus_text` | string | 200–20,000 chars; rejected if mostly links, mostly repeated words/lines, or too short on real vocabulary |
| `study_hours_per_week` | int | 1–40 |
| `plan_duration_weeks` | int | 2–12 |
| `known_skills` | string[] (optional) | max 20 items, no duplicates (case-insensitive) |

See `sample_syllabi/sample_request_career_map.json` for a full example, and
`sample_syllabi/sample_response_career_map.json` for the matching response.

**Response fields**: `analysis_id`, `course_summary`, `readiness_score` (+
explanation), `matched_skills` (each with syllabus evidence + career
relevance), `skill_gaps` (importance/priority/next step), 2–3
`project_recommendations`, a week-by-week `learning_plan`, `assumptions`,
`warnings`, `usage` (token counts), and `meta` (request ID + timing).

### `POST /career-map/compare`
Same syllabus, two target careers (`target_career_a`, `target_career_b`),
compared side by side. See `sample_syllabi/sample_request_compare.json`.
Returns `career_a` / `career_b` (each shaped like a single career map, minus
top-level usage/meta) plus a plain-language `recommendation`.

### Errors
Every error uses one envelope:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "One or more request fields are invalid.",
  "request_id": "...",
  "details": [{ "field": "syllabus_text", "message": "String should have at least 200 characters" }]
}
```

See `sample_syllabi/sample_response_error.json` for a full example.

| Status | error_code | When |
|---|---|---|
| 422 | `VALIDATION_ERROR` | Invalid/missing request fields, or a low-quality syllabus (too short, mostly links, repeated junk) |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds the size ceiling |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests from the same client in the current window |
| 502 | `PROVIDER_BAD_RESPONSE` | OpenAI's JSON failed validation twice (original + one corrective retry) |
| 502 | `PROVIDER_CONNECTION_ERROR` | Network-level failure reaching OpenAI |
| 504 | `PROVIDER_TIMEOUT` | OpenAI did not respond within the configured timeout |
| 500 | `INTERNAL_ERROR` | Unexpected server error (no stack trace is ever returned) |

## How OpenAI output is validated

1. Build a prompt that includes the syllabus, target career, and the exact
   JSON schema OpenAI must return.
2. Call OpenAI with `response_format: json_object`.
3. Parse the JSON and check it against the expected shape.
4. If parsing or validation fails, send **one** corrective prompt back to
   OpenAI with the original output and the validation error, asking it to fix
   just that.
5. If the second attempt also fails, return a `502 PROVIDER_BAD_RESPONSE`
   error. Raw model output is never returned to the client, valid or not —
   it always passes through the full Pydantic response model first.

## Logging & performance

- Every request gets a UUID `request_id` (returned in the `X-Request-ID`
  header and in every log line / error body).
- Logs are structured JSON: endpoint, status code, total time, OpenAI time,
  token usage. **Full syllabus text is never logged** by default
  (`LOG_FULL_SYLLABUS=false`).
- The OpenAI HTTP client is created once at app startup and reused across
  requests (connection pooling), not recreated per request.
- Timeouts return a clear `504` instead of hanging.

## Sample requests (curl)

```bash
# Health check
curl http://localhost:8000/health

# Career map
curl -X POST http://localhost:8000/career-map \
  -H "Content-Type: application/json" \
  --data @sample_syllabi/sample_request_career_map.json

# Compare two careers
curl -X POST http://localhost:8000/career-map/compare \
  -H "Content-Type: application/json" \
  --data @sample_syllabi/sample_request_compare.json
```

A ready-to-import Postman collection is also included:
`Syllabus-to-Career-Mapper.postman_collection.json` (set the `base_url`
collection variable if not running on `localhost:8000`).

## Sample syllabi

Two short, self-contained course syllabi are provided in `sample_syllabi/`
for demoing both endpoints:

- `web_development_101.txt` — a full-stack web dev course (paired with the
  `Backend Developer` career target in the sample requests).
- `data_analytics_foundations.txt` — a data analytics course (paired with the
  `Data Analyst` vs. `Data Engineer` comparison in the sample compare
  request).

## Out of scope (by design)

User accounts/login, a frontend, database storage, live job-market scraping,
resume scoring, and guaranteed placement/salary predictions are explicitly
out of scope per the product requirements.

## Notes on this implementation

- Rate limiting is an in-memory, per-process, per-client-IP sliding window —
  sufficient for a single instance. For multi-instance deployments, swap
  `app/core/rate_limit.py`'s `InMemoryRateLimiter` for a shared store (e.g.
  Redis) behind the same `check(client_key)` interface.
- Input-quality checks (`app/models/request.py`) reject syllabi that are
  mostly URLs, mostly one repeated word, or mostly one repeated line/sentence
  — these are cheap, deterministic checks that run *before* any OpenAI call,
  so obviously bad input never costs a token.
# AI-Career-Intelligence-Platform-using-LLMs-
