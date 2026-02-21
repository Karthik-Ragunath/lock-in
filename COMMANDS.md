# 🎮 Lock-In Commands Reference

Quick reference for all Lock-In commands and scripts.

## Run Script (`scripts/run.sh`)

The main entry point for running Lock-In components.

```bash
./scripts/run.sh <command>
```

### Available Commands

| Command | Description |
|---------|-------------|
| `mcp-http` | Start MCP server in HTTP mode (for MCP Inspector, ChatGPT, Claude) |
| `mcp` | Start MCP server in stdio mode (for Cursor IDE) |
| `voice` | Start the voice agent only |
| `client` | Start the audio client (browser-based) |
| `both` | Start MCP server (background) + voice agent (foreground) |
| `all` | Start everything (voice + MCP + audio client) |
| `test` | Run the full test suite |
| `test-coverage` | Run tests with coverage report |
| `demo` | Run the narration demo script |
| `lint` | Run code linters (ruff) |
| `help` | Show available commands |

### Examples

```bash
# Test MCP server with MCP Inspector (recommended first step)
./scripts/run.sh mcp-http
# Then in another terminal:
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp

# Start everything for full voice experience
./scripts/run.sh all

# Run only the MCP server (HTTP mode for testing)
./scripts/run.sh mcp-http

# Run only the MCP server (stdio mode for Cursor)
./scripts/run.sh mcp

# Run only the voice agent
./scripts/run.sh voice

# Run the audio client
./scripts/run.sh client

# Run tests
./scripts/run.sh test

# Run narration demo
./scripts/run.sh demo
```

## Setup Script (`scripts/setup.sh`)

Run once to initialize the project:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This creates the virtual environment, installs dependencies (including mcp-use), and sets up the `.env` file.

## MCP Server Endpoints (HTTP Mode)

When running in HTTP mode (`./scripts/run.sh mcp-http`), these endpoints are available:

| Endpoint | Description |
|----------|-------------|
| `http://localhost:8000/mcp` | MCP protocol endpoint (Streamable HTTP) |
| `http://localhost:8000/openmcp.json` | OpenMCP schema (tools, resources, prompts) |
| `http://localhost:8000/inspector` | Built-in inspector UI |
| `http://localhost:8000/docs` | API documentation |

### Test with curl

```bash
# Get server schema
curl http://localhost:8000/openmcp.json | jq .tools

# Test MCP initialize
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

### Test with MCP Inspector

```bash
# Local inspector (recommended)
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp

# Or use ngrok for remote access
ngrok http 8000
# Then use the ngrok URL in the web inspector at https://inspector.mcp-use.com
```

## MCP Server Tools

These tools are exposed by the MCP server and can be called by Cursor's agent or any MCP client.

### `stream_reasoning_step`

Stream a reasoning step from the AI agent to the voice agent for narration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `step_number` | int | Yes | Sequential step number |
| `step_description` | string | Yes | Human-readable description of what you're doing |
| `thinking_type` | string | Yes | One of: `planning`, `analyzing`, `implementing`, `debugging`, `testing` |
| `estimated_duration_seconds` | float | No | Estimated time for this step (default: `0.0`) |
| `files_involved` | list[str] | No | Files being worked on (default: `[]`) |

**Example call:**

```json
{
  "step_number": 1,
  "step_description": "I'll start by creating the authentication module...",
  "thinking_type": "planning",
  "files_involved": ["auth.py", "models.py"]
}
```

**Returns:** Status dict with narration text and optional user question.

---

### `answer_user_question`

Answer a question asked by the user through the voice interface.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | The user's question text |
| `current_context` | dict | No | Additional context from the agent |

**Example call:**

```json
{
  "question": "Why are you using a factory pattern here?"
}
```

**Returns:** The generated answer text that was spoken to the user.

---

### `get_conversation_history`

Retrieve the Q&A conversation history for the current session.

**Parameters:** None

**Returns:** JSON array of conversation entries with question/answer pairs and timestamps.

## Cursor MCP Configuration

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lock-in": {
      "command": "/path/to/lock-in/venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/lock-in",
      "env": {
        "PYTHONPATH": "/path/to/lock-in",
        "MCP_TRANSPORT": "stdio",
        "CARTESIA_API_KEY": "your_cartesia_key",
        "ANTHROPIC_API_KEY": "your_anthropic_key"
      }
    }
  }
}
```

**Important:** Set `MCP_TRANSPORT=stdio` for Cursor integration.

## Python Module Commands

### Run Components Directly

```bash
# Activate virtual environment
source venv/bin/activate

# Run the MCP server (HTTP mode)
MCP_TRANSPORT=streamable-http python -m mcp_server.server

# Run the MCP server (stdio mode)
MCP_TRANSPORT=stdio python -m mcp_server.server

# Run the voice agent
python -m voice_agent.agent
```

### Run Tests Directly

```bash
source venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_mcp_server.py -v
python -m pytest tests/test_voice_agent.py -v
python -m pytest tests/test_integration.py -v

# Run with coverage
python -m pytest tests/ -v --cov=mcp_server --cov=voice_agent --cov-report=term-missing

# Run specific test by name
python -m pytest tests/ -k "test_reasoning_step_creation" -v
```

### Run Examples Directly

```bash
source venv/bin/activate

# Narration demo
python examples/test_narration.py
```

## Environment Variables

Set these in `.env` (see `.env.example` for template):

### Required

| Variable | Description |
|----------|-------------|
| `CARTESIA_API_KEY` | Your Cartesia API key for TTS/STT |
| `ANTHROPIC_API_KEY` | Your Anthropic API key for LLM (voice agent Q&A) |

### MCP Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `streamable-http` | Transport mode: `streamable-http` or `stdio` |
| `MCP_SERVER_PORT` | `8000` | HTTP server port (HTTP mode only) |

### Voice Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CARTESIA_VOICE_ID` | `a0e99841-...` | Cartesia voice to use |
| `TTS_MODEL` | `sonic-3` | TTS model |
| `STT_MODEL` | `ink-whisper` | STT model |
| `TTS_SAMPLE_RATE` | `24000` | TTS audio sample rate |
| `STT_SAMPLE_RATE` | `16000` | STT audio sample rate |

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WS_HOST` | `0.0.0.0` | WebSocket bind address |
| `WS_PORT` | `8765` | Voice agent WebSocket port |
| `MCP_WS_PORT` | `8766` | MCP ↔ Voice agent WebSocket port |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model for Q&A |
| `LLM_TEMPERATURE` | `0.7` | Temperature for LLM generation |
| `MAX_NARRATION_LENGTH` | `150` | Max words per narration |

### Narration Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NARRATION_SPEED` | `1.1` | Speech speed multiplier |
| `ENABLE_INTERRUPTIONS` | `true` | Allow user interruptions |
| `QUESTION_DETECTION_CONFIDENCE` | `0.7` | STT confidence threshold for questions |

### Logging and Debug

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | `lock-in.log` | Log file path |
| `DEBUG_MODE` | `false` | Enable debug output |
| `SAVE_TRACES` | `true` | Save agent trace data |
| `TRACES_DIR` | `./traces` | Directory for trace files |

## Troubleshooting

### Kill processes on specific ports

```bash
# Kill MCP server (HTTP mode)
lsof -ti:8000 | xargs kill 2>/dev/null

# Kill voice agent
lsof -ti:8765 | xargs kill 2>/dev/null

# Kill MCP WebSocket bridge
lsof -ti:8766 | xargs kill 2>/dev/null

# Kill audio client
lsof -ti:8080 | xargs kill 2>/dev/null

# Kill all at once
lsof -ti:8000 -ti:8765 -ti:8766 -ti:8080 | xargs kill 2>/dev/null; echo "done"
```

### Check if ports are in use

```bash
lsof -i :8000  # MCP HTTP
lsof -i :8765  # Voice agent
lsof -i :8766  # MCP WebSocket
lsof -i :8080  # Audio client
```
