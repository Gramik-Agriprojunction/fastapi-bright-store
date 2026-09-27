# Bright Store API

FastAPI backend for the Bright Store project. The UAT branch is `uat`.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. OpenAPI documentation is
available at `/docs`.

## Project structure

```text
app/
├── api/v1/          # versioned HTTP routes
├── core/            # settings and shared concerns
├── db/              # SQLAlchemy database layer
├── integrations/ai/ # provider-independent AI boundary
└── modules/         # business domains (products, orders, etc.)
```

See [`docs/architecture.md`](docs/architecture.md) before adding a new
business feature.

## Database

The API uses an async PostgreSQL connection through `DATABASE_URL`. Put the
Lens UAT database connection string in `.env`; credentials must not be
committed. The `/ready` endpoint verifies database connectivity.

## Checks

```bash
ruff check .
pytest
```
