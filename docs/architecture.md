# Architecture

## Layers

- `app/api`: HTTP-only concerns, versioned routers, request/response handling.
- `app/modules`: business domains. Each domain should contain its schemas,
  repository, service, and endpoints.
- `app/db`: SQLAlchemy engine, sessions, base model, and migrations.
- `app/integrations`: external systems such as Lens and AI providers.
- `app/core`: configuration and cross-cutting application concerns.

Business rules belong in services. Endpoints should validate input, call a
service, and translate the result into an HTTP response.

## AI boundary

AI code is isolated behind `app.integrations.ai.contracts.AIClient`. A provider
adapter can be added later without coupling domain services to an SDK. Prompts,
model selection, retries, token usage, and safety checks should remain inside
the AI integration layer.

AI-generated output must be treated as untrusted input: validate structured
responses with Pydantic schemas and never allow model output to execute
database queries or application commands directly.

## New domain module pattern

```text
app/modules/<domain>/
├── models.py
├── schemas.py
├── repository.py
├── service.py
└── router.py
```
