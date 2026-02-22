"""Pydantic data models for Lock-In MCP Server."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ReasoningStep(BaseModel):
    """Represents a single reasoning step from the Cursor agent."""

    step_number: int = Field(..., description="Sequential step number")
    step_description: str = Field(..., description="Human-readable description of the step")
    thinking_type: Literal["planning", "analyzing", "implementing", "debugging", "testing"] = Field(
        ..., description="Category of reasoning"
    )
    estimated_duration_seconds: float = Field(
        0.0, description="Estimated time for this step"
    )
    files_involved: List[str] = Field(
        default_factory=list, description="Files being read/written in this step"
    )
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class UserQuestion(BaseModel):
    """A question asked by the user during code generation."""

    question: str = Field(..., description="The user's question text")
    asked_at_step: int = Field(..., description="Step number when question was asked")
    timestamp: datetime = Field(default_factory=datetime.now)


class ConversationEntry(BaseModel):
    """A single Q&A entry in conversation history."""

    question: str
    answer: str
    asked_at_step: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class NarrationText(BaseModel):
    """A single narration text generated for a reasoning step."""

    step_number: int
    narration_text: str
    thinking_type: str = "analyzing"
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class SessionContext(BaseModel):
    """Full context for an active coding session."""

    session_id: str = Field(..., description="Unique session identifier")
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list)
    narration_texts: List[NarrationText] = Field(default_factory=list)
    conversation_history: List[ConversationEntry] = Field(default_factory=list)
    current_step: Optional[int] = Field(None, description="Current step number")
    is_paused: bool = Field(False, description="Whether narration is currently paused")
    started_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(True, description="Whether the session is still active")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class NarrationRequest(BaseModel):
    """Request to generate narration for a reasoning step."""

    step: ReasoningStep
    previous_steps: List[ReasoningStep] = Field(default_factory=list)
    session_id: str


class NarrationResponse(BaseModel):
    """Response containing generated narration text."""

    narration_text: str
    step_number: int
    thinking_type: str
    duration_estimate_seconds: float = Field(
        0.0, description="Estimated speech duration"
    )


class WebSocketMessage(BaseModel):
    """Message format for WebSocket communication between MCP server and voice agent."""

    type: Literal[
        "narration",
        "question",
        "answer",
        "status",
        "pause",
        "resume",
        "rewind",
        "session_start",
        "session_end",
        "error",
    ]
    payload: dict = Field(default_factory=dict)
    session_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
