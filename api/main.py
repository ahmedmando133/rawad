"""
Main FastAPI Application Entrypoint.

Provides:
    - Root and /health endpoints for monitoring and deployment uptime checks.
    - Mounts /webhook router for Meta Graph API messaging.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.webhook import get_assistant, router as webhook_router

load_dotenv()

# Configure unified application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("clinic_assistant")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Pre-warm the AI assistant and knowledge base on startup."""
    logger.info("Initializing Pediatrician AI Assistant...")
    try:
        assistant = get_assistant()
        logger.info(
            "AI Assistant initialized successfully. Loaded profile for: %s",
            assistant.doctor_profile.get("doctor", {}).get("name", {}).get("ar", "Doctor"),
        )
    except Exception:
        logger.exception("Failed to initialize AI Assistant on startup.")
    yield
    logger.info("Application shutting down.")


app = FastAPI(
    title="Pediatrician AI Assistant — Meta Messenger API",
    description="Production-grade AI assistant for Dr. Rawad Shehima's clinic in Tripoli, Libya.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware (allows web dashboard or diagnostic tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Meta Webhook endpoints
app.include_router(webhook_router)


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    """Root endpoint verifying API is live."""
    return {
        "status": "online",
        "service": "Pediatrician AI Messenger Assistant",
        "doctor": "د. رواد شحيمة - مجمع عيادات الرباط",
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Standard health check for deployment monitors / cloud platforms."""
    return {"status": "healthy"}
