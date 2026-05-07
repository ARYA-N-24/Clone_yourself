"""
Clone Yourself Platform — FastAPI application entry point.

Configures:
- CORS middleware (restricted to FRONTEND_URL in production, * in dev)
- SlowAPI rate-limit middleware
- Router includes for all six API modules
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.api import auth, emails, calendar, dashboard, followup, analytics

load_dotenv()

# ---------------------------------------------------------------------------
# Rate limiter (shared instance imported by individual route modules)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    yield


app = FastAPI(
    title="Clone Yourself Platform",
    description="AI-powered personal digital worker — FastAPI backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach the limiter to the app state so SlowAPI can find it
app.state.limiter = limiter

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# CORS — restrict to FRONTEND_URL in production, allow all origins in dev
environment = os.getenv("ENVIRONMENT", "development")
frontend_url = os.getenv("FRONTEND_URL", "")

if environment == "production" and frontend_url:
    allowed_origins = [frontend_url]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SlowAPI rate-limit middleware
app.add_middleware(SlowAPIMiddleware)

# Register the 429 handler for rate-limit violations
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(emails.router, prefix="/emails", tags=["emails"])
app.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(followup.router, prefix="/followups", tags=["followup"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
