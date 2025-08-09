# --- include all imports here ---
from datetime import datetime, timedelta
import json
import asyncio
import uuid
from fastapi import (
    APIRouter,
    HTTPException,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict
from src import db

from src.utils import create_agent_session, get_agent_session
from src.agent import run_agent_session
from src.websocket_manager import ws_manager
from src.logger import get_logger
from src.models import (
    SharedConfiguration,
    CreateShareRequest,
    CreateShareResponse,
    GetShareResponse,
)

logger = get_logger(__name__)


router = APIRouter()


class StartAgentRequest(BaseModel):
    html: str
    query: str
    model_type: str = "gemini"
    initial_screenshot: Optional[str] = None


class StartAgentResponse(BaseModel):
    session_id: str
    message: str


# --- websocket communication - no longer need http response models ---


@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Lemur Agent API is running"}


@router.websocket("/agent/{session_id}/ws")
async def websocket_agent_session(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for agent communication"""
    try:
        await ws_manager.connect(session_id, websocket)
        logger.info(f"WebSocket connected for session: {session_id}")

        # --- start agent in background ---
        agent_task = asyncio.create_task(run_agent_session(session_id))

        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info(f"Agent task cancelled for session: {session_id}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(
            f"WebSocket error for session {session_id}: {str(e)}", exc_info=True
        )
    finally:
        await ws_manager.disconnect(session_id)


@router.post("/agent/start", response_model=StartAgentResponse)
async def start_agent_session(request: StartAgentRequest):
    """Create a new AI agent session"""
    session_id = str(uuid.uuid4())
    logger.info(f"Creating new agent session: {session_id}")

    # Max iterations is now a fixed config value
    MAX_ITERATIONS = 10

    try:
        create_agent_session(
            session_id,
            request.html,
            request.query,
            MAX_ITERATIONS,
            request.initial_screenshot,
        )
        logger.info(f"Agent session {session_id} created")

        return StartAgentResponse(
            session_id=session_id,
            message="Agent session created. Connect via WebSocket.",
        )
    except Exception as e:
        logger.error(
            f"Failed to create agent session {session_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to create session: {str(e)}"
        )


# --- legacy http endpoints removed - now using websocket ---


# --- URL Sharing API Endpoints ---


@router.post("/api/share", response_model=CreateShareResponse)
async def create_shared_configuration(request: CreateShareRequest):
    """Create a shareable configuration that can be accessed via URL parameter"""
    try:
        share_id = str(uuid.uuid4())[:8]  # Use shorter ID for URLs

        # Calculate expiration date
        expires_at = None
        if request.expires_in_days:
            expires_at = (
                datetime.now() + timedelta(days=request.expires_in_days)
            ).isoformat()

        # Create shared configuration
        shared_config = SharedConfiguration(
            id=share_id,
            original_url=request.url,
            modified_html=request.html,
            title=request.title,
            description=request.description,
            created_at=datetime.now().isoformat(),
            expires_at=expires_at,
            view_count=0,
        )

        # Store in database
        db.set(f"share:{share_id}", shared_config.dict())

        # Generate shareable URL (the original URL with aid parameter)
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        parsed_url = urlparse(request.url)
        query_params = parse_qs(parsed_url.query)
        query_params["aid"] = [share_id]
        new_query = urlencode(query_params, doseq=True)
        shareable_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment,
            )
        )

        logger.info(f"Created shared configuration: {share_id} for URL: {request.url}")

        return CreateShareResponse(
            share_id=share_id,
            shareable_url=shareable_url,
            message="Shareable URL created successfully",
        )

    except Exception as e:
        logger.error(f"Failed to create shared configuration: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create shareable URL: {str(e)}"
        )


@router.get("/api/share/{share_id}", response_model=GetShareResponse)
async def get_shared_configuration(share_id: str):
    """Retrieve a shared configuration by ID"""
    try:
        # Get shared configuration from database
        shared_config_data = db.get(f"share:{share_id}")

        if not shared_config_data:
            raise HTTPException(
                status_code=404, detail="Shared configuration not found"
            )

        shared_config = SharedConfiguration(**shared_config_data)

        # Check if configuration has expired
        if shared_config.expires_at:
            expiry_date = datetime.fromisoformat(shared_config.expires_at)
            if datetime.now() > expiry_date:
                # Remove expired configuration
                db.set(f"share:{share_id}", None)
                raise HTTPException(
                    status_code=410, detail="Shared configuration has expired"
                )

        # Increment view count
        shared_config.view_count += 1
        db.set(f"share:{share_id}", shared_config.dict())

        logger.info(
            f"Retrieved shared configuration: {share_id} (views: {shared_config.view_count})"
        )

        return GetShareResponse(
            original_url=shared_config.original_url,
            modified_html=shared_config.modified_html,
            title=shared_config.title,
            description=shared_config.description,
            created_at=shared_config.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to retrieve shared configuration {share_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve shared configuration: {str(e)}"
        )
