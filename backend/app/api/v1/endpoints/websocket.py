"""
WebSocket endpoint for the live command-center feed.

Endpoint
--------
WS /ws/live?token=<jwt>

Protocol
--------
The server sends JSON frames; the client may send ping frames.

Server-to-client message shapes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
{"type": "ping"}
{"type": "pong"}
{"type": "connected",     "client_id": "...", "ts": "..."}
{"type": "job_progress",  "job_id": "...", "status": "...", "total_found": 0, ...}
{"type": "audit_complete","audit_id": "...", "business_id": "...", "scores": {...}}
{"type": "new_business",  "business": {...}}
{"type": "error_event",   "code": "...", "message": "..."}

Client-to-server message shapes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
{"type": "ping"}           – triggers a pong reply

Authentication
--------------
JWT token passed as a query parameter: ?token=<access_token>
The WS handshake is validated before any frame is exchanged.

Redis pub/sub
-------------
All workers publish to channels in the pattern  ``bi:ws:<event_type>``.
The WebSocket handler subscribes to ``bi:ws:*`` so messages are broadcast
to every connected client, distributing across Uvicorn worker processes.

Connection registry
-------------------
An in-process dict ``_CONNECTIONS`` tracks active WebSocket objects.
For single-worker deployments this is sufficient.  For multi-worker setups
the Redis pub/sub layer ensures messages reach all processes regardless
of which worker holds a given connection.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.security import verify_token
from app.core.exceptions import AuthenticationError

router = APIRouter(tags=["websocket"])

# ---------------------------------------------------------------------------
# In-process connection registry
# ---------------------------------------------------------------------------

# Maps client_id (str) -> WebSocket
_CONNECTIONS: Dict[str, WebSocket] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_json(ws: WebSocket, payload: Dict[str, Any]) -> None:
    """Send a JSON frame, silently dropping on closed connections."""
    try:
        await ws.send_json(payload)
    except Exception:
        pass


async def _broadcast(payload: Dict[str, Any]) -> None:
    """Send a message to all currently connected clients."""
    dead: Set[str] = set()
    for cid, ws in list(_CONNECTIONS.items()):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(cid)
    for cid in dead:
        _CONNECTIONS.pop(cid, None)


# ---------------------------------------------------------------------------
# Redis pub/sub listener
# ---------------------------------------------------------------------------


async def _redis_listener(client_id: str) -> None:
    """
    Subscribe to ``bi:ws:*`` Redis channels and forward published messages
    to all in-process WebSocket connections.

    Runs as a background task until the WebSocket disconnects.
    """
    try:
        import aioredis  # type: ignore
    except ImportError:
        # aioredis not available – skip Redis pub/sub
        return

    try:
        redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        pubsub = redis.pubsub()
        await pubsub.psubscribe("bi:ws:*")

        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue

            # Stop if the owning connection is gone
            if client_id not in _CONNECTIONS:
                break

            try:
                data = json.loads(message.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue

            await _broadcast(data)

        await pubsub.punsubscribe("bi:ws:*")
        await redis.close()

    except Exception:
        # Redis unavailable – degrade gracefully, WebSocket still works
        pass


# ---------------------------------------------------------------------------
# Heartbeat task
# ---------------------------------------------------------------------------


async def _heartbeat(ws: WebSocket, client_id: str, interval: int = 30) -> None:
    """Send a ping frame every *interval* seconds."""
    while client_id in _CONNECTIONS:
        await asyncio.sleep(interval)
        if client_id not in _CONNECTIONS:
            break
        await _send_json(ws, {"type": "ping", "ts": _utc_now_iso()})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/live")
async def websocket_live(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> None:
    """
    Authenticated WebSocket endpoint for the live command-center.

    Query parameters
    ----------------
    token : str
        A valid JWT access token.  The connection is immediately closed with
        code 4001 if the token is absent or invalid.
    """
    # ------------------------------------------------------------------
    # Authenticate before accepting the connection
    # ------------------------------------------------------------------
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token.")
        return

    try:
        token_data = verify_token(token, expected_type="access")
    except AuthenticationError:
        await websocket.close(code=4001, reason="Invalid or expired token.")
        return

    # ------------------------------------------------------------------
    # Accept & register
    # ------------------------------------------------------------------
    await websocket.accept()
    client_id = uuid.uuid4().hex
    _CONNECTIONS[client_id] = websocket

    # Send welcome frame
    await _send_json(
        websocket,
        {
            "type": "connected",
            "client_id": client_id,
            "user_id": token_data.sub,
            "ts": _utc_now_iso(),
            "active_connections": len(_CONNECTIONS),
        },
    )

    # ------------------------------------------------------------------
    # Start background tasks (heartbeat + Redis listener)
    # ------------------------------------------------------------------
    heartbeat_task = asyncio.create_task(_heartbeat(websocket, client_id))
    redis_task = asyncio.create_task(_redis_listener(client_id))

    # ------------------------------------------------------------------
    # Main receive loop
    # ------------------------------------------------------------------
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send_json(
                    websocket,
                    {
                        "type": "error_event",
                        "code": "invalid_json",
                        "message": "Could not parse message as JSON.",
                    },
                )
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await _send_json(websocket, {"type": "pong", "ts": _utc_now_iso()})

            elif msg_type == "pong":
                # Client acknowledging our heartbeat ping — no action needed
                pass

            else:
                await _send_json(
                    websocket,
                    {
                        "type": "error_event",
                        "code": "unknown_message_type",
                        "message": f"Unknown message type: '{msg_type}'.",
                    },
                )

    except WebSocketDisconnect:
        pass

    except Exception as exc:
        await _send_json(
            websocket,
            {
                "type": "error_event",
                "code": "server_error",
                "message": "An unexpected server error occurred.",
            },
        )

    finally:
        # ------------------------------------------------------------------
        # Cleanup
        # ------------------------------------------------------------------
        _CONNECTIONS.pop(client_id, None)
        heartbeat_task.cancel()
        redis_task.cancel()

        # Swallow CancelledError from the tasks
        for task in (heartbeat_task, redis_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Utility: publish a message from application code
# ---------------------------------------------------------------------------


async def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Publish an event to all connected WebSocket clients.

    This function is meant to be called from background tasks, Celery
    result callbacks, or any part of the application that needs to push
    a real-time update.

    If Redis is available the message is published on ``bi:ws:<event_type>``
    so it reaches all Uvicorn workers.  It is also broadcast directly to
    clients held in the current process.

    Parameters
    ----------
    event_type:
        One of ``job_progress``, ``audit_complete``, ``new_business``,
        ``error_event``, or any custom type understood by the frontend.
    payload:
        Arbitrary JSON-serialisable dict.  The ``type`` key will be added
        automatically.
    """
    frame = {"type": event_type, "ts": _utc_now_iso(), **payload}

    # Broadcast in-process
    await _broadcast(frame)

    # Publish to Redis for cross-worker delivery
    try:
        import aioredis  # type: ignore

        redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis.publish(f"bi:ws:{event_type}", json.dumps(frame))
        await redis.close()
    except Exception:
        pass  # Degrade gracefully if Redis is unavailable


# ---------------------------------------------------------------------------
# Connection count helper (useful for monitoring endpoints)
# ---------------------------------------------------------------------------


def active_connection_count() -> int:
    """Return the number of live WebSocket connections in this process."""
    return len(_CONNECTIONS)
