"""Trace Listener - Parse Cursor agent traces into reasoning steps."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

import aiofiles
from loguru import logger

from .models import ReasoningStep


# Mapping of trace event types to our thinking types
TRACE_TYPE_MAP = {
    "tool_call": "implementing",
    "file_read": "analyzing",
    "file_write": "implementing",
    "file_edit": "implementing",
    "search": "analyzing",
    "plan": "planning",
    "think": "planning",
    "debug": "debugging",
    "test": "testing",
    "error": "debugging",
    "lint": "testing",
    "terminal": "implementing",
    "grep": "analyzing",
    "codebase_search": "analyzing",
}

# Human-readable descriptions for trace event types
TRACE_DESCRIPTIONS = {
    "tool_call": "Using a tool to {details}",
    "file_read": "Reading file {file}",
    "file_write": "Creating file {file}",
    "file_edit": "Editing file {file}",
    "search": "Searching for {details}",
    "plan": "Planning: {details}",
    "think": "Thinking about {details}",
    "debug": "Debugging: {details}",
    "test": "Running tests: {details}",
    "error": "Encountered an error: {details}",
    "lint": "Checking code quality in {file}",
    "terminal": "Running command: {details}",
    "grep": "Searching codebase for {details}",
    "codebase_search": "Searching codebase: {details}",
}


class TraceListener:
    """
    Listen to Cursor's agent-trace output and convert to ReasoningStep format.
    
    Supports both file-based and stdio trace input for real-time streaming.
    """

    def __init__(self, trace_source: str = "stdio"):
        """
        Initialize with trace source.
        
        Args:
            trace_source: Path to trace file, or "stdio" for standard input.
        """
        self.trace_source = trace_source
        self._step_counter = 0
        self._running = False
        logger.info(f"TraceListener initialized with source: {trace_source}")

    async def listen(self) -> AsyncGenerator[ReasoningStep, None]:
        """
        Stream reasoning steps as they happen.
        
        Yields ReasoningStep objects in real-time from the trace source.
        """
        self._running = True
        logger.info("TraceListener started listening")

        try:
            if self.trace_source == "stdio":
                async for step in self._listen_stdio():
                    yield step
            else:
                async for step in self._listen_file():
                    yield step
        except asyncio.CancelledError:
            logger.info("TraceListener cancelled")
        except Exception as e:
            logger.error(f"TraceListener error: {e}")
        finally:
            self._running = False
            logger.info("TraceListener stopped")

    async def _listen_file(self) -> AsyncGenerator[ReasoningStep, None]:
        """Listen to a file-based trace source (watches for new lines)."""
        path = Path(self.trace_source)

        if not path.exists():
            logger.warning(f"Trace file not found: {path}. Waiting for creation...")
            while not path.exists() and self._running:
                await asyncio.sleep(0.5)

        if not self._running:
            return

        async with aiofiles.open(str(path), mode="r") as f:
            # Read existing content first
            content = await f.read()
            for line in content.strip().split("\n"):
                if line.strip():
                    step = self._parse_line(line)
                    if step:
                        yield step

            # Then tail for new content
            while self._running:
                line = await f.readline()
                if line:
                    step = self._parse_line(line.strip())
                    if step:
                        yield step
                else:
                    await asyncio.sleep(0.1)

    async def _listen_stdio(self) -> AsyncGenerator[ReasoningStep, None]:
        """Listen to standard input for trace events."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        try:
            await loop.connect_read_pipe(lambda: protocol, __import__("sys").stdin)
        except (OSError, NotImplementedError):
            logger.warning("Cannot connect to stdin, falling back to queue-based input")
            return

        while self._running:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=1.0)
                if not line:
                    break
                decoded = line.decode("utf-8").strip()
                if decoded:
                    step = self._parse_line(decoded)
                    if step:
                        yield step
            except asyncio.TimeoutError:
                continue

    def _parse_line(self, line: str) -> Optional[ReasoningStep]:
        """Parse a single line of trace output."""
        try:
            event = json.loads(line)
            return self.parse_trace_event(event)
        except json.JSONDecodeError:
            # Not JSON - try to parse as plain text
            return self._parse_plain_text(line)
        except Exception as e:
            logger.debug(f"Failed to parse trace line: {e}")
            return None

    def parse_trace_event(self, event: dict) -> Optional[ReasoningStep]:
        """
        Convert a raw trace event dictionary to a ReasoningStep.
        
        Handles various event formats from Cursor agent traces.
        """
        if not isinstance(event, dict):
            return None

        # Extract event type
        event_type = event.get("type", event.get("event", event.get("action", "")))
        if not event_type:
            return None

        # Map to our thinking type
        thinking_type = TRACE_TYPE_MAP.get(
            event_type.lower(), "analyzing"
        )

        # Extract files involved
        files = self._extract_files(event)

        # Generate description
        description = self._generate_description(event_type, event, files)

        # Extract or estimate duration
        duration = event.get("duration", event.get("estimated_duration", 0.0))

        self._step_counter += 1

        step = ReasoningStep(
            step_number=self._step_counter,
            step_description=description,
            thinking_type=thinking_type,
            estimated_duration_seconds=float(duration),
            files_involved=files,
            timestamp=datetime.now(),
        )

        logger.debug(f"Parsed step {step.step_number}: {step.thinking_type} - {description[:60]}")
        return step

    def _extract_files(self, event: dict) -> list:
        """Extract file paths from a trace event."""
        files = []

        # Check common field names for file paths
        for key in ["file", "path", "filepath", "target_file", "file_path"]:
            if key in event:
                val = event[key]
                if isinstance(val, str):
                    files.append(val)
                elif isinstance(val, list):
                    files.extend([f for f in val if isinstance(f, str)])

        # Check for files_involved field
        if "files_involved" in event:
            fi = event["files_involved"]
            if isinstance(fi, list):
                files.extend([f for f in fi if isinstance(f, str)])

        # Check nested args/parameters
        for key in ["args", "parameters", "params"]:
            if key in event and isinstance(event[key], dict):
                nested_files = self._extract_files(event[key])
                files.extend(nested_files)

        return list(set(files))  # Deduplicate

    def _generate_description(
        self, event_type: str, event: dict, files: list
    ) -> str:
        """Generate a human-readable description from a trace event."""
        # Try to get description from event
        for key in ["description", "message", "summary", "text", "content"]:
            if key in event and isinstance(event[key], str):
                return event[key]

        # Use template-based description
        template = TRACE_DESCRIPTIONS.get(
            event_type.lower(),
            "Working on: {details}",
        )

        details = event.get("details", event.get("query", event.get("command", event_type)))
        if isinstance(details, dict):
            details = json.dumps(details)[:100]
        elif not isinstance(details, str):
            details = str(details)[:100]

        file_str = files[0] if files else "the codebase"

        return template.format(details=details, file=file_str)

    def _parse_plain_text(self, text: str) -> Optional[ReasoningStep]:
        """Parse plain text trace output (non-JSON)."""
        if not text or text.startswith("#"):
            return None

        # Detect thinking type from keywords
        text_lower = text.lower()
        if any(w in text_lower for w in ["plan", "thinking", "approach", "strategy"]):
            thinking_type = "planning"
        elif any(w in text_lower for w in ["read", "check", "look", "search", "find", "analyz"]):
            thinking_type = "analyzing"
        elif any(w in text_lower for w in ["writ", "creat", "implement", "add", "edit", "modify"]):
            thinking_type = "implementing"
        elif any(w in text_lower for w in ["debug", "fix", "error", "bug", "issue"]):
            thinking_type = "debugging"
        elif any(w in text_lower for w in ["test", "verify", "assert", "check"]):
            thinking_type = "testing"
        else:
            thinking_type = "analyzing"

        self._step_counter += 1

        return ReasoningStep(
            step_number=self._step_counter,
            step_description=text[:200],
            thinking_type=thinking_type,
            estimated_duration_seconds=0.0,
            files_involved=[],
            timestamp=datetime.now(),
        )

    def stop(self) -> None:
        """Stop listening for trace events."""
        self._running = False
        logger.info("TraceListener stop requested")

    @property
    def is_running(self) -> bool:
        """Whether the listener is actively running."""
        return self._running

    @property
    def step_count(self) -> int:
        """Number of steps parsed so far."""
        return self._step_counter
