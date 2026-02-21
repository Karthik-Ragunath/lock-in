"""Integration tests for Lock-In components working together."""

import asyncio
import json
from datetime import datetime

import pytest

from mcp_server.context_manager import ContextManager
from mcp_server.models import ReasoningStep, WebSocketMessage
from mcp_server.narration_generator import NarrationGenerator


# ---------------------------------------------------------------------------
# Integration: Context Manager + Narration Generator
# ---------------------------------------------------------------------------
class TestContextNarrationIntegration:
    """Test context manager and narration generator working together."""

    @pytest.mark.asyncio
    async def test_full_reasoning_flow(self):
        """Test a complete flow: create session, add steps, generate narration."""
        cm = ContextManager()
        ng = NarrationGenerator()

        # Create session
        session = cm.create_session("integration-test")
        assert session.is_active

        # Simulate a multi-step reasoning flow
        steps_data = [
            ("Planning the API authentication", "planning", ["api/routes.py"]),
            ("Reading the existing user model", "analyzing", ["models/user.py"]),
            ("Implementing JWT middleware", "implementing", ["middleware/auth.py"]),
            ("Found an issue with token expiry", "debugging", ["config.py"]),
            ("Testing the auth flow", "testing", ["tests/test_auth.py"]),
        ]

        narrations = []
        for i, (desc, thinking_type, files) in enumerate(steps_data, 1):
            step = ReasoningStep(
                step_number=i,
                step_description=desc,
                thinking_type=thinking_type,
                files_involved=files,
            )
            cm.add_reasoning_step("integration-test", step)

            # Generate narration with context
            previous = cm.get_session("integration-test").reasoning_steps[:-1]
            narration = await ng.generate_narration(step, previous)
            narrations.append(narration)

            assert len(narration) > 0
            assert len(narration) <= 250

        # Verify session state
        session = cm.get_session("integration-test")
        assert len(session.reasoning_steps) == 5
        assert session.current_step == 5
        assert len(narrations) == 5

    @pytest.mark.asyncio
    async def test_qa_during_reasoning(self):
        """Test Q&A interspersed with reasoning steps."""
        cm = ContextManager()
        ng = NarrationGenerator()

        cm.create_session("qa-test")

        # Step 1
        step1 = ReasoningStep(
            step_number=1,
            step_description="Planning JWT auth",
            thinking_type="planning",
            files_involved=["auth.py"],
        )
        cm.add_reasoning_step("qa-test", step1)
        await ng.generate_narration(step1)

        # User asks a question
        cm.add_conversation("qa-test", "Why JWT?", "JWT is stateless and scalable.")

        # Step 2
        step2 = ReasoningStep(
            step_number=2,
            step_description="Implementing token verification",
            thinking_type="implementing",
            files_involved=["auth.py", "middleware.py"],
        )
        cm.add_reasoning_step("qa-test", step2)
        await ng.generate_narration(step2, [step1])

        # Verify context includes conversation
        ctx = cm.get_context_for_question("qa-test")
        assert len(ctx["conversation_history"]) == 1
        assert ctx["conversation_history"][0]["question"] == "Why JWT?"
        assert len(ctx["recent_steps"]) == 2
        assert "auth.py" in ctx["files_involved"]


# ---------------------------------------------------------------------------
# Integration: WebSocket Message Serialization
# ---------------------------------------------------------------------------
class TestWebSocketMessageIntegration:
    """Test WebSocket message creation and serialization."""

    def test_narration_message_roundtrip(self):
        """Test creating, serializing, and deserializing a narration message."""
        msg = WebSocketMessage(
            type="narration",
            payload={
                "narration_text": "I'm checking the user model...",
                "step_number": 2,
                "thinking_type": "analyzing",
            },
            session_id="test-session",
        )

        # Serialize
        json_str = msg.model_dump_json()
        assert "narration" in json_str

        # Deserialize
        data = json.loads(json_str)
        assert data["type"] == "narration"
        assert data["payload"]["step_number"] == 2
        assert data["session_id"] == "test-session"

    def test_question_message_roundtrip(self):
        """Test question message serialization."""
        msg = WebSocketMessage(
            type="question",
            payload={"question": "Why use JWT?"},
            session_id="test-session",
        )

        json_str = msg.model_dump_json()
        data = json.loads(json_str)
        assert data["type"] == "question"
        assert data["payload"]["question"] == "Why use JWT?"


# ---------------------------------------------------------------------------
# Integration: Full Session Lifecycle
# ---------------------------------------------------------------------------
class TestSessionLifecycle:
    """Test complete session lifecycle."""

    def test_session_start_to_end(self):
        """Test creating, using, and ending a session."""
        cm = ContextManager()

        # Start
        session = cm.create_session("lifecycle-test")
        assert session.is_active
        assert cm.get_active_session_id() == "lifecycle-test"

        # Add steps
        for i in range(3):
            step = ReasoningStep(
                step_number=i + 1,
                step_description=f"Step {i + 1}",
                thinking_type="implementing",
            )
            cm.add_reasoning_step("lifecycle-test", step)

        # Add Q&A
        cm.add_conversation("lifecycle-test", "What?", "This.")

        # End
        ended = cm.end_session("lifecycle-test")
        assert ended.is_active is False
        assert cm.get_active_session_id() is None

        # Data persists after end
        history = cm.get_conversation_history("lifecycle-test")
        assert len(history) == 1

    def test_multiple_sessions(self):
        """Test managing multiple concurrent sessions."""
        cm = ContextManager()

        cm.create_session("s1")
        cm.create_session("s2")

        cm.add_reasoning_step("s1", ReasoningStep(
            step_number=1, step_description="S1 step", thinking_type="planning",
        ))
        cm.add_reasoning_step("s2", ReasoningStep(
            step_number=1, step_description="S2 step", thinking_type="analyzing",
        ))

        s1 = cm.get_session("s1")
        s2 = cm.get_session("s2")

        assert s1.reasoning_steps[0].step_description == "S1 step"
        assert s2.reasoning_steps[0].step_description == "S2 step"
