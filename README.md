# 🔒 Lock-In: Never Wait Silently for Code Again

Lock-In transforms Cursor's AI agent from a silent code generator into an active pair programmer. Instead of staring at a loading spinner, you hear the agent explain its reasoning in real-time and can ask questions mid-generation.

**Built with [mcp-use](https://mcp-use.com/)** — Connect Any LLM to Any MCP Server

## 🎯 The Problem

When Cursor's agent generates code, you wait 30-60 seconds in silence:
- ❌ No idea what it's thinking
- ❌ Can't course-correct early
- ❌ Wasted time feeling disconnected
- ❌ Miss learning opportunities

## ✨ The Solution

Lock-In gives Cursor's agent a voice:
- ✅ Hear reasoning in real-time ("I'm checking your auth setup...")
- ✅ Ask questions mid-generation ("Should we use JWT or sessions?")
- ✅ Catch mistakes before code is written
- ✅ Learn WHY decisions are made
- ✅ Stay engaged and "locked in" to the process

## 🎥 Demo

**Old way:**
```
User: "Add authentication to my API"
[30 seconds of loading spinner]
[Code appears]
```

**Lock-In way:**
```
User: "Add authentication to my API"
Agent: "Alright, let me think about authentication for your API..."
Agent: "I'm checking your existing user model... I see you have password hashing already, good."
User: "Should we use JWT or sessions?"
Agent: "Great question! Since this is a REST API, JWT tokens would be better for stateless auth..."
Agent: "Now I'm creating the auth middleware file..."
[Code appears with full understanding of decisions]
```

## 🚀 Quick Start

```bash
# 1. Setup
cd lock-in
chmod +x scripts/setup.sh
./scripts/setup.sh

# 2. Add API keys to .env
# Edit .env with your Cartesia API key

# 3. Run the MCP Server (HTTP mode for testing)
./scripts/run.sh mcp-http

# 4. Test with MCP Inspector
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp

# 5. Or run everything (voice agent + MCP server + audio client)
./scripts/run.sh all
```

### Testing the MCP Server

The MCP server runs on `http://localhost:8000` with these endpoints:
- `/mcp` — MCP protocol endpoint (Streamable HTTP)
- `/openmcp.json` — OpenMCP schema
- `/inspector` — Built-in inspector UI
- `/docs` — API documentation

```bash
# Test with curl
curl http://localhost:8000/openmcp.json | jq .tools

# Test with MCP Inspector (local)
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8000/mcp

# Test with ngrok (for remote access)
ngrok http 8000
# Then use the ngrok URL in MCP Inspector web UI
```

## 🏗️ Architecture

```
Cursor Agent (generating code)
    ↓ (reasoning traces via MCP tools)
Lock-In MCP Server (mcp-use, port 8000)
    ↓ (narration text via WebSocket)
Voice Agent (Pipecat pipeline, port 8765)
    ↓ (TTS via Cartesia, protobuf frames)
Audio Client (browser, connects to port 8765)
    ↓
User's Speakers 🔊

User's Microphone 🎤
    ↓ (captured by Audio Client)
Voice Agent (STT via Cartesia)
    ↓ (question via WebSocket)
MCP Server (answers using session context)
    ↓ (answer text)
Voice Agent → Audio Client → User's Speakers
```

### MCP Server Modes

The MCP server supports two transport modes:

| Mode | Command | Use Case |
|------|---------|----------|
| **HTTP** | `./scripts/run.sh mcp-http` | Web clients, MCP Inspector, ChatGPT, Claude |
| **stdio** | `./scripts/run.sh mcp` | Cursor IDE, Claude Desktop |

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────┐
│                    VOICE AGENT                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  User Audio Input (microphone)                         │
│         ↓                                               │
│  Cartesia STT (speech → text)                          │
│         ↓                                               │
│  UserQuestionHandler (detect questions)                │
│         ↓                                               │
│  NarrationInjector (queue + inject narration text)     │
│         ↓                                               │
│  Cartesia TTS (text → speech)                          │
│         ↓                                               │
│  User Audio Output (speakers)                          │
│                                                         │
│  ← MCP Server sends narration/answers via WebSocket →  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
lock-in/
├── README.md                      # This file
├── SETUP.md                       # Detailed setup instructions
├── COMMANDS.md                    # All commands reference
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variables template
├── .gitignore                     # Git ignore rules
│
├── scripts/
│   ├── setup.sh                   # Automated setup script
│   └── run.sh                     # Multi-command run script
│
├── audio_client/
│   └── index.html                 # Browser audio client (WebSocket + protobuf)
│
├── mcp_server/
│   ├── __init__.py
│   ├── server.py                  # MCP server with tools (mcp-use SDK)
│   ├── trace_listener.py          # Parse Cursor agent traces
│   ├── narration_generator.py     # Convert traces to natural speech
│   ├── context_manager.py         # Session context for Q&A
│   └── models.py                  # Pydantic data models
│
├── voice_agent/
│   ├── __init__.py
│   ├── agent.py                   # Main voice agent orchestrator
│   ├── config.py                  # Pydantic Settings configuration
│   └── pipeline.py                # Pipecat pipeline (STT→LLM→TTS)
│
├── tests/
│   ├── __init__.py
│   ├── test_mcp_server.py         # MCP server component tests
│   ├── test_voice_agent.py        # Voice agent component tests
│   └── test_integration.py        # Integration tests
│
└── examples/
    ├── example_traces.json        # Sample reasoning traces
    └── test_narration.py          # Standalone narration demo
```

## 🛠️ Tech Stack

- **[mcp-use](https://mcp-use.com/)** — MCP server SDK for Python (Streamable HTTP + stdio)
- **[Pipecat](https://github.com/pipecat-ai/pipecat)** — Voice pipeline orchestration
- **[Cartesia](https://cartesia.ai/)** — Ultra-low latency TTS/STT (< 500ms)
- **[MCP](https://modelcontextprotocol.io/)** — Model Context Protocol for Cursor integration
- **[Pydantic](https://docs.pydantic.dev/)** — Type-safe configuration and models
- **[Loguru](https://github.com/Delgan/loguru)** — Structured logging

## 🎤 Example Narrations

**Planning Phase:**
> "Okay, so you want authentication. I'm thinking JWT tokens since this is a REST API. Let me plan out what files we'll need to touch."

**Analyzing Phase:**
> "I'm looking at your existing user model in models/user.py. I see you already have password hashing, that's good."

**Implementing Phase:**
> "Now I'm creating auth_middleware.py. Writing the verify_token function for protected routes..."

**Debugging Phase:**
> "Hmm, I noticed your token expiry is set to 15 minutes — that might be too short for development."

**Testing Phase:**
> "Let me verify this works... Running a quick check on the auth flow."

## 🔊 Audio Client

The audio client is a browser-based frontend that connects to the voice agent's WebSocket on port 8765. It receives protobuf-encoded audio frames from the Pipecat pipeline and plays them through your speakers. Optionally, it captures microphone audio for the speech-to-text question flow.

```bash
# Serve the audio client (default port 8080)
./scripts/run.sh client

# Or specify a custom port
./scripts/run.sh client 9000

# Or start everything at once (voice agent + MCP server + audio client)
./scripts/run.sh all
```

Then open `http://localhost:8080` (or `http://<server-ip>:8080` from another machine), and click **Connect**.

## 🔧 Configuration

Customize narration style, voice, speed, and more in `.env`:

```bash
# Use a different Cartesia voice
CARTESIA_VOICE_ID=your_preferred_voice_id

# Adjust narration speed (1.0 = normal, 1.2 = faster)
NARRATION_SPEED=1.1

# Enable/disable user interruptions
ENABLE_INTERRUPTIONS=true

# Set log level
LOG_LEVEL=DEBUG
```

See `.env.example` for all available settings.

## 📚 Documentation

- [Setup Guide](SETUP.md) — Detailed setup and Cursor integration instructions
- [Commands Reference](COMMANDS.md) — All commands and usage patterns

## 🧪 Testing

```bash
# Run all tests
./scripts/run.sh test

# Run with coverage
./scripts/run.sh test-coverage

# Run a specific test file
PYTHONPATH=. pytest tests/test_mcp_server.py -v
```

## 📄 License

MIT License

## 🙏 Acknowledgments

- **[mcp-use](https://mcp-use.com/)** for the MCP server SDK
- [Anthropic](https://anthropic.com/) for MCP
- [Pipecat / Daily](https://www.pipecat.ai/) for voice infrastructure
- [Cartesia](https://cartesia.ai/) for low-latency TTS/STT
- [Cursor](https://cursor.com/) for the agent-trace spec
