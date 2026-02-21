# Lock-In + Claude Desktop Integration

Hear Claude's reasoning out loud while it thinks through your questions.

## Prerequisites

- [Claude Desktop](https://claude.ai/download) installed (Mac or Windows)
- Python 3.10+
- API keys for [Cartesia](https://cartesia.ai/) and [Anthropic](https://console.anthropic.com/)

## Step 1 — Clone and Set Up

```bash
git clone <your-repo-url> cursor-tts
cd cursor-tts/lock-in
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Edit the `.env` file with your API keys:

```bash
CARTESIA_API_KEY=your_cartesia_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## Step 2 — Add the MCP Server to Claude Desktop

Open the Claude Desktop config file in a text editor:

- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the Lock-In MCP server (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "lock-in": {
      "command": "python3",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/full/path/to/cursor-tts/lock-in",
      "env": {
        "PYTHONPATH": "/full/path/to/cursor-tts/lock-in",
        "CARTESIA_API_KEY": "your_cartesia_api_key",
        "ANTHROPIC_API_KEY": "your_anthropic_api_key"
      }
    }
  }
}
```

> Replace `/full/path/to/cursor-tts/lock-in` with the actual absolute path on your machine.

**Restart Claude Desktop** after saving the config.

## Step 3 — Start the Voice Agent and Audio Client

Open two terminal windows:

**Terminal 1 — Voice Agent:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh voice
or
WS_PORT=9765 ./scripts/run.sh voice
or
WS_PORT=9765 MCP_WS_PORT=9766 ./scripts/run.sh voice
```

You should see:

```
🎤 Voice agent listening on ws://0.0.0.0:8765
```

**Terminal 2 — Audio Client:**

```bash
cd cursor-tts/lock-in
./scripts/run.sh client
or
./scripts/run.sh client 9090
```

You should see:

```
🔊 Serving Lock-In Audio Client...
   Open: http://localhost:8080
```

## Step 4 — Connect the Audio Client

1. Open **http://localhost:8080** in your browser
2. Click **Connect** — the status dot should turn green
3. Optionally click **Enable Microphone** (works on localhost without HTTPS)

> Since everything runs locally, `localhost` is a secure context and the microphone will work.

## Step 5 — Add Narration Instructions to Claude

Claude Desktop uses **Project Instructions** (similar to Cursor's `.cursorrules`):

1. Open Claude Desktop
2. Click **Projects** in the left sidebar
3. Create a new project (e.g., "Lock-In Voice")
4. Click the **Project instructions** area
5. Paste the following:

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

Example for "explain recursion":
  Step 1 [planning]: "Okay, the user wants to understand recursion. Let me think of
    a clear analogy and a simple code example."
  Step 2 [analyzing]: "I'll use the Russian nesting dolls analogy — each doll contains
    a smaller version of itself until you reach the smallest one. That's the base case."
  Step 3 [implementing]: "Writing a factorial example since it's the classic recursion
    demo. factorial of 5 calls factorial of 4, which calls factorial of 3, all the way
    down to 1."
```

6. Start a new conversation **inside this project**

## Step 6 — Talk to Claude

Every conversation inside the Lock-In project will have the narration instructions.
Claude will call `stream_reasoning_step` as it works through your questions, the
voice agent will convert the text to speech via Cartesia, and you'll hear it through
your browser.

## How It Works

```
You ask Claude a question
    ↓
Claude calls stream_reasoning_step (MCP tool) at each thinking step
    ↓
MCP Server generates narration text → sends to Voice Agent (port 8766)
    ↓
Voice Agent runs Cartesia TTS → sends audio frames (port 8765)
    ↓
Audio Client (browser) receives and plays the audio
    ↓
You hear Claude's reasoning through your speakers
```

## Troubleshooting

### Claude doesn't call the MCP tool

- Make sure Claude Desktop was restarted after editing the config
- Check that the `cwd` and `PYTHONPATH` paths are correct
- Look for the Lock-In tools icon (hammer) in Claude's input area — it should show `stream_reasoning_step`

### No audio

- Check the audio client shows "Connected" (green dot)
- Check the voice agent terminal for `📢 Narrating:` messages
- Make sure both the voice agent and audio client are running

### MCP server won't start

- Verify the Python path: run `which python3` and use that in the config
- Check that the venv is set up: `cd lock-in && source venv/bin/activate && python -m mcp_server.server`
- Check `lock-in.log` for errors

### SSL certificate errors (macOS)

If you see `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate` when the voice agent tries to connect to Cartesia, run the certificate install script that ships with Python:

```bash
"/Applications/Python 3.12/Install Certificates.command"
```

> Adjust the version number (`3.12`) to match your installed Python version. This installs the `certifi` root certificates that Python on macOS needs for HTTPS connections.

## Differences from Cursor Integration

| Feature | Cursor | Claude Desktop |
|---------|--------|----------------|
| MCP transport | stdio | stdio |
| Narration rules | `.cursorrules` file | Project Instructions |
| Rule scope | Workspace-wide | Per-project |
| Extended thinking capture | No (model limitation) | No (same limitation) |
| Audio client | Same | Same |
| Voice agent | Same | Same |