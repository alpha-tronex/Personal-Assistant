# FastAPI Code Scaffold (Starter Snippets)

Use these snippets as a baseline implementation for your MVP backend.  
They are intentionally minimal and map to the contracts in `09-api-contracts.md`.

## 1) `app/main.py`

```python
from fastapi import FastAPI
from app.api.v1 import auth, sync, tasks, briefing, dashboard

app = FastAPI(title="Morning Command Dashboard API", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(briefing.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
```

## 2) `app/core/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"

    database_url: str

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_scopes: str

    token_encryption_key: str
    internal_job_token: str = "change-me"


settings = Settings()
```

## 3) `app/core/database.py`

```python
from sqlmodel import SQLModel, Session, create_engine
from app.core.config import settings

engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
```

## 4) `app/schemas/auth.py`

```python
from pydantic import BaseModel


class OAuthStartRequest(BaseModel):
    return_to: str | None = "/dashboard"


class OAuthStartResponse(BaseModel):
    auth_url: str
    state: str
```

## 5) `app/services/google_oauth_service.py`

```python
from urllib.parse import urlencode
import secrets
from app.core.config import settings


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def build_google_auth_url() -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": settings.google_scopes,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state
```

## 6) `app/api/v1/auth.py`

```python
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from app.schemas.auth import OAuthStartRequest, OAuthStartResponse
from app.services.google_oauth_service import build_google_auth_url
from app.core.config import settings

router = APIRouter(tags=["Auth"])

# Replace with persistent storage (Redis/DB) in real implementation.
STATE_STORE: set[str] = set()


@router.post("/auth/google/start", response_model=OAuthStartResponse)
def start_google_oauth(payload: OAuthStartRequest) -> OAuthStartResponse:
    auth_url, state = build_google_auth_url()
    STATE_STORE.add(state)
    return OAuthStartResponse(auth_url=auth_url, state=state)


@router.get("/auth/google/callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    if state not in STATE_STORE:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # TODO:
    # 1) Exchange code for tokens via GOOGLE_TOKEN_URL
    # 2) Encrypt and persist refresh token
    # 3) Upsert user + oauth_tokens
    # 4) Remove used state
    STATE_STORE.remove(state)
    return RedirectResponse(url=f"{settings.frontend_base_url}/dashboard")
```

## 7) `app/schemas/common.py` (error shape)

```python
from pydantic import BaseModel
from typing import Any


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
```

## 8) `app/api/v1/sync.py` (contract skeleton)

```python
from uuid import uuid4
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Sync"])


class QueuedJob(BaseModel):
    job_id: str
    status: str


@router.post("/sync/gmail", response_model=QueuedJob, status_code=202)
def queue_gmail_sync() -> QueuedJob:
    # TODO enqueue background job
    return QueuedJob(job_id=str(uuid4()), status="queued")


@router.post("/sync/calendar", response_model=QueuedJob, status_code=202)
def queue_calendar_sync() -> QueuedJob:
    # TODO enqueue background job
    return QueuedJob(job_id=str(uuid4()), status="queued")
```

## 9) `app/models/task.py` (starter)

```python
from datetime import datetime, date
from sqlmodel import SQLModel, Field
from typing import Optional
import uuid


class Task(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    category: str
    action_type: str
    urgency: str
    title: str
    details: Optional[str] = None
    due_at: Optional[datetime] = None
    priority_score: float = 0
    status: str = "Open"
    snoozed_until: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

## 10) Local run commands

```bash
# from backend/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Docs:
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 11) Immediate next steps

1. Replace in-memory `STATE_STORE` with persistent state table/cache.
2. Implement token exchange in callback (`httpx` POST token endpoint).
3. Add encrypted token storage (`oauth_tokens`).
4. Build Gmail and Calendar sync services behind `/sync/*`.
5. Add Alembic migrations before adding more models.
