# Syllabus-to-Career Mapper — Project Documentation

## 1. Project overview

Syllabus-to-Career Mapper is a ChatGPT-powered REST API that evaluates how well an academic course prepares a student for a target career. A client submits the course syllabus, the desired career, the student's education level, available study time, and optional existing skills. The application sends this context to OpenAI's `gpt-5-nano` model, validates the generated JSON, and returns an evidence-based career-readiness report.

In this document, “ChatGPT-powered” describes the user-facing AI capability. The application integrates through the **OpenAI API**, not through the ChatGPT website or a ChatGPT user subscription. It therefore requires a separate OpenAI Platform API key and API billing.

The report includes:

- A summary of the submitted course
- A career-readiness score from 0 to 100
- Skills supported by evidence from the syllabus
- Important skills that appear to be missing
- Two or three portfolio project recommendations
- A week-by-week learning plan
- Explicit assumptions and warnings
- LLM token usage and request-processing metadata

The application also supports comparing the same syllabus against two different careers.

This project is an API-only backend. It does not currently include a browser frontend, user accounts, persistent storage, or live labor-market data.

## 2. Goals and design principles

The application is designed around the following principles:

1. **Evidence-grounded analysis**  
   A matched skill must be supported by a topic or phrase found in the submitted syllabus. The prompt explicitly tells the model not to invent course content.

2. **Structured output**  
   The ChatGPT model is instructed through the OpenAI API to return a single JSON object. The service then parses and validates that output before returning it to the client.

3. **Actionable recommendations**  
   Project suggestions must produce demonstrable artifacts, and learning plans must contain concrete weekly tasks.

4. **Transparent uncertainty**  
   Missing information should be identified in `assumptions` or `warnings` instead of being silently guessed.

5. **Safe API behavior**  
   Validation errors, provider failures, timeouts, payload limits, and rate limits use a consistent error envelope. Stack traces and secrets are not returned to clients.

6. **Reusable external connections**  
   A single asynchronous HTTP client is created during application startup and reused across requests.

## 3. Technology stack

| Component | Technology | Version |
|---|---|---:|
| Programming language | Python | 3.11+ recommended |
| Web framework | FastAPI | 0.115.0 |
| ASGI server | Uvicorn | 0.30.6 |
| Data validation | Pydantic | 2.9.2 |
| Environment settings | pydantic-settings | 2.5.2 |
| HTTP client | HTTPX | 0.27.2 |
| Environment-file support | python-dotenv | 1.0.1 |
| AI capability | ChatGPT-powered analysis | OpenAI API |
| AI provider | OpenAI | `https://api.openai.com/v1` |
| Default model | `gpt-5-nano` | Lowest-cost GPT model |

## 4. Repository structure

```text
syllabus-career-mapper/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── rate_limit.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py
│   │   └── response.py
│   └── services/
│       ├── __init__.py
│       ├── career_mapper.py
│       ├── openai_client.py
│       └── prompts.py
├── sample_syllabi/
│   ├── data_analytics_foundations.txt
│   ├── web_development_101.txt
│   ├── sample_request_career_map.json
│   ├── sample_request_compare.json
│   ├── sample_response_career_map.json
│   └── sample_response_error.json
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── Syllabus-to-Career-Mapper.postman_collection.json
└── document.md
```

### 4.1 Main modules

#### `app/main.py`

The FastAPI entry point. It:

- Creates the application
- Manages startup and shutdown resources
- Creates the shared `OpenAIClient`
- Creates the in-memory rate limiter
- Assigns request IDs
- Enforces the request-body size ceiling
- Applies per-client rate limiting
- Registers global exception handlers
- Defines the three API routes
- Emits structured request logs

#### `app/config.py`

Defines all environment-based settings in one Pydantic `Settings` class. The result of `get_settings()` is cached, so the `.env` file is parsed only once per process.

#### `app/models/request.py`

Defines and validates request payloads. In addition to ordinary type and length checks, it applies low-cost syllabus quality heuristics before any provider request is made.

#### `app/models/response.py`

Defines the public response schemas and the nested structures used for skills, gaps, projects, weekly plans, token usage, metadata, health information, and errors.

#### `app/services/prompts.py`

Builds system and user prompts for single-career analysis, two-career comparison, and corrective retries.

#### `app/services/openai_client.py`

Wraps OpenAI's Chat Completions API used to provide the project's ChatGPT-powered analysis, with:

- An asynchronous reusable HTTP client
- JSON response mode
- Configurable timeout and model settings
- Retry handling for transient failures
- Safe conversion of provider/network errors into application errors

#### `app/services/career_mapper.py`

Orchestrates the complete analysis flow:

1. Build the prompt.
2. Call OpenAI.
3. Strip accidental Markdown code fences.
4. Parse JSON.
5. Validate the generated structure.
6. Request one correction if parsing or selected validation fails.
7. Assemble the final typed API response.

#### `app/core/exceptions.py`

Defines application-specific exceptions and maps them to stable HTTP status codes and machine-readable error codes.

#### `app/core/logging.py`

Configures JSON-line logging and emits safe request metadata without accepting syllabus text, authorization headers, or API keys.

#### `app/core/rate_limit.py`

Implements a lightweight in-memory, per-client-IP sliding-window rate limiter.

## 5. Architecture

The service uses a layered architecture:

```text
API client
    |
    v
FastAPI middleware
  - request ID
  - body-size check
  - rate limit
    |
    v
Pydantic request validation
    |
    v
Route handler
    |
    v
Career-mapper service
  - build prompt
  - call provider
  - parse and validate JSON
  - optional corrective request
    |
    v
Shared asynchronous OpenAI client
    |
    v
OpenAI API
    |
    v
Typed Pydantic response
    |
    v
JSON response to client
```

### 5.1 Application lifecycle

FastAPI's lifespan handler creates two shared objects during startup:

- `app.state.openai_client`: one `OpenAIClient` for connection pooling
- `app.state.rate_limiter`: one `InMemoryRateLimiter`

When the application shuts down, the asynchronous HTTP client is closed cleanly.

### 5.2 Single-career request flow

For `POST /career-map`:

1. Middleware creates a UUID request ID.
2. The `Content-Length` header is checked against a 200,000-byte ceiling.
3. The client IP is checked against the rate limiter.
4. FastAPI and Pydantic validate and normalize the payload.
5. The prompt builder inserts student context, syllabus text, behavioral rules, and the required output schema.
6. The OpenAI client calls `/chat/completions` with JSON-object response mode.
7. The returned content is parsed as JSON.
8. The service checks required top-level fields and project count.
9. If JSON parsing or compatible validation fails, the model receives one correction prompt containing its prior output and the validation error.
10. The service builds a `CareerMapResponse`, adding:
    - A new `analysis_id`
    - Aggregated token usage
    - The request ID
    - Processing time
11. The route writes a structured log and returns the JSON response.

### 5.3 Comparison request flow

`POST /career-map/compare` follows the same overall path, but requests two analyses in one provider response. Each side includes its own readiness score, skill matches, gaps, projects, plan, assumptions, and warnings. Token usage and request metadata remain at the top level.

## 6. Installation and setup

### 6.1 Prerequisites

- Python 3.11 or newer
- An OpenAI Platform API key
- Network access to `https://api.openai.com`, unless a different compatible base URL is configured

A ChatGPT Free, Plus, Pro, Business, or Enterprise subscription is not used as the application's API credential. API access is configured separately through the OpenAI Platform.

### 6.2 Create a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 6.3 Install dependencies

```bash
pip install -r requirements.txt
```

### 6.4 Configure environment variables

Copy the example configuration:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

At minimum, replace the placeholder API key:

```dotenv
OPENAI_API_KEY=your_real_openai_api_key
```

Do not commit `.env`. It contains a secret and is already covered by the project's `.gitignore`.

### 6.5 Run the development server

Default command:

```bash
uvicorn app.main:app --reload --port 8000
```

Equivalent virtual-environment command on Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

If reload mode or port 8000 is unavailable:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

After startup:

- API root host: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`
- Health endpoint: `http://127.0.0.1:8000/health`

Replace `8000` with the selected port when using a different port.

## 7. Configuration reference

| Environment variable | Required | Default | Purpose |
|---|---:|---|---|
| `OPENAI_API_KEY` | Yes | None | Bearer token sent to OpenAI |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | OpenAI API base URL |
| `OPENAI_MODEL` | No | `gpt-5-nano` | Lowest-cost GPT model used for ChatGPT-powered analysis |
| `OPENAI_TIMEOUT_SECONDS` | No | `30.0` | Timeout for one provider call |
| `OPENAI_MAX_RETRIES` | No | `2` | Number of retries after the initial transient failure |
| `OPENAI_MAX_COMPLETION_TOKENS` | No | `4096` | Maximum completion tokens per provider call |
| `MAX_SYLLABUS_CHARS` | No | `20000` | Intended maximum syllabus size setting |
| `MIN_SYLLABUS_CHARS` | No | `200` | Intended minimum syllabus size setting |
| `RATE_LIMIT_PER_MINUTE` | No | `20` | Requests permitted per client IP in 60 seconds |
| `APP_NAME` | No | `Syllabus-to-Career Mapper` | Name returned by health metadata and shown in API docs |
| `ENVIRONMENT` | No | `development` | Environment label returned by `/health` |
| `LOG_FULL_SYLLABUS` | No | `false` | Declared logging preference |

Important implementation note: the request models currently enforce syllabus lengths of 200–20,000 characters directly in their Pydantic fields. Changing `MIN_SYLLABUS_CHARS` or `MAX_SYLLABUS_CHARS` does not currently alter those validation constraints. Similarly, `LOG_FULL_SYLLABUS` is defined but the current logger never logs syllabus content in either mode.

## 8. API conventions

### 8.1 Content type

POST endpoints expect:

```http
Content-Type: application/json
```

### 8.2 Request IDs

Every request receives a UUID request ID. Successful responses include it in the `X-Request-ID` response header. Career-analysis responses also include it at:

```text
meta.request_id
```

Error responses include it at:

```text
request_id
```

Clients should record this value when reporting a failed request.

### 8.3 Payload limit

Middleware rejects a request when its declared `Content-Length` is greater than 200,000 bytes. This ceiling allows JSON overhead while remaining well above the 20,000-character syllabus field limit.

### 8.4 Rate limit

All endpoints except `/health` are limited by client IP. The default is 20 requests per 60-second sliding window.

The limiter is:

- In memory
- Local to one Python process
- Reset when the server restarts
- Not shared among multiple workers or instances

## 9. Endpoint reference

### 9.1 `GET /health`

Confirms that the API process is running. This endpoint does not call OpenAI and is exempt from rate limiting.

Example request:

```bash
curl http://127.0.0.1:8000/health
```

Example response:

```json
{
  "status": "ok",
  "app_name": "Syllabus-to-Career Mapper",
  "environment": "development"
}
```

A successful health check confirms that FastAPI has started. It does not independently verify the API key or make a provider request.

### 9.2 `POST /career-map`

Analyzes one syllabus against one target career.

#### Request fields

| Field | Type | Required | Validation |
|---|---|---:|---|
| `course_name` | string | Yes | 3–100 characters |
| `target_career` | string | Yes | 2–100 characters |
| `education_level` | string enum | Yes | `school`, `undergraduate`, `postgraduate`, or `other` |
| `syllabus_text` | string | Yes | 200–20,000 characters plus quality checks |
| `study_hours_per_week` | integer | Yes | 1–40 |
| `plan_duration_weeks` | integer | Yes | 2–12 |
| `known_skills` | array of strings or null | No | At most 20 items; case-insensitive duplicates rejected |

Whitespace in `course_name`, `target_career`, and `syllabus_text` is trimmed and consecutive whitespace is collapsed.

For this endpoint, `known_skills` entries are trimmed, blank entries are discarded, and duplicates are rejected case-insensitively. For example, `["Python", " python "]` is invalid.

#### Example request

```json
{
  "course_name": "Introduction to Web Development",
  "target_career": "Backend Developer",
  "education_level": "undergraduate",
  "syllabus_text": "Week 1-2: HTML fundamentals - semantic tags, forms, accessibility basics. Week 3-4: CSS fundamentals - box model, flexbox, responsive design with media queries. Week 5-6: JavaScript basics - variables, functions, DOM manipulation, event handling. Week 7-8: Introduction to version control with Git and GitHub, including branching and pull requests. Week 9-10: Building RESTful APIs with Node.js and Express, including routing, middleware, and JSON request/response handling. Week 11: Introduction to relational databases and SQL - basic CRUD operations using PostgreSQL. Week 12: Authentication basics - sessions, cookies, and JSON Web Tokens. Week 13: Deploying a full-stack application to a cloud hosting provider. Week 14: Final project - students build and deploy a full-stack CRUD application with a database-backed API and a simple frontend.",
  "study_hours_per_week": 10,
  "plan_duration_weeks": 4,
  "known_skills": ["HTML", "CSS"]
}
```

Example curl command:

```bash
curl -X POST http://127.0.0.1:8000/career-map \
  -H "Content-Type: application/json" \
  --data @sample_syllabi/sample_request_career_map.json
```

#### Response structure

| Field | Type | Meaning |
|---|---|---|
| `analysis_id` | UUID | Identifier generated for this analysis |
| `course_summary` | string | Summary based on the submitted syllabus |
| `readiness_score` | integer | Estimated readiness from 0 to 100 |
| `readiness_explanation` | string | Plain-language reasoning behind the score |
| `matched_skills` | array | Career-relevant skills supported by syllabus evidence |
| `skill_gaps` | array | Missing or underdeveloped career skills |
| `project_recommendations` | array | Two or three demonstrable projects |
| `learning_plan` | array | Weekly learning tasks |
| `assumptions` | array of strings | Assumptions caused by incomplete information |
| `warnings` | array of strings | Qualifications or limitations |
| `usage` | object | Provider model and token counts |
| `meta` | object | Request ID and processing time |

#### Nested response objects

Matched skill:

```json
{
  "skill": "REST API development",
  "syllabus_evidence": "Building RESTful APIs with Node.js and Express",
  "career_relevance": "Backend developers commonly design and maintain HTTP APIs."
}
```

Skill gap:

```json
{
  "skill": "Automated testing",
  "importance": "Tests help prevent regressions in backend services.",
  "priority": "high",
  "next_step": "Add unit and integration tests to the course API project."
}
```

Project recommendation:

```json
{
  "title": "Tested Task Management API",
  "outcome": "A deployed repository containing a documented CRUD API.",
  "mapped_skills": ["Node.js", "Express", "PostgreSQL", "Testing"],
  "difficulty": "intermediate",
  "success_criteria": "The API is deployed, documented, and passes its automated test suite."
}
```

Learning week:

```json
{
  "week_number": 1,
  "focus": "API testing fundamentals",
  "tasks": [
    "Learn the difference between unit and integration tests.",
    "Write tests for two existing API routes."
  ],
  "estimated_hours": 8
}
```

Usage and metadata:

```json
{
  "usage": {
    "provider_model": "gpt-5-nano",
    "input_tokens": 1400,
    "output_tokens": 1800,
    "total_tokens": 3200
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "processing_time_ms": 2840.5
  }
}
```

### 9.3 `POST /career-map/compare`

Compares one syllabus against two different careers.

#### Request fields

| Field | Type | Required | Validation |
|---|---|---:|---|
| `course_name` | string | Yes | 3–100 characters |
| `syllabus_text` | string | Yes | 200–20,000 characters plus quality checks |
| `education_level` | string enum | Yes | `school`, `undergraduate`, `postgraduate`, or `other` |
| `study_hours_per_week` | integer | Yes | 1–40 |
| `plan_duration_weeks` | integer | Yes | 2–12 |
| `target_career_a` | string | Yes | 2–100 characters |
| `target_career_b` | string | Yes | 2–100 characters and different from career A |
| `known_skills` | array of strings or null | No | At most 20 items |

Career names are compared after trimming and lowercasing. Values such as `"Data Analyst"` and `" data analyst "` are therefore considered the same and rejected.

Implementation note: unlike `CareerMapRequest`, the comparison request currently does not apply the dedicated trim-and-deduplicate validator to individual `known_skills` entries.

#### Example request

```json
{
  "course_name": "Foundations of Data Analytics",
  "syllabus_text": "Week 1: Introduction to data analytics - the analytics lifecycle, types of data, and common business use cases. Week 2: Excel and spreadsheet-based analysis - pivot tables, VLOOKUP, and basic charting for exploratory data analysis. Week 3: Introduction to SQL - SELECT statements, WHERE filtering, GROUP BY, and JOIN operations across multiple tables. Week 4: Data cleaning principles - handling missing values, duplicates, and inconsistent formatting in real-world datasets. Week 5: Introduction to Python for data analysis using pandas - reading CSV files, filtering rows, and creating summary statistics. Week 6: Data visualization principles - choosing the right chart type, avoiding misleading visuals, and building dashboards in Tableau. Week 7: Descriptive statistics - mean, median, standard deviation, and correlation. Week 8: Introduction to A/B testing and basic hypothesis testing concepts. Week 9: Storytelling with data - structuring a data-driven presentation for a non-technical audience. Week 10: Capstone project - students analyze a provided retail sales dataset and present findings and recommendations to a mock stakeholder panel.",
  "education_level": "undergraduate",
  "study_hours_per_week": 6,
  "plan_duration_weeks": 3,
  "target_career_a": "Data Analyst",
  "target_career_b": "Data Engineer"
}
```

Example curl command:

```bash
curl -X POST http://127.0.0.1:8000/career-map/compare \
  -H "Content-Type: application/json" \
  --data @sample_syllabi/sample_request_compare.json
```

#### Response structure

```text
analysis_id
course_summary
career_a
  target_career
  readiness_score
  readiness_explanation
  matched_skills
  skill_gaps
  project_recommendations
  learning_plan
  assumptions
  warnings
career_b
  target_career
  readiness_score
  readiness_explanation
  matched_skills
  skill_gaps
  project_recommendations
  learning_plan
  assumptions
  warnings
recommendation
usage
meta
```

The API sets `career_a.target_career` and `career_b.target_career` from the submitted request rather than trusting the provider to reproduce the names.

## 10. Input validation and syllabus quality checks

Validation occurs before the application spends provider tokens.

### 10.1 Standard field validation

Pydantic enforces:

- Required fields
- Correct JSON types
- String length limits
- Integer ranges
- Education-level enum values
- Maximum array length
- Different career names for comparison requests

### 10.2 Syllabus normalization

The syllabus is stripped and all whitespace sequences are collapsed to one space. As a result, newlines and repeated spacing are not preserved when the syllabus reaches the prompt.

### 10.3 Quality heuristics

The syllabus is rejected when any of the following applies:

1. **Mostly URLs**  
   Text matched as URLs accounts for more than 50% of all characters.

2. **Too few recognizable words**  
   Fewer than 20 alphabetic words containing at least two letters are found.

3. **Very low vocabulary diversity**  
   With at least 20 words present, fewer than 15% are unique after lowercasing.

4. **Repeated lines or sentences**  
   A non-trivial line or sentence occurs at least five times and accounts for more than 40% of the extracted lines/sentences.

These rules are intentionally heuristic. They reject obvious spam and low-information input, but they do not prove that a syllabus is academically valid.

## 11. Prompt and LLM behavior

### 11.1 Provider request

The ChatGPT-powered analysis is performed by sending a POST request to OpenAI:

```text
{OPENAI_BASE_URL}/chat/completions
```

The request uses the low-cost `gpt-5-nano` model by default:

```json
{
      "model": "gpt-5-nano",
  "messages": [
    {"role": "system", "content": "<behavioral rules>"},
    {"role": "user", "content": "<student context, syllabus, and schema>"}
  ],
  "temperature": 0.2,
  "max_tokens": 4096,
  "response_format": {"type": "json_object"}
}
```

Temperature and maximum tokens use configured values.

### 11.2 Grounding rules

The system prompt requires the model to:

- Reference only submitted syllabus topics
- Cite syllabus evidence for every matched skill
- Avoid guaranteeing employment or outcomes
- Expose assumptions and warnings
- Recommend demonstrable projects
- Respect education level and available weekly study time
- Use plain language
- Return only JSON

### 11.3 Corrective output retry

Provider transport retries and output-correction retries are separate:

- **Transport retry:** handled by `OpenAIClient` for timeouts, network errors, HTTP 429, and selected 5xx statuses
- **Correction retry:** handled by `career_mapper.py` when the first generated output cannot be parsed or passes through a supported schema-validation failure

The correction prompt includes:

- The validation error
- The previous generated output
- A request to return only corrected JSON

Only one corrective generation is attempted. Token counts from both generations are added together.

### 11.4 Defensive code-fence removal

Although the model is told to return raw JSON, the service removes an outer Markdown code fence such as:

````text
```json
{...}
```
````

before attempting to parse the content.

## 12. Provider retry behavior

The default `OPENAI_MAX_RETRIES=2` means one initial attempt plus up to two retries.

Retryable provider HTTP statuses are:

- 429 Too Many Requests
- 500 Internal Server Error
- 502 Bad Gateway
- 503 Service Unavailable
- 504 Gateway Timeout

Timeouts and selected connection/read/network errors are also retried. The current implementation retries immediately; it does not add exponential backoff or jitter.

Non-retryable provider errors, such as most 4xx responses, are converted to a safe `PROVIDER_CONNECTION_ERROR`. Provider response bodies and API secrets are not exposed to the API client.

## 13. Error handling

All application errors use this envelope:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "One or more request fields are invalid.",
  "request_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "details": [
    {
      "field": "study_hours_per_week",
      "message": "Input should be less than or equal to 40"
    }
  ]
}
```

The `details` field is optional and is primarily used for request validation.

| HTTP status | Error code | Cause |
|---:|---|---|
| 413 | `PAYLOAD_TOO_LARGE` | Declared body length exceeds 200,000 bytes |
| 422 | `VALIDATION_ERROR` | Missing, mistyped, out-of-range, duplicate, low-quality, or otherwise invalid input |
| 429 | `RATE_LIMIT_EXCEEDED` | Client IP exceeded the configured request window |
| 502 | `PROVIDER_BAD_RESPONSE` | Provider output could not be converted into the required structure after correction |
| 502 | `PROVIDER_CONNECTION_ERROR` | Provider returned an unrecoverable HTTP error or could not be reached |
| 504 | `PROVIDER_TIMEOUT` | Provider timed out after all configured attempts |
| 500 | `INTERNAL_ERROR` | Unexpected unhandled application failure |

The generic 500 handler returns a safe message and does not expose exception details or stack traces.

## 14. Logging and observability

The application writes one-line JSON log events to standard output.

Example:

```json
{
  "ts": 1785370000.25,
  "request_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "endpoint": "/career-map",
  "status_code": 200,
  "total_time_ms": 2840.5,
  "input_tokens": 1400,
  "output_tokens": 1800
}
```

Depending on the event, a log may contain:

- Unix timestamp
- Request ID
- Endpoint
- HTTP status
- Total time
- OpenAI time, if supplied
- Input and output token counts
- Machine-readable error code

Provider retries emit a separate `openai_retry` event with the attempt number and HTTP status.

The safe logging helper does not accept syllabus content, API keys, or authorization headers. Full syllabus content is not logged by the current implementation.

## 15. Security and privacy considerations

### 15.1 Existing protections

- The OpenAI API key is loaded from environment configuration.
- Error responses do not expose raw exception text or stack traces.
- Provider errors are converted into stable, safe messages.
- The logging helper accepts only structured metadata.
- Request size and field size limits reduce abuse.
- Rate limiting reduces repeated requests from one client.
- Obvious junk input is rejected before provider use.

### 15.2 Important deployment considerations

The current application does not include:

- Authentication or authorization
- TLS termination
- CORS configuration
- Persistent audit storage
- Content moderation
- Personally identifiable information detection
- Distributed rate limiting
- API-key rotation logic

For an internet-facing deployment:

- Place the service behind HTTPS.
- Add authentication appropriate to the client application.
- Restrict CORS to trusted origins if a browser frontend is added.
- Do not submit sensitive student information in syllabus text.
- Use a shared limiter such as Redis across multiple instances.
- Store secrets in the hosting platform's secret manager.
- Add monitoring for latency, provider failure rate, validation failures, and token use.

## 16. Performance characteristics

The main source of latency is the external LLM request. A normal analysis requires one provider call; malformed provider output may require a second generation. Transient provider failures may additionally trigger transport retries.

Connection pooling reduces repeated connection setup overhead. The FastAPI routes and HTTP client are asynchronous, so one process can wait on multiple provider requests concurrently.

Potential scaling limitations include:

- In-memory rate-limit state
- No shared cache
- No background job system for long analyses
- Provider token and request limits
- Potentially large prompts when the syllabus approaches 20,000 characters

## 17. Testing the API

### 17.1 Swagger UI

Start the server and open:

```text
http://127.0.0.1:8000/docs
```

Swagger UI displays schemas, allows requests to be submitted, and shows status codes and response bodies.

### 17.2 Postman

Import:

```text
Syllabus-to-Career-Mapper.postman_collection.json
```

Update the collection's `base_url` variable if the server is not using `http://localhost:8000`.

### 17.3 PowerShell examples

Health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Career map using the sample file:

```powershell
$body = Get-Content -Raw "sample_syllabi\sample_request_career_map.json"
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/career-map" `
  -ContentType "application/json" `
  -Body $body
```

Career comparison:

```powershell
$body = Get-Content -Raw "sample_syllabi\sample_request_compare.json"
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/career-map/compare" `
  -ContentType "application/json" `
  -Body $body
```

### 17.4 Suggested validation tests

Useful negative tests include:

- Omit a required field.
- Submit fewer than 200 syllabus characters.
- Submit more than 40 study hours.
- Use an unsupported education level.
- Repeat a known skill with different capitalization.
- Use the same career on both sides of a comparison.
- Submit mostly links.
- Submit one word repeatedly.
- Send more than the rate-limit allowance.

## 18. Current limitations and implementation caveats

1. **No automated test suite is included**  
   The repository contains sample requests and responses but no unit, integration, or end-to-end tests.

2. **No persistent storage**  
   `analysis_id` values identify responses but do not allow later retrieval. Analyses disappear after the response is returned.

3. **No frontend**  
   Consumers must use Swagger, Postman, curl, PowerShell, or a custom client.

4. **No authentication**  
   Any client that can reach the server can call the analysis endpoints.

5. **Rate limiting is process-local**  
   Multiple workers or servers maintain independent counters.

6. **Configurable syllabus limits are not wired to model constraints**  
   The environment exposes minimum and maximum syllabus settings, but request models currently use literal values of 200 and 20,000.

7. **Comparison `known_skills` validation differs from single-map validation**  
   The comparison model limits the list length but does not currently reuse the individual trimming and duplicate-rejection validator.

8. **Generated-output validation is partly staged**  
   The service performs preliminary shape checks and then constructs the final Pydantic response. Some nested or type errors may only appear during final response construction. The corrective retry does not currently cover every possible `ValueError` or final-model validation path.

9. **Prompt constraints are not all enforced deterministically**  
   The prompt requests exactly `plan_duration_weeks` entries and weekly hours within the student's budget, but the final Pydantic schemas do not independently enforce plan length, sequential week numbering, or the weekly hour ceiling.

10. **Priority and difficulty are free-form strings**  
    The prompt suggests fixed values, but `priority` and `difficulty` are not Pydantic enums.

11. **No retry backoff**  
    Transient provider retries occur immediately.

12. **Health does not verify provider connectivity**  
    `/health` verifies application availability only.

13. **No live job-market grounding**  
    Career requirements are based on the model's general knowledge, not current job postings or a versioned occupational-skills database.

14. **LLM output is probabilistic**  
    Low temperature and schema validation improve consistency but cannot make scores objective or perfectly repeatable.

## 19. Recommended future improvements

### High priority

- Add unit tests for request validators, rate limiting, prompt construction, and error mapping.
- Add integration tests with `httpx.MockTransport` or a mocked OpenAI client.
- Perform complete Pydantic validation inside the correction loop.
- Enforce learning-plan length, week numbering, and weekly hour limits in code.
- Replace free-form priority and difficulty fields with enums.
- Make environment-based syllabus limits actually control validation.
- Apply the same `known_skills` normalization to both request types.

### Production readiness

- Add authentication and authorization.
- Configure CORS for known frontend origins.
- Add Redis-backed distributed rate limiting.
- Add retry backoff with jitter.
- Add metrics and tracing.
- Add readiness checks for provider configuration or a separate deep-health endpoint.
- Use a secret manager instead of a local `.env` file.
- Define explicit production worker and reverse-proxy settings.

### Product capabilities

- Add a frontend for syllabus submission and result visualization.
- Store analysis history with user consent.
- Export reports as PDF or Markdown.
- Support syllabus file uploads with safe text extraction.
- Ground career requirements in a maintained skills taxonomy or current job-market dataset.
- Add side-by-side comparison of more than two careers.
- Allow users to revise known skills and regenerate only the affected plan.

## 20. Extending the codebase

### 20.1 Add a new endpoint

The usual pattern is:

1. Define a request model in `app/models/request.py`.
2. Define response models in `app/models/response.py`.
3. Add prompt construction in `app/services/prompts.py`.
4. Add orchestration in `app/services/career_mapper.py`.
5. Add a thin route in `app/main.py`.
6. Reuse the shared `request.app.state.openai_client`.
7. Raise `AppError` subclasses rather than leaking raw provider exceptions.
8. Add tests and example requests.

### 20.2 Change the AI provider

The current client uses OpenAI's `/chat/completions` endpoint with JSON-object mode. The provider URL and model remain configurable through:

```dotenv
OPENAI_BASE_URL=<compatible base URL>
OPENAI_API_KEY=<provider key>
OPENAI_MODEL=<model identifier>
```

If the provider uses a different request or response format, implement a new client behind an equivalent `chat_completion_json()` interface so the rest of the application remains unchanged.

### 20.3 Add persistence

A persistence layer could store:

- `analysis_id`
- Request owner
- A hash or redacted form of the submitted syllabus
- Target career information
- Validated response JSON
- Provider model and token usage
- Request and creation timestamps

Raw syllabus retention should be an explicit product and privacy decision rather than a default.

## 21. Troubleshooting

### Application fails during import with a settings validation error

Cause: `OPENAI_API_KEY` is missing.

Fix: create `.env` and set a non-empty key.

### `401` or provider connection error during analysis

Likely causes:

- Invalid or expired API key
- Wrong provider base URL
- Model unavailable for the account

Verify the `.env` values and restart the application so cached settings are reloaded.

### Provider timeout

Increase:

```dotenv
OPENAI_TIMEOUT_SECONDS=60
```

Then restart the server. Also check provider status and network connectivity.

### `422 VALIDATION_ERROR`

Inspect `details`. Common causes include:

- Syllabus below 200 characters
- Too few meaningful words
- Mostly repeated or linked content
- Invalid education level
- Plan shorter than 2 or longer than 12 weeks
- Duplicate known skills

### `429 RATE_LIMIT_EXCEEDED`

Wait for entries to age out of the 60-second window or adjust `RATE_LIMIT_PER_MINUTE` and restart the server.

### Port binding fails on Windows

Try a different explicit loopback port without reload mode:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then use `http://127.0.0.1:8765/docs`.

### Configuration changes do not take effect

Settings are cached per Python process. Restart Uvicorn after editing `.env`.

## 22. Scope summary

The project provides a focused, well-separated, ChatGPT-powered backend for transforming a syllabus into an evidence-based career map through the OpenAI API. Its strongest implementation features are typed API contracts, pre-provider input filtering, reusable asynchronous networking, consistent error envelopes, safe logging, request correlation, and an automatic correction attempt for malformed model output.

It should currently be treated as a development or demonstration service. Before production use, the most important additions are comprehensive tests, stronger generated-output enforcement, authentication, distributed rate limiting, observability, and explicit privacy controls.
