# 🔧 Lock-In Setup Guide

Detailed instructions for setting up Lock-In on your machine.

## Prerequisites

- **Python 3.10+** — required by Pipecat and MCP
- **Cartesia API key** — sign up at [cartesia.ai](https://cartesia.ai/)
- **Cursor IDE** — for MCP integration (optional for standalone testing)

## Step 1: Clone and Setup

```bash
cd lock-in
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The setup script will:
1. Create a Python virtual environment (`venv/`)
2. Install all dependencies from `requirements.txt` (including mcp-use)
3. Create a `.env` file from the template (if one doesn't exist)
4. Create `traces/` and `logs/` directories
5. Verify all dependencies are importable

## Step 2: Configure API Keys

Edit the `.env` file and add your API keys:

```bash
# Required key
CARTESIA_API_KEY=sk-your-cartesia-key
```

### Getting API Keys

**Cartesia:**
1. Go to [cartesia.ai](https://cartesia.ai/) and create an account
2. Navigate to the API section in your dashboard
3. Generate a new API key

### Verify API Keys

```bash
# Check Cartesia key
curl -H "X-API-Key: $CARTESIA_API_KEY" https://api.cartesia.ai/voices
```

## Step 3: Run Lock-In

### Option A: HTTP Mode (for testing with MCP Inspector)

```bash
# Start the MCP server in HTTP mode
./scripts/run.sh mcp-http
```

This starts the server on `http://localhost:8000` with:
- `/mcp` — MCP protocol endpoint (Streamable HTTP)
- `/openmcp.json` — OpenMCP schema
- `/inspector` — Built-in inspector UI
- `/docs` — API documentation

**Test with MCP Inspector:**
```bash
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp
```

### Option B: Full Stack (Voice + MCP + Audio Client)

```bash
# Start everything
./scripts/run.sh all
```

Or start components individually:

**Terminal 1 — Voice Agent:**
```bash
./scripts/run.sh voice
```

**Terminal 2 — MCP Server (stdio mode for Cursor):**
```bash
./scripts/run.sh mcp
```

**Terminal 3 — Audio Client:**
```bash
./scripts/run.sh client
```

### Test the Narration Demo

To verify everything works without API keys:

```bash
./scripts/run.sh demo
```

This runs the template-based narration demo using example traces.

## Step 4: Configure Cursor MCP Integration

Add Lock-In as an MCP server in Cursor's settings.

### Option A: stdio Mode (Recommended for Cursor)

Add to your Cursor `settings.json` or `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lock-in": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/lock-in",
      "env": {
        "PYTHONPATH": "/path/to/lock-in",
        "MCP_TRANSPORT": "stdio",
        "CARTESIA_API_KEY": "your_cartesia_key"
      }
    }
  }
}
```

### Option B: HTTP Mode (for remote/shared servers)

If running the MCP server on a remote machine or using ngrok:

```json
{
  "mcpServers": {
    "lock-in": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Or with ngrok for remote access:
```json
{
  "mcpServers": {
    "lock-in": {
      "url": "https://your-ngrok-url.ngrok-free.app/mcp"
    }
  }
}
```

Replace `/path/to/lock-in` with the actual absolute path to the `lock-in` directory.

### MCP Tools Available

Once configured, Cursor's agent can call these tools:

| Tool | Description |
|------|-------------|
| `stream_reasoning_step` | Stream a reasoning step for voice narration |
| `answer_user_question` | Answer a user question using session context |
| `get_conversation_history` | Retrieve the Q&A history for the current session |

## Step 5: Verify Everything Works

### Test MCP Server (HTTP Mode)

```bash
# Start the server
./scripts/run.sh mcp-http

# In another terminal, test the endpoint
curl http://localhost:8000/openmcp.json | jq .tools

# Or use MCP Inspector
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp
```

### Run the Test Suite

```bash
./scripts/run.sh test
```

### Run with Coverage

```bash
./scripts/run.sh test-coverage
```

### Test the Full Flow

1. Start the voice agent: `./scripts/run.sh voice`
2. Start the MCP server (HTTP): `./scripts/run.sh mcp-http`
3. Start the audio client: `./scripts/run.sh client`
4. Open `http://localhost:8080` and click **Connect**
5. Use MCP Inspector to call `stream_reasoning_step`
6. You should hear narration through your speakers

## Troubleshooting

### "Virtual environment not found"

Run `./scripts/setup.sh` first to create the virtual environment.

### "Missing API keys"

Edit `.env` and replace placeholder values with real API keys. Don't use the default `your_*_here` values.

### Port conflicts

Check if ports 8000 (MCP HTTP), 8765 (voice agent), or 8766 (MCP WebSocket) are already in use:

```bash
lsof -i :8000
lsof -i :8765
lsof -i :8766
```

Kill processes on those ports:

```bash
kill $(lsof -t -i:8000)
kill $(lsof -t -i:8765)
kill $(lsof -t -i:8766)
```

### MCP Inspector "Connection Error"

Make sure:
1. The MCP server is running: `./scripts/run.sh mcp-http`
2. You're using the correct URL: `http://localhost:8000/mcp`
3. Transport type is set to "Streamable HTTP"

### Import errors

Re-run setup to reinstall dependencies:

```bash
rm -rf venv/
./scripts/setup.sh
```

### No audio output

- Check that your system audio is working
- Verify the Cartesia API key is valid
- Check the log file: `tail -f lock-in.log`

### Cursor doesn't see MCP tools

- Verify the MCP server path in settings is correct
- Ensure `PYTHONPATH` includes the `lock-in` directory
- Set `MCP_TRANSPORT=stdio` in the env for Cursor
- Restart Cursor after changing MCP settings
- Check Cursor's MCP logs for connection errors

## Optional Configuration

### Change the Voice

Browse voices at [Cartesia](https://cartesia.ai/) and update in `.env`:

```bash
CARTESIA_VOICE_ID=your_preferred_voice_id
```

### Adjust Speed

```bash
NARRATION_SPEED=1.2  # Slightly faster narration
```

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG
DEBUG_MODE=true
```

### Save Trace Data

```bash
SAVE_TRACES=true
TRACES_DIR=./traces
```
