#!/usr/bin/env python3
"""
Standalone narration test - demonstrates the narration generator
without requiring a running voice agent or MCP server.

Usage:
    python examples/test_narration.py
    python examples/test_narration.py --trace-file examples/example_traces.json
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.models import ReasoningStep
from mcp_server.narration_generator import NarrationGenerator
from mcp_server.trace_listener import TraceListener


async def demo_template_narration():
    """Demonstrate template-based narration generation."""
    print("=" * 60)
    print("🎤 Lock-In Narration Demo (Template-Based)")
    print("=" * 60)
    print()

    ng = NarrationGenerator()

    steps = [
        ReasoningStep(
            step_number=1,
            step_description="Planning authentication implementation for REST API using JWT tokens",
            thinking_type="planning",
            files_involved=["api/routes.py", "models/user.py"],
        ),
        ReasoningStep(
            step_number=2,
            step_description="Reading existing user model to check for password hashing",
            thinking_type="analyzing",
            files_involved=["models/user.py"],
        ),
        ReasoningStep(
            step_number=3,
            step_description="Creating JWT authentication middleware with token verification",
            thinking_type="implementing",
            files_involved=["middleware/auth.py"],
        ),
        ReasoningStep(
            step_number=4,
            step_description="Token expiry is set to 15 minutes, might be too short for dev",
            thinking_type="debugging",
            files_involved=["config/auth_config.py"],
        ),
        ReasoningStep(
            step_number=5,
            step_description="Writing tests for authentication flow including login and token refresh",
            thinking_type="testing",
            files_involved=["tests/test_auth.py"],
        ),
    ]

    previous = []
    for step in steps:
        narration = await ng.generate_narration(step, previous)
        icon = {
            "planning": "🧠",
            "analyzing": "🔍",
            "implementing": "⚡",
            "debugging": "🐛",
            "testing": "✅",
        }.get(step.thinking_type, "💬")

        print(f"  Step {step.step_number} [{step.thinking_type}] {icon}")
        print(f"  📝 {step.step_description}")
        print(f"  🔊 \"{narration}\"")
        print()

        previous.append(step)

    print(f"Total narrations generated: {ng.narration_count}")
    print()


async def demo_trace_file_narration(trace_file: str):
    """Demonstrate narration from a trace file."""
    print("=" * 60)
    print(f"🎤 Lock-In Narration Demo (From Trace File: {trace_file})")
    print("=" * 60)
    print()

    # Parse trace file
    listener = TraceListener()
    ng = NarrationGenerator()

    with open(trace_file) as f:
        traces = json.load(f)

    previous = []
    for trace_event in traces:
        step = listener.parse_trace_event(trace_event)
        if step is None:
            continue

        narration = await ng.generate_narration(step, previous)
        icon = {
            "planning": "🧠",
            "analyzing": "🔍",
            "implementing": "⚡",
            "debugging": "🐛",
            "testing": "✅",
        }.get(step.thinking_type, "💬")

        print(f"  Step {step.step_number} [{step.thinking_type}] {icon}")
        print(f"  📝 {step.step_description}")
        if step.files_involved:
            print(f"  📁 Files: {', '.join(step.files_involved)}")
        print(f"  🔊 \"{narration}\"")
        print()

        previous.append(step)

    print(f"Total steps parsed: {listener.step_count}")
    print(f"Total narrations generated: {ng.narration_count}")


async def main():
    """Run narration demos."""
    # Template demo
    await demo_template_narration()

    # Trace file demo (if file exists or specified)
    trace_file = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--trace-file" and len(sys.argv) > 2:
            trace_file = sys.argv[2]
    else:
        default_trace = Path(__file__).parent / "example_traces.json"
        if default_trace.exists():
            trace_file = str(default_trace)

    if trace_file:
        await demo_trace_file_narration(trace_file)
    else:
        print("💡 Tip: Run with --trace-file <path> to test with a trace file")
        print("   Example: python examples/test_narration.py --trace-file examples/example_traces.json")


if __name__ == "__main__":
    asyncio.run(main())
