"""Tests for the Lock-In MCP server components."""

import asyncio
from datetime import datetime

import pytest

from mcp_server.context_manager import ContextManager
from mcp_server.models import (
    ConversationEntry,
    NarrationRequest,
    NarrationResponse,
    ReasoningStep,
    SessionContext,
    UserQuestion,
    WebSocketMessage,
)
from mcp_server.narration_generator import NarrationGenerator
from mcp_server.trace_listener import TraceListener


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------
class TestModels:
    """Test Pydantic data models."""

    def test_reasoning_step_creation(self):
        step = ReasoningStep(
            step_number=1,
            step_description="Planning the authentication flow",
            thinking_type="planning",
            estimated_duration_seconds=5.0,
            files_involved=["auth.py", "models.py"],
        )
        assert step.step_number == 1
        assert step.thinking_type == "planning"
        assert len(step.files_involved) == 2
        assert step.timestamp is not None

    def test_reasoning_step_defaults(self):
        step = ReasoningStep(
            step_number=1,
            step_description="Analyzing code",
            thinking_type="analyzing",
        )
        assert step.estimated_duration_seconds == 0.0
        assert step.files_involved == []

    def test_user_question_creation(self):
        q = UserQuestion(
            question="Why use JWT instead of sessions?",
            asked_at_step=3,
        )
        assert q.question == "Why use JWT instead of sessions?"
        assert q.asked_at_step == 3

    def test_session_context_creation(self):
        ctx = SessionContext(session_id="test-session")
        assert ctx.session_id == "test-session"
        assert ctx.reasoning_steps == []
        assert ctx.conversation_history == []
        assert ctx.current_step is None
        assert ctx.is_active is True

    def test_websocket_message_types(self):
        msg = WebSocketMessage(
            type="narration",
            payload={"narration_text": "Hello"},
            session_id="test",
        )
        assert msg.type == "narration"
        data = msg.model_dump_json()
        assert "narration" in data

    def test_conversation_entry(self):
        entry = ConversationEntry(
            question="What are you doing?",
            answer="I'm implementing auth.",
            asked_at_step=2,
        )
        assert entry.asked_at_step == 2

    def test_narration_request(self):
        step = ReasoningStep(
            step_number=1,
            step_description="test",
            thinking_type="planning",
        )
        req = NarrationRequest(step=step, session_id="s1")
        assert req.session_id == "s1"

    def test_narration_response(self):
        resp = NarrationResponse(
            narration_text="Working on auth...",
            step_number=1,
            thinking_type="implementing",
        )
        assert resp.narration_text == "Working on auth..."


# ---------------------------------------------------------------------------
# Context Manager Tests
# ---------------------------------------------------------------------------
class TestContextManager:
    """Test the ContextManager."""

    def test_create_session(self):
        cm = ContextManager()
        session = cm.create_session("test-1")
        assert session.session_id == "test-1"
        assert session.is_active is True

    def test_get_session(self):
        cm = ContextManager()
        cm.create_session("test-1")
        session = cm.get_session("test-1")
        assert session is not None
        assert session.session_id == "test-1"

    def test_get_nonexistent_session(self):
        cm = ContextManager()
        session = cm.get_session("nope")
        assert session is None

    def test_get_or_create_session(self):
        cm = ContextManager()
        s1 = cm.get_or_create_session("test-1")
        s2 = cm.get_or_create_session("test-1")
        assert s1.session_id == s2.session_id

    def test_add_reasoning_step(self):
        cm = ContextManager()
        cm.create_session("test-1")
        step = ReasoningStep(
            step_number=1,
            step_description="Planning",
            thinking_type="planning",
        )
        cm.add_reasoning_step("test-1", step)
        session = cm.get_session("test-1")
        assert len(session.reasoning_steps) == 1
        assert session.current_step == 1

    def test_add_conversation(self):
        cm = ContextManager()
        cm.create_session("test-1")
        cm.add_conversation("test-1", "Why JWT?", "Because stateless auth.")
        history = cm.get_conversation_history("test-1")
        assert len(history) == 1
        assert history[0]["question"] == "Why JWT?"

    def test_get_context_for_question(self):
        cm = ContextManager()
        cm.create_session("test-1")

        for i in range(7):
            step = ReasoningStep(
                step_number=i + 1,
                step_description=f"Step {i + 1}",
                thinking_type="implementing",
                files_involved=[f"file{i}.py"],
            )
            cm.add_reasoning_step("test-1", step)

        ctx = cm.get_context_for_question("test-1")
        assert ctx["current_step"] == 7
        assert ctx["total_steps"] == 7
        # Should only have last 5 steps
        assert len(ctx["recent_steps"]) == 5
        # Should have all unique files
        assert len(ctx["files_involved"]) == 7

    def test_end_session(self):
        cm = ContextManager()
        cm.create_session("test-1")
        session = cm.end_session("test-1")
        assert session.is_active is False

    def test_get_active_session_id(self):
        cm = ContextManager()
        cm.create_session("s1")
        cm.create_session("s2")
        active = cm.get_active_session_id()
        assert active == "s2"

        cm.end_session("s2")
        active = cm.get_active_session_id()
        assert active == "s1"


# ---------------------------------------------------------------------------
# Narration Generator Tests
# ---------------------------------------------------------------------------
class TestNarrationGenerator:
    """Test template-based narration generation."""

    @pytest.mark.asyncio
    async def test_generate_planning_narration(self):
        ng = NarrationGenerator()
        step = ReasoningStep(
            step_number=1,
            step_description="Setting up the authentication middleware",
            thinking_type="planning",
            files_involved=["auth.py"],
        )
        narration = await ng.generate_narration(step)
        assert len(narration) > 0
        assert len(narration) <= 250

    @pytest.mark.asyncio
    async def test_generate_analyzing_narration(self):
        ng = NarrationGenerator()
        step = ReasoningStep(
            step_number=2,
            step_description="Reading the user model",
            thinking_type="analyzing",
            files_involved=["models/user.py"],
        )
        narration = await ng.generate_narration(step)
        assert len(narration) > 0

    @pytest.mark.asyncio
    async def test_generate_implementing_narration(self):
        ng = NarrationGenerator()
        step = ReasoningStep(
            step_number=3,
            step_description="Writing JWT verification logic",
            thinking_type="implementing",
            files_involved=["auth_middleware.py"],
        )
        narration = await ng.generate_narration(step)
        assert "auth_middleware.py" in narration or "Writing" in narration or "implement" in narration.lower()

    @pytest.mark.asyncio
    async def test_generate_debugging_narration(self):
        ng = NarrationGenerator()
        step = ReasoningStep(
            step_number=4,
            step_description="Token expiry is too short",
            thinking_type="debugging",
        )
        narration = await ng.generate_narration(step)
        assert len(narration) > 0

    @pytest.mark.asyncio
    async def test_narration_with_previous_steps(self):
        ng = NarrationGenerator()
        prev = [
            ReasoningStep(
                step_number=1,
                step_description="Planning auth",
                thinking_type="planning",
            ),
        ]
        step = ReasoningStep(
            step_number=2,
            step_description="Checking files",
            thinking_type="analyzing",
        )
        narration = await ng.generate_narration(step, prev)
        assert len(narration) > 0

    @pytest.mark.asyncio
    async def test_narration_count_increments(self):
        ng = NarrationGenerator()
        step = ReasoningStep(
            step_number=1,
            step_description="Test",
            thinking_type="planning",
        )
        await ng.generate_narration(step)
        await ng.generate_narration(step)
        assert ng.narration_count == 2


# ---------------------------------------------------------------------------
# Trace Listener Tests
# ---------------------------------------------------------------------------
class TestTraceListener:
    """Test the TraceListener."""

    def test_parse_trace_event_tool_call(self):
        listener = TraceListener()
        event = {
            "type": "tool_call",
            "description": "Calling search function",
            "file": "utils.py",
        }
        step = listener.parse_trace_event(event)
        assert step is not None
        assert step.thinking_type == "implementing"
        assert "utils.py" in step.files_involved

    def test_parse_trace_event_file_read(self):
        listener = TraceListener()
        event = {
            "type": "file_read",
            "file": "models/user.py",
        }
        step = listener.parse_trace_event(event)
        assert step is not None
        assert step.thinking_type == "analyzing"

    def test_parse_trace_event_plan(self):
        listener = TraceListener()
        event = {
            "type": "plan",
            "description": "Planning authentication approach",
        }
        step = listener.parse_trace_event(event)
        assert step is not None
        assert step.thinking_type == "planning"

    def test_parse_trace_event_invalid(self):
        listener = TraceListener()
        step = listener.parse_trace_event({})
        assert step is None

    def test_parse_trace_event_not_dict(self):
        listener = TraceListener()
        step = listener.parse_trace_event("not a dict")
        assert step is None

    def test_extract_files(self):
        listener = TraceListener()
        event = {
            "file": "a.py",
            "args": {"target_file": "b.py"},
        }
        files = listener._extract_files(event)
        assert "a.py" in files
        assert "b.py" in files

    def test_step_counter_increments(self):
        listener = TraceListener()
        e1 = {"type": "plan", "description": "Step 1"}
        e2 = {"type": "plan", "description": "Step 2"}
        s1 = listener.parse_trace_event(e1)
        s2 = listener.parse_trace_event(e2)
        assert s1.step_number == 1
        assert s2.step_number == 2
        assert listener.step_count == 2

    def test_parse_plain_text(self):
        listener = TraceListener()
        step = listener._parse_plain_text("Reading the config file")
        assert step is not None
        assert step.thinking_type == "analyzing"

    def test_parse_plain_text_implementing(self):
        listener = TraceListener()
        step = listener._parse_plain_text("Writing the new module")
        assert step is not None
        assert step.thinking_type == "implementing"

    def test_parse_plain_text_empty(self):
        listener = TraceListener()
        step = listener._parse_plain_text("")
        assert step is None

    def test_parse_plain_text_comment(self):
        listener = TraceListener()
        step = listener._parse_plain_text("# This is a comment")
        assert step is None
