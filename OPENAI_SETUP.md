# Lock-In + OpenAI Integration

Hear reasoning out loud when using OpenAI models. Two integration paths are available:

| Path | Best for | Transport | Setup effort |
|------|----------|-----------|--------------|
| **ChatGPT Desktop** | Interactive chat with voice narration | Streamable HTTP + ngrok | Medium |
| **OpenAI Agents SDK** | Custom Python agents with voice narration | stdio | Low |

---

## Prerequisites (both paths)

- Python 3.10+
- API keys for [Cartesia](https://cartesia.ai/) and [OpenAI](https://platform.openai.com/api-keys)
- Lock-In repo cloned and set up:

```bash
git clone <your-repo-url> cursor-tts
cd cursor-tts/lock-in
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Edit `.env` with your keys:

```bash
CARTESIA_API_KEY=your_cartesia_api_key
OPENAI_API_KEY=your_openai_api_key
```

---

## Path A: ChatGPT Desktop App

ChatGPT Desktop connects to MCP servers over **streamable HTTP** with a **public HTTPS endpoint**. It does not support stdio. This means you need to:

1. Run the MCP server in HTTP mode
2. Expose it publicly via a tunnel (ngrok)

### A1 — Install ngrok

Sign up at [ngrok.com](https://ngrok.com/) and install:

```bash
# Linux
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz | tar xz
sudo mv ngrok /usr/local/bin/

# Mac
brew install ngrok

# Then authenticate
ngrok config add-authtoken YOUR_NGROK_TOKEN
```

### A2 — Create the HTTP launcher

Create a file `lock-in/run_http_server.py`:

```python
"""Launch the Lock-In MCP server in streamable-http mode for ChatGPT Desktop."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_server.server import mcp_server
from loguru import logger

def main():
    port = int(os.environ.get("MCP_HTTP_PORT", "8100"))
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add("lock-in.log", rotation="10 MB", level="DEBUG")
    logger.info(f"Starting Lock-In MCP server (streamable-http) on port {port}...")

    mcp_server.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
    )

if __name__ == "__main__":
    main()
```

### A3 — Start all services

Open four terminal windows:

**Terminal 1 — Voice Agent:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh voice
```

**Terminal 2 — Audio Client:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh client
```

**Terminal 3 — MCP HTTP Server:**

```bash
cd cursor-tts/lock-in
source venv/bin/activate
python run_http_server.py
```

You should see:

```
Starting Lock-In MCP server (streamable-http) on port 8100...
```

**Terminal 4 — ngrok tunnel:**

```bash
ngrok http 8100
```

ngrok will display a public URL like:

```
Forwarding  https://a1b2c3d4.ngrok-free.app -> http://localhost:8100
```

Copy the `https://...ngrok-free.app` URL.

### A4 — Enable Developer Mode in ChatGPT

1. Open **ChatGPT Desktop**
2. Go to **Settings** (gear icon)
3. Navigate to **Apps & Connectors > Advanced settings**
4. Toggle **Developer mode** on

> Developer mode may require a ChatGPT Plus, Team, or Enterprise plan. Workspace admins may need to enable it first.

### A5 — Add the MCP Connector

1. In ChatGPT, go to **Settings > Apps & Connectors**
2. Click **Add connector**
3. Fill in:
   - **Name**: `Lock-In Voice`
   - **Description**: `Live voice narration of reasoning`
   - **MCP endpoint**: `https://a1b2c3d4.ngrok-free.app/mcp` (your ngrok URL + `/mcp`)
4. Click **Save**

### A6 — Add Narration Instructions

ChatGPT doesn't have "Project Instructions" like Claude Desktop. Instead, use **Custom Instructions**:

1. Go to **Settings > Personalization > Custom instructions**
2. In the "How would you like ChatGPT to respond?" section, paste:

```
You have access to the Lock-In MCP server which narrates your reasoning out loud
to the user via text-to-speech. The user is listening through speakers.

Call `stream_reasoning_step` MULTIPLE TIMES per response to narrate your thinking
process conversationally, as if you're a colleague thinking out loud.

When to narrate:
- Initial reaction to the user's request
- Your planning and approach
- Key decisions and trade-offs
- Discoveries or surprises
- What you're implementing and why

Style:
- Talk like a thoughtful colleague, not a documentation bot
- Be specific — mention concrete details
- Keep each narration 1-3 sentences (it gets spoken aloud)
- Use thinking_type accurately: "planning", "analyzing", "implementing", "debugging", "testing"
- Increment step_number with each call
- For complex tasks, aim for 3-6 narration steps
- For simple questions, 1-2 steps is fine
```

3. Save and start a new conversation

### A7 — Test it

1. Open **http://localhost:8080** in your browser and click **Connect**
2. In ChatGPT, start a new conversation and ask a question
3. Look for the Lock-In tools icon — ChatGPT will show tool-call payloads for confirmation
4. Approve the tool call and listen for the narration

---

## Path B: OpenAI Agents SDK

The Agents SDK is a Python library that lets you build custom agents with OpenAI models. It has native MCP support via stdio — no tunnel needed.

### B1 — Install the SDK

```bash
cd cursor-tts/lock-in
source venv/bin/activate
pip install openai-agents
```

### B2 — Create the agent script

Create a file `lock-in/run_openai_agent.py`:

```python
"""Custom OpenAI agent with Lock-In voice narration via MCP."""

import asyncio
import os
import sys

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

NARRATION_INSTRUCTIONS = """
You have access to the Lock-In MCP server which narrates your reasoning out loud
to the user via text-to-speech. The user is listening through speakers.

Call `stream_reasoning_step` MULTIPLE TIMES per response to narrate your thinking
process conversationally, as if you're a colleague thinking out loud.

When to narrate:
- Initial reaction to the user's request
- Your planning and approach
- Key decisions and trade-offs
- Discoveries or surprises
- What you're implementing and why

Style:
- Talk like a thoughtful colleague, not a documentation bot
- Be specific — mention concrete details
- Keep each narration 1-3 sentences (it gets spoken aloud)
- Use thinking_type accurately: "planning", "analyzing", "implementing", "debugging", "testing"
- Increment step_number with each call
- For complex tasks, aim for 3-6 narration steps
- For simple questions, 1-2 steps is fine
"""

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


async def main():
    async with MCPServerStdio(
        name="lock-in",
        command="python3",
        args=["-m", "mcp_server.server"],
        cwd=PROJECT_DIR,
        env={
            **os.environ,
            "PYTHONPATH": PROJECT_DIR,
        },
    ) as lock_in_server:

        agent = Agent(
            name="Lock-In Assistant",
            instructions=NARRATION_INSTRUCTIONS,
            mcp_servers=[lock_in_server],
        )

        print("Lock-In OpenAI Agent ready. Type your questions (Ctrl+C to exit).\n")

        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                print("Thinking...\n")
                result = await Runner.run(agent, user_input)
                print(f"Agent: {result.final_output}\n")
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break


if __name__ == "__main__":
    asyncio.run(main())
```

### B3 — Start the services

Open three terminal windows:

**Terminal 1 — Voice Agent:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh voice
```

**Terminal 2 — Audio Client:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh client
```

**Terminal 3 — OpenAI Agent:**

```bash
cd cursor-tts/lock-in
source venv/bin/activate
export OPENAI_API_KEY=your_openai_api_key
python run_openai_agent.py
```

### B4 — Test it

1. Open **http://localhost:8080** in your browser and click **Connect**
2. In Terminal 3, type a question at the `You:` prompt
3. The agent will call `stream_reasoning_step` and you'll hear the narration
4. The agent's final text response appears in the terminal

---

## How It Works

Both paths use the same audio pipeline; they differ only in how the MCP server is connected:

```
                  Path A (ChatGPT)                    Path B (Agents SDK)
                  ────────────────                    ───────────────────
                  ChatGPT Desktop                     Python Agent (CLI)
                       │                                     │
                  streamable-http                          stdio
                  (ngrok tunnel)                     (subprocess)
                       │                                     │
                       └──────────────┬──────────────────────┘
                                      │
                              Lock-In MCP Server
                                      │
                              WebSocket (port 8766)
                                      │
                              Voice Agent (Pipecat)
                              Cartesia TTS engine
                                      │
                              WebSocket (port 8765)
                                      │
                              Audio Client (browser)
                                      │
                              Your speakers
```

## Troubleshooting

### ChatGPT says "Unsafe URL"

ChatGPT requires a **public HTTPS** endpoint. Make sure ngrok is running and you're using the `https://` URL it provides, not `http://localhost`.

### ChatGPT doesn't show Lock-In tools

- Developer mode must be enabled in ChatGPT settings
- Refresh the connector: Settings > Apps & Connectors > Lock-In Voice > Refresh
- Try starting a new conversation after adding the connector

### Agents SDK can't find the MCP server

- Make sure `PYTHONPATH` includes the `lock-in` directory
- Check that `mcp_server/server.py` exists and is importable: `python -c "from mcp_server.server import mcp_server; print('OK')"`

### ngrok tunnel disconnects

Free ngrok sessions expire after a few hours. Restart ngrok and update the connector URL in ChatGPT settings. For persistent URLs, upgrade to a paid ngrok plan or use Cloudflare Tunnel.

### No audio

- Check the audio client shows "Connected" (green dot)
- Check the voice agent terminal for `Narrating:` messages
- Make sure voice agent and audio client are both running

## Comparison: ChatGPT vs Agents SDK

| Feature | ChatGPT Desktop (Path A) | Agents SDK (Path B) |
|---------|--------------------------|---------------------|
| UI | ChatGPT app | Terminal CLI |
| Transport | Streamable HTTP | stdio |
| Needs tunnel | Yes (ngrok) | No |
| Tool approval | Manual per call | Automatic |
| Model | GPT-4o (or current default) | Configurable |
| Custom instructions | ChatGPT settings | Code |
| Conversation memory | Built-in | Manual |
| Setup effort | Medium | Low |
