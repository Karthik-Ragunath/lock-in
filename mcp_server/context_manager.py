"""Context Manager - Track session state for intelligent Q&A."""

import threading
from datetime import datetime
from typing import Dict, List, Optional, Set

from loguru import logger

from .models import ConversationEntry, NarrationText, ReasoningStep, SessionContext


class ContextManager:
    """
    Thread-safe manager for coding session context.
    
    Keeps track of reasoning steps, conversation history, and session state
    to provide rich context for answering user questions.
    """

    def __init__(self):
        self.sessions: Dict[str, SessionContext] = {}
        self._lock = threading.Lock()
        logger.info("ContextManager initialized")

    def create_session(self, session_id: str) -> SessionContext:
        """Create a new coding session."""
        with self._lock:
            context = SessionContext(
                session_id=session_id,
                reasoning_steps=[],
                conversation_history=[],
                current_step=None,
                started_at=datetime.now(),
            )
            self.sessions[session_id] = context
            logger.info(f"Session created: {session_id}")
            return context

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get a session by ID."""
        with self._lock:
            return self.sessions.get(session_id)

    def get_or_create_session(self, session_id: str) -> SessionContext:
        """Get existing session or create a new one."""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)
        return session

    def add_reasoning_step(self, session_id: str, step: ReasoningStep) -> None:
        """Add a reasoning step to the session."""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].reasoning_steps.append(step)
                self.sessions[session_id].current_step = step.step_number
                logger.info(
                    f"[{session_id}] Step {step.step_number}: "
                    f"{step.thinking_type} - {step.step_description[:50]}..."
                )
            else:
                logger.warning(f"Session not found: {session_id}")

    def add_conversation(
        self, session_id: str, question: str, answer: str
    ) -> None:
        """Add a Q&A entry to conversation history."""
        with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                entry = ConversationEntry(
                    question=question,
                    answer=answer,
                    asked_at_step=session.current_step,
                    timestamp=datetime.now(),
                )
                session.conversation_history.append(entry)
                logger.info(
                    f"[{session_id}] Q&A added at step {session.current_step}: "
                    f"Q={question[:40]}..."
                )
            else:
                logger.warning(f"Session not found: {session_id}")

    def add_narration_text(
        self, session_id: str, step_number: int, text: str, thinking_type: str = "analyzing"
    ) -> None:
        """Store a generated narration text for the session."""
        with self._lock:
            if session_id in self.sessions:
                entry = NarrationText(
                    step_number=step_number,
                    narration_text=text,
                    thinking_type=thinking_type,
                    timestamp=datetime.now(),
                )
                self.sessions[session_id].narration_texts.append(entry)
            else:
                logger.warning(f"Session not found: {session_id}")

    def get_narration_texts(self, session_id: str, last_n: Optional[int] = None) -> List[dict]:
        """Get narration texts, optionally limited to the last N entries."""
        with self._lock:
            if session_id not in self.sessions:
                return []
            texts = self.sessions[session_id].narration_texts
            if last_n is not None:
                texts = texts[-last_n:]
            return [
                {
                    "step_number": t.step_number,
                    "narration_text": t.narration_text,
                    "thinking_type": t.thinking_type,
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in texts
            ]

    def set_paused(self, session_id: str, paused: bool) -> None:
        """Set the pause state for a session."""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].is_paused = paused

    def get_session_status(self, session_id: str) -> dict:
        """Get a status snapshot of the session for the widget."""
        with self._lock:
            if session_id not in self.sessions:
                return {"active": False}
            session = self.sessions[session_id]
            return {
                "active": session.is_active,
                "paused": session.is_paused,
                "current_step": session.current_step,
                "total_steps": len(session.reasoning_steps),
                "total_narrations": len(session.narration_texts),
                "duration_seconds": (datetime.now() - session.started_at).total_seconds(),
            }

    def get_full_session_data(self, session_id: str) -> dict:
        """Get all steps and narrations for summary generation."""
        with self._lock:
            if session_id not in self.sessions:
                return {}
            session = self.sessions[session_id]

            all_files: Set[str] = set()
            for step in session.reasoning_steps:
                for f in step.files_involved:
                    all_files.add(f)

            return {
                "session_id": session_id,
                "current_step": session.current_step,
                "total_steps": len(session.reasoning_steps),
                "duration_seconds": (datetime.now() - session.started_at).total_seconds(),
                "files_involved": sorted(all_files),
                "steps": [
                    {
                        "step_number": s.step_number,
                        "description": s.step_description,
                        "type": s.thinking_type,
                        "files": s.files_involved,
                    }
                    for s in session.reasoning_steps
                ],
                "narrations": [
                    {
                        "step_number": n.step_number,
                        "text": n.narration_text,
                        "type": n.thinking_type,
                    }
                    for n in session.narration_texts
                ],
            }

    def get_context_for_question(self, session_id: str) -> dict:
        """
        Build context dictionary for answering user questions.
        
        Includes recent reasoning steps, conversation history, and file info.
        """
        with self._lock:
            if session_id not in self.sessions:
                return {}

            session = self.sessions[session_id]

            # Collect all unique files involved
            all_files: Set[str] = set()
            for step in session.reasoning_steps:
                for f in step.files_involved:
                    all_files.add(f)

            # Get recent steps (last 5)
            recent_steps = session.reasoning_steps[-5:]
            recent_steps_data = [
                {
                    "step_number": s.step_number,
                    "description": s.step_description,
                    "type": s.thinking_type,
                    "files": s.files_involved,
                }
                for s in recent_steps
            ]

            # Get recent conversation (last 3)
            recent_convo = session.conversation_history[-3:]
            recent_convo_data = [
                {
                    "question": c.question,
                    "answer": c.answer,
                    "at_step": c.asked_at_step,
                }
                for c in recent_convo
            ]

            return {
                "session_id": session_id,
                "current_step": session.current_step,
                "total_steps": len(session.reasoning_steps),
                "recent_steps": recent_steps_data,
                "conversation_history": recent_convo_data,
                "files_involved": sorted(all_files),
                "session_duration_seconds": (
                    datetime.now() - session.started_at
                ).total_seconds(),
            }

    def get_conversation_history(self, session_id: str) -> List[dict]:
        """Get full conversation history for a session."""
        with self._lock:
            if session_id not in self.sessions:
                return []

            return [
                {
                    "question": c.question,
                    "answer": c.answer,
                    "asked_at_step": c.asked_at_step,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in self.sessions[session_id].conversation_history
            ]

    def end_session(self, session_id: str) -> Optional[SessionContext]:
        """Mark a session as inactive."""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].is_active = False
                logger.info(f"Session ended: {session_id}")
                return self.sessions[session_id]
            return None

    def get_active_session_id(self) -> Optional[str]:
        """Get the most recent active session ID."""
        with self._lock:
            for sid, session in reversed(list(self.sessions.items())):
                if session.is_active:
                    return sid
            return None
