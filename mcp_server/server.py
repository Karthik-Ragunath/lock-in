"""
Lock-In MCP Server - Expose reasoning trace tools for AI agent integration.

This server provides tools that AI agents call to stream reasoning traces
and handle user questions during code generation. It communicates with the voice
agent via WebSocket for real-time narration.

Built with mcp-use SDK for compatibility with ChatGPT, Claude, and other MCP clients.
"""

# CRITICAL: Suppress all stdout output before ANY imports for stdio mode
# The PyTorch/transformers warning goes to stdout and breaks JSON-RPC
import os
import sys

_transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
if _transport == "stdio":
    # Suppress ALL warnings and redirect stdout during imports
    import warnings
    warnings.filterwarnings("ignore")
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["PYTHONWARNINGS"] = "ignore"
    # Temporarily redirect stdout to stderr during imports
    _original_stdout = sys.stdout
    sys.stdout = sys.stderr

import asyncio
import json
import uuid
from datetime import datetime
from typing import Annotated, List, Optional

import websockets
from loguru import logger
from pydantic import Field

# Use mcp-use SDK
from mcp_use.server import MCPServer

# Restore stdout after imports (for stdio mode)
if _transport == "stdio":
    sys.stdout = _original_stdout

from .context_manager import ContextManager
from .models import ReasoningStep, WebSocketMessage
from .narration_generator import NarrationGenerator
from .widget_html import build_widget_html

# ---------------------------------------------------------------------------
# Globals shared across MCP tool calls
# ---------------------------------------------------------------------------
context_manager = ContextManager()
narration_generator = NarrationGenerator()  # Template-based by default

# Active WebSocket connection to the voice agent
_voice_ws: Optional[websockets.ClientConnection] = None
_voice_ws_lock = asyncio.Lock()

# Queue of pending user questions (filled by voice agent via WS)
_user_question_queue: asyncio.Queue = asyncio.Queue()

# Current session ID
_current_session_id: Optional[str] = None

# ---------------------------------------------------------------------------
# MCP Server (using mcp-use SDK)
# ---------------------------------------------------------------------------
# Use PORT (standard cloud env var) > MCP_SERVER_PORT > 8000
_server_port = int(os.environ.get("PORT", os.environ.get("MCP_SERVER_PORT", "8000")))

mcp_server = MCPServer(
    name="lock-in",
    version="1.0.0",
    instructions="Lock-In: Live voice narration of AI agent reasoning. "
                 "Call stream_reasoning_step() to narrate your thinking process.",
    host="0.0.0.0",
    port=_server_port,
    debug=True,  # Enable debug endpoints
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_voice_ws() -> Optional[websockets.ClientConnection]:
    """Get or establish WebSocket connection to the voice agent's MCP bridge."""
    global _voice_ws
    async with _voice_ws_lock:
        if _voice_ws is not None:
            try:
                await _voice_ws.ping()
                return _voice_ws
            except Exception:
                _voice_ws = None

        try:
            mcp_ws_port = os.environ.get("MCP_WS_PORT", "8766")
            _voice_ws = await websockets.connect(f"ws://localhost:{mcp_ws_port}")
            logger.info(f"Connected to voice agent MCP bridge on port {mcp_ws_port}")
            asyncio.create_task(_listen_for_questions())
            return _voice_ws
        except Exception as e:
            logger.warning(f"Could not connect to voice agent bridge: {e}")
            return None


async def _listen_for_questions():
    """Background task: listen for user questions from the voice agent."""
    global _voice_ws
    try:
        while _voice_ws is not None:
            try:
                raw = await _voice_ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "question":
                    question_text = msg.get("payload", {}).get("question", "")
                    if question_text:
                        logger.info(f"Received user question: {question_text[:60]}...")
                        await _user_question_queue.put(question_text)
            except websockets.ConnectionClosed:
                logger.info("Voice agent WebSocket closed")
                break
            except Exception as e:
                logger.debug(f"WS listener error: {e}")
                await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Question listener crashed: {e}")


async def _send_to_voice_agent(message: WebSocketMessage) -> bool:
    """Send a message to the voice agent over WebSocket."""
    ws = await _get_voice_ws()
    if ws is None:
        logger.debug("No voice agent connection, skipping send")
        return False
    try:
        await ws.send(message.model_dump_json())
        return True
    except Exception as e:
        logger.warning(f"Failed to send to voice agent: {e}")
        return False


def _ensure_session() -> str:
    """Ensure we have an active session, creating one if needed."""
    global _current_session_id
    if _current_session_id is None:
        _current_session_id = str(uuid.uuid4())
        context_manager.create_session(_current_session_id)
        logger.info(f"Auto-created session: {_current_session_id}")
    return _current_session_id


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp_server.tool(
    name="stream_reasoning_step",
    description="Stream a single reasoning step to the voice agent for narration. "
                "Called by AI agent during code generation to explain its thinking.",
)
async def stream_reasoning_step(
    step_number: Annotated[int, Field(description="Sequential step number")],
    step_description: Annotated[str, Field(description="Human-readable description of what you're doing")],
    thinking_type: Annotated[str, Field(description="One of: planning, analyzing, implementing, debugging, testing")],
    estimated_duration_seconds: Annotated[float, Field(description="Estimated time for this step")] = 0.0,
    files_involved: Annotated[List[str], Field(description="List of file paths being read/written")] = [],
) -> dict:
    """
    Stream a single reasoning step to the voice agent for narration.
    Called by Cursor agent during code generation to explain its thinking.

    Args:
        step_number: Sequential step number
        step_description: Human-readable description of what you're doing
        thinking_type: One of "planning", "analyzing", "implementing", "debugging", "testing"
        estimated_duration_seconds: Estimated time for this step
        files_involved: List of file paths being read/written

    Returns:
        Status dict with optional user question if the user asked something
    """
    session_id = _ensure_session()

    # Validate thinking_type
    valid_types = {"planning", "analyzing", "implementing", "debugging", "testing"}
    if thinking_type not in valid_types:
        thinking_type = "analyzing"

    # Create reasoning step
    step = ReasoningStep(
        step_number=step_number,
        step_description=step_description,
        thinking_type=thinking_type,
        estimated_duration_seconds=estimated_duration_seconds,
        files_involved=files_involved,
        timestamp=datetime.now(),
    )

    # Store in context
    context_manager.add_reasoning_step(session_id, step)
    logger.info(
        f"Step {step_number} [{thinking_type}]: {step_description[:80]}"
    )

    # Generate narration
    previous_steps = []
    session = context_manager.get_session(session_id)
    if session:
        previous_steps = session.reasoning_steps[:-1]  # All except current

    narration_text = await narration_generator.generate_narration(step, previous_steps)

    # Store narration text for rewind / summary
    context_manager.add_narration_text(session_id, step_number, narration_text, thinking_type)

    # Send narration to voice agent
    ws_msg = WebSocketMessage(
        type="narration",
        payload={
            "narration_text": narration_text,
            "step_number": step_number,
            "thinking_type": thinking_type,
            "description": step_description,
        },
        session_id=session_id,
    )
    sent = await _send_to_voice_agent(ws_msg)

    # Check for pending user questions (non-blocking)
    user_question = None
    try:
        user_question = _user_question_queue.get_nowait()
    except asyncio.QueueEmpty:
        pass

    result = {
        "status": "narrated" if sent else "narrated_locally",
        "narration": narration_text,
        "step_number": step_number,
    }

    if user_question:
        result["user_question"] = user_question
        logger.info(f"Passing user question back to agent: {user_question[:60]}...")

    return result


@mcp_server.tool(
    name="answer_user_question",
    description="Answer a user question about the current reasoning process. "
                "Uses the current trace context and conversation history.",
)
async def answer_user_question(
    question: Annotated[str, Field(description="The user's question text")],
    current_context: Annotated[dict, Field(description="Optional additional context from the agent")] = {},
) -> str:
    """
    Answer a user question about the current reasoning process.
    Uses the current trace context and conversation history to provide a helpful answer.

    Args:
        question: The user's question text
        current_context: Optional additional context from the agent

    Returns:
        Answer text that will be spoken to the user
    """
    session_id = _ensure_session()

    # Build rich context
    ctx = context_manager.get_context_for_question(session_id)
    ctx.update(current_context)

    logger.info(f"Answering question: {question[:80]}")

    # Generate answer using context
    answer = _build_contextual_answer(question, ctx)

    # Store in conversation history
    context_manager.add_conversation(session_id, question, answer)

    # Send answer to voice agent
    ws_msg = WebSocketMessage(
        type="answer",
        payload={
            "question": question,
            "answer": answer,
        },
        session_id=session_id,
    )
    await _send_to_voice_agent(ws_msg)

    return answer


@mcp_server.tool(
    name="get_conversation_history",
    description="Get the conversation history (questions and answers) for the current session.",
)
async def get_conversation_history() -> List[dict]:
    """
    Get the conversation history (questions and answers) for the current session.

    Returns:
        List of Q&A entries with timestamps
    """
    session_id = _ensure_session()
    history = context_manager.get_conversation_history(session_id)
    logger.info(f"Returning {len(history)} conversation entries")
    return history


# ---------------------------------------------------------------------------
# Audio Control Tools (MCP Apps widget + backend)
# ---------------------------------------------------------------------------
_WIDGET_RESOURCE_URI = "ui://lock-in/audio-controls.html"
_WIDGET_RESOURCE_URI_LEGACY = "ui://lock-in/audio-controls-legacy.html"


@mcp_server.resource(
    _WIDGET_RESOURCE_URI,
    name="audio-controls",
    description="Lock-In interactive audio control widget",
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": True,
            "widgetDescription": "Interactive audio controls for narration playback.",
        },
        "openai/widgetDescription": "Interactive audio controls for narration playback.",
        "openai/widgetPrefersBorder": True,
    },
)
async def audio_controls_resource() -> str:
    """Serve widget HTML content in MCP Apps resource format."""
    session_id = _ensure_session()
    status = context_manager.get_session_status(session_id)
    narrations = context_manager.get_narration_texts(session_id)
    html = build_widget_html(status=status, narrations=narrations)
    return html


@mcp_server.resource(
    _WIDGET_RESOURCE_URI_LEGACY,
    name="audio-controls-legacy",
    description="Lock-In interactive audio control widget (legacy host compatibility).",
    mime_type="text/html",
)
async def audio_controls_resource_legacy() -> str:
    """Serve widget HTML for hosts that still expect plain text/html."""
    session_id = _ensure_session()
    status = context_manager.get_session_status(session_id)
    narrations = context_manager.get_narration_texts(session_id)
    html = build_widget_html(status=status, narrations=narrations)
    return html


@mcp_server.tool(
    name="show_audio_controls",
    description="Display the Lock-In audio control widget with pause, rewind, "
                "and summary controls. Renders inline in the conversation.",
    meta={
        "ui": {"resourceUri": _WIDGET_RESOURCE_URI},
        # Backward-compatible flat key used by some hosts.
        "ui/resourceUri": _WIDGET_RESOURCE_URI,
        # ChatGPT/Apps-SDK style key used by some clients and bridges.
        "openai/outputTemplate": _WIDGET_RESOURCE_URI_LEGACY,
        "openai/toolInvocation/invoking": "Loading audio controls...",
        "openai/toolInvocation/invoked": "Audio controls ready.",
    },
    structured_output=False,
)
async def show_audio_controls() -> str:
    """
    Render the Lock-In audio control widget as an MCP App.

    The host fetches the ui:// resource and renders it in a sandboxed iframe
    with playback controls and narration timeline.
    """
    session_id = _ensure_session()
    status = context_manager.get_session_status(session_id)
    logger.info(f"Rendering audio control widget (session {session_id[:8]}...)")

    return (
        f"Audio controls widget displayed. "
        f"Session has {status.get('total_steps', 0)} steps, "
        f"{'paused' if status.get('paused') else 'playing'}."
    )


@mcp_server.tool(
    name="pause_narration",
    description="Pause voice narration playback. The agent keeps working but "
                "narration is silenced until resumed.",
)
async def pause_narration() -> dict:
    """Pause the voice agent's narration output."""
    session_id = _ensure_session()
    context_manager.set_paused(session_id, True)

    ws_msg = WebSocketMessage(
        type="pause",
        payload={},
        session_id=session_id,
    )
    sent = await _send_to_voice_agent(ws_msg)
    logger.info("Narration paused")

    return {
        "status": "paused",
        "paused": True,
        "voice_agent_notified": sent,
    }


@mcp_server.tool(
    name="resume_narration",
    description="Resume voice narration playback after a pause.",
)
async def resume_narration() -> dict:
    """Resume the voice agent's narration output."""
    session_id = _ensure_session()
    context_manager.set_paused(session_id, False)

    ws_msg = WebSocketMessage(
        type="resume",
        payload={},
        session_id=session_id,
    )
    sent = await _send_to_voice_agent(ws_msg)
    logger.info("Narration resumed")

    return {
        "status": "playing",
        "paused": False,
        "voice_agent_notified": sent,
    }


@mcp_server.tool(
    name="rewind_narration",
    description="Replay the last N narration steps through the voice agent. "
                "Useful when the user missed something.",
)
async def rewind_narration(
    steps_back: Annotated[int, Field(description="Number of steps to replay")] = 1,
) -> dict:
    """
    Replay recent narration steps by re-sending them to the voice agent.

    Args:
        steps_back: How many past narration steps to replay (default 1).

    Returns:
        Dict with the replayed narrations and current timeline.
    """
    session_id = _ensure_session()
    steps_back = max(1, min(steps_back, 10))
    narrations = context_manager.get_narration_texts(session_id, last_n=steps_back)

    replayed = []
    for n in narrations:
        ws_msg = WebSocketMessage(
            type="rewind",
            payload={
                "narration_text": n["narration_text"],
                "step_number": n["step_number"],
            },
            session_id=session_id,
        )
        sent = await _send_to_voice_agent(ws_msg)
        replayed.append({**n, "sent": sent})

    all_narrations = context_manager.get_narration_texts(session_id)
    logger.info(f"Rewound {len(replayed)} narration step(s)")

    return {
        "replayed_count": len(replayed),
        "replayed_narrations": replayed,
        "all_narrations": all_narrations,
    }


@mcp_server.tool(
    name="get_session_summary",
    description="Generate a plain-text summary of everything the agent has done "
                "in the current session, including all reasoning steps and files touched.",
)
async def get_session_summary() -> dict:
    """
    Generate a summary of the current coding session.

    Aggregates all reasoning steps, narrations, and files involved into a
    concise human-readable summary.
    """
    session_id = _ensure_session()
    data = context_manager.get_full_session_data(session_id)

    if not data:
        return {"summary": "No session data available yet."}

    summary = _build_session_summary(data)
    logger.info(f"Generated session summary ({len(summary)} chars)")

    return {
        "summary": summary,
        "total_steps": data.get("total_steps", 0),
        "files_involved": data.get("files_involved", []),
        "duration_seconds": data.get("duration_seconds", 0),
    }


def _build_session_summary(data: dict) -> str:
    """Build a human-readable session summary from full session data."""
    steps = data.get("steps", [])
    narrations = data.get("narrations", [])
    files = data.get("files_involved", [])
    duration = data.get("duration_seconds", 0)

    parts = []
    total = len(steps)
    mins = int(duration // 60)
    secs = int(duration % 60)

    parts.append(
        f"Session covered {total} step{'s' if total != 1 else ''} "
        f"over {mins}m {secs}s."
    )

    if files:
        parts.append(f"Files touched: {', '.join(files[:8])}" +
                      ("..." if len(files) > 8 else "") + ".")

    type_counts: dict[str, int] = {}
    for s in steps:
        t = s.get("type", "other")
        type_counts[t] = type_counts.get(t, 0) + 1
    if type_counts:
        breakdown = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        parts.append(f"Breakdown: {breakdown}.")

    if narrations:
        parts.append("\nKey narrations:")
        shown = narrations if len(narrations) <= 6 else (
            narrations[:3] + narrations[-3:]
        )
        for n in shown:
            text = n.get("text", "")[:120]
            parts.append(f"  [{n.get('type', '?')}] {text}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Answer generation (template-based fallback; LLM used when available)
# ---------------------------------------------------------------------------
def _build_contextual_answer(question: str, context: dict) -> str:
    """
    Build a contextual answer to a user question using available context.

    This is a template-based fallback. When an LLM client is configured on the
    narration generator, we delegate to it instead.
    """
    recent_steps = context.get("recent_steps", [])
    files = context.get("files_involved", [])
    current_step = context.get("current_step")

    # Build a helpful answer from context
    parts = []

    if current_step is not None and recent_steps:
        latest = recent_steps[-1] if recent_steps else None
        if latest:
            parts.append(
                f"Right now I'm on step {current_step}, "
                f"which is about {latest.get('description', 'the current task')}."
            )

    if files:
        parts.append(f"So far I've been working with: {', '.join(files[:5])}.")

    if not parts:
        parts.append("Let me think about that.")

    # Add question-specific context
    q_lower = question.lower()
    if any(w in q_lower for w in ["why", "reason", "explain"]):
        if recent_steps:
            step_descs = [s.get("description", "") for s in recent_steps[-3:]]
            parts.append(
                "Here's what I've been doing: "
                + "; ".join(s for s in step_descs if s)
                + "."
            )
    elif any(w in q_lower for w in ["what file", "which file"]):
        if files:
            parts.append(f"The main files involved are: {', '.join(files[:5])}.")
    elif any(w in q_lower for w in ["how long", "time", "when"]):
        total_steps = context.get("total_steps", 0)
        parts.append(f"We're at step {current_step or 0} out of {total_steps} so far.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------
def main():
    """Run the MCP server."""
    import warnings
    from pathlib import Path
    
    # Get the project directory for log file
    project_dir = Path(__file__).parent.parent
    log_file = project_dir / "lock-in.log"
    
    # Get transport mode early to decide logging behavior
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    
    if transport == "stdio":
        # In stdio mode, only log to file, not stderr (to keep output clean)
        logger.remove()
        logger.add(str(log_file), rotation="10 MB", level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(str(log_file), rotation="10 MB", level="DEBUG")
        logger.info("Starting Lock-In MCP server (mcp-use SDK)...")

    # Use PORT (standard cloud env var) > MCP_SERVER_PORT > 8000
    port = int(os.environ.get("PORT", os.environ.get("MCP_SERVER_PORT", "8000")))
    
    if transport == "stdio":
        # Run silently in stdio mode - no output except JSON-RPC
        mcp_server.run(transport="stdio")
    else:
        logger.info(f"Running in HTTP mode on port {port}")
        logger.info(f"  MCP endpoint: http://localhost:{port}/mcp")
        logger.info(f"  Inspector: http://localhost:{port}/inspector")
        logger.info(f"  OpenMCP: http://localhost:{port}/openmcp.json")
        
        # Run with mcp-use's built-in server
        mcp_server.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=port,
            debug=True,
        )


if __name__ == "__main__":
    main()
