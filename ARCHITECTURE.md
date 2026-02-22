# Lock-In Architecture: Complete Code Flow

This document explains exactly what happens at every step when Lock-In runs,
how the pieces connect, and where the data flows.

## The Three Processes

When you run `./scripts/run.sh both`, two OS processes start:

| Process | Command | Role |
|---------|---------|------|
| **MCP Server** | `python -m mcp_server.server` | Receives tool calls from Cursor via stdio, generates narration text, sends it to the voice agent via WebSocket |
| **Voice Agent** | `python -m voice_agent.agent` | Hosts the audio pipeline (STT + TTS), hosts the MCP bridge WebSocket server, converts text to speech |

Cursor itself is the third participant -- it calls MCP tools over stdio when its
agent is working on a task.

## Network Ports

```
Port 8765  (voice agent)  -- Pipecat audio WebSocket server
                             Accepts connections from an audio client
                             Streams PCM audio in (mic) and out (speakers)

Port 8766  (voice agent)  -- MCP bridge WebSocket server
                             Accepts connections from the MCP server
                             Carries JSON messages (narrations, questions, answers)
```

Both ports are hosted by the voice agent process. The MCP server connects to
8766 as a client.

## Startup Sequence

```
1. run.sh starts MCP server in background
   └─ server.py main()
      ├─ Creates ContextManager (session state)
      ├─ Creates NarrationGenerator (template-based, no LLM client)
      ├─ Creates FastMCP server with 3 tools
      └─ Blocks on mcp_server.run(transport="stdio")
         Cursor communicates with this process via stdin/stdout

2. run.sh starts voice agent in foreground (after 2s delay)
   └─ agent.py main()
      ├─ Loads Settings from .env
      ├─ Validates API keys (Cartesia + Anthropic)
      ├─ Creates LockInVoiceAgent
      └─ asyncio.run(agent.run())
         ├─ _setup_pipeline()           → builds the Pipecat audio pipeline
         ├─ _start_mcp_bridge()         → starts WebSocket server on port 8766
         ├─ starts narration_loop task  → background loop that feeds text to TTS
         └─ PipelineRunner.run()        → starts WebSocket server on port 8765
                                           blocks here, processing audio frames
```

## The Pipecat Audio Pipeline

The pipeline is a chain of frame processors. Data flows through them in order:

```
transport.input()          Audio frames from user's microphone (port 8765)
       │
       ▼
CartesiaSTTService         Sends audio to Cartesia API, returns TranscriptionFrames
       │                   Model: ink-whisper, 16kHz
       ▼
UserQuestionHandler        Inspects TranscriptionFrames
       │                   If it sees text, calls agent.handle_user_question()
       │                   Passes all frames through unchanged
       ▼
NarrationInjector          Passes through incoming frames unchanged
       │                   ALSO: background loop pulls from _narration_queue
       │                   and pushes TextFrames downstream (towards TTS)
       ▼
CartesiaTTSService         Converts TextFrames to audio via Cartesia API
       │                   Model: sonic-3, 44.1kHz, PCM s16le
       ▼
transport.output()         Sends audio frames to user's speakers (port 8765)
```

Key detail: the pipeline needs a WebSocket client connected to port 8765 to
actually process frames. Without a connected audio client, the pipeline is idle.
The `StartFrame` is sent when a client connects, which is what enables frame
processing.

### How Text Becomes Speech

1. `NarrationInjector` has an internal `asyncio.Queue[str]`
2. When narration text arrives (from MCP bridge), it's added to the queue
3. A background task (`run_narration_loop`) pulls text from the queue every 0.5s
4. It creates a `TextFrame(text=...)` and pushes it downstream
5. `CartesiaTTSService` receives the TextFrame, calls Cartesia's TTS API
6. Cartesia returns audio chunks, which become audio frames
7. `transport.output()` sends those audio frames over the WebSocket to the client

### How Speech Becomes Text (User Questions)

1. User speaks into microphone → audio frames arrive at `transport.input()`
2. `CartesiaSTTService` streams audio to Cartesia's STT API
3. When Cartesia detects a complete utterance, it returns a `TranscriptionFrame`
4. `UserQuestionHandler.process_frame()` sees the TranscriptionFrame
5. It calls `agent.handle_user_question(text)`
6. The agent pauses narration, sends the question to MCP server via WebSocket
7. The MCP server builds a contextual answer and sends it back
8. The voice agent speaks the answer through the pipeline

## The Narration Flow (MCP → Voice)

This is the main flow -- Cursor's agent narrates what it's thinking:

```
Step 1: Cursor agent calls MCP tool
────────────────────────────────────
Cursor's AI agent is working on your code. Its system prompt (or rules)
tell it to call stream_reasoning_step() at each thinking step.

   Cursor Agent ──stdio──▶ MCP Server
   {
     "tool": "stream_reasoning_step",
     "args": {
       "step_number": 1,
       "step_description": "Planning JWT auth for the REST API",
       "thinking_type": "planning",
       "files_involved": ["auth.py", "models.py"]
     }
   }


Step 2: MCP server processes the tool call
──────────────────────────────────────────
   server.py: stream_reasoning_step()
   │
   ├─ _ensure_session()
   │    Creates a session if one doesn't exist (UUID)
   │
   ├─ Creates a ReasoningStep model
   │    Stores it in ContextManager (for Q&A context later)
   │
   ├─ narration_generator.generate_narration(step, previous_steps)
   │    Template-based: picks a tone intro + description
   │    Example output: "Okay, so here's my plan... We'll need to
   │                     work with auth.py, models.py. Planning JWT
   │                     auth for the REST API"
   │
   │    (If an LLM client were configured, it would call Claude to
   │     generate a more natural narration instead)
   │
   └─ _send_to_voice_agent(ws_msg)
        Calls _get_voice_ws() which lazily connects to ws://localhost:8766
        Sends JSON: {"type": "narration", "payload": {"narration_text": "..."}}


Step 3: Voice agent receives narration via bridge
─────────────────────────────────────────────────
   agent.py: _handle_connection() on port 8766
   │
   ├─ Receives JSON message, parses type="narration"
   ├─ Calls handle_narration_step_text(text)
   └─ Calls narration_injector.inject_narration(text)
        Adds text to the internal asyncio.Queue


Step 4: Narration loop delivers to TTS
───────────────────────────────────────
   pipeline.py: NarrationInjector.run_narration_loop()
   │
   ├─ Pulls text from queue
   ├─ Creates TextFrame(text=narration_text)
   ├─ Pushes frame DOWNSTREAM in the pipeline
   │
   ▼
   CartesiaTTSService converts text to audio
   ▼
   transport.output() sends audio to connected client on port 8765
   ▼
   User hears the narration through speakers


Step 5: Tool returns result to Cursor
─────────────────────────────────────
   stream_reasoning_step() returns to Cursor:
   {
     "status": "narrated",
     "narration": "Okay, so here's my plan...",
     "step_number": 1,
     "user_question": null   ← or a question if the user spoke
   }

   If user_question is set, Cursor's agent sees it and can respond.
```

## The Question Flow (User → MCP → Voice)

When the user speaks a question while the agent is working:

```
Step 1: User speaks
───────────────────
   Microphone audio → port 8765 → CartesiaSTT → TranscriptionFrame
   UserQuestionHandler detects text, calls agent.handle_user_question()


Step 2: Voice agent routes question
────────────────────────────────────
   agent.py: handle_user_question()
   │
   ├─ pause_narration()        ← stops delivering queued narrations
   ├─ Sends JSON to MCP server via the bridge WebSocket on 8766:
   │    {"type": "question", "payload": {"question": "Why JWT?"}}
   └─ Waits 1 second, then resume_narration()


Step 3: MCP server receives question
─────────────────────────────────────
   server.py: _listen_for_questions() (background task)
   │
   └─ Puts question text into _user_question_queue


Step 4: Cursor agent sees the question
───────────────────────────────────────
   Next time Cursor calls stream_reasoning_step(), the return value
   includes "user_question": "Why JWT?"

   Cursor's agent can then call answer_user_question() to respond.


Step 5: Answer flows back to voice
───────────────────────────────────
   server.py: answer_user_question()
   │
   ├─ Builds context from ContextManager (recent steps, files, history)
   ├─ Generates answer (template-based or LLM-powered)
   ├─ Stores in conversation history
   └─ Sends to voice agent: {"type": "answer", "payload": {"answer": "..."}}

   Voice agent receives it on the bridge, speaks it through TTS.
```

## Turn-Taking

Turn-taking is handled by pausing and resuming the narration queue:

1. **Normal state**: narration_loop pulls from queue, feeds TTS
2. **User speaks**: `UserQuestionHandler` fires → `pause_narration()` is called
   - `_paused = True` on the NarrationInjector
   - New narrations are NOT added to queue (rejected in `inject_narration`)
   - Items already in queue are re-queued if loop tries to deliver them
3. **Question sent**: routed to MCP server via bridge
4. **Answer received**: spoken through TTS
5. **Resume**: after 1 second delay, `resume_narration()` is called
   - `_paused = False` — queued narrations start flowing again

If `enable_interruptions=True` (the default), pipecat also handles audio-level
interruption — if the user starts speaking while TTS is playing, the TTS output
is cut off.

## Template vs LLM Narration

The `NarrationGenerator` has two modes:

### Template-Based (current default)
- No API calls needed
- Picks a tone-appropriate intro phrase from `TONE_INTROS` dict
- Concatenates with the step description and file names
- Example: `"Let me take a look at... models/user.py. Reading existing user model"`
- Fast but repetitive

### LLM-Powered (when llm_client is provided)
- Uses Claude (Anthropic) to generate natural narration
- System prompt defines the "conversational pair programmer" persona
- Takes step info + previous steps as context
- Produces more varied, natural speech
- Falls back to template if the API call fails

Currently the MCP server creates `NarrationGenerator()` with no client
(template-based). To enable LLM narration, you'd pass an Anthropic
`AsyncAnthropic` client to the constructor.

## Context Manager (Session State)

The `ContextManager` tracks everything that happens in a session:

```
SessionContext
├── session_id: UUID
├── reasoning_steps: [ReasoningStep, ...]     ← every step the agent reported
├── conversation_history: [ConversationEntry]  ← every Q&A exchange
├── current_step: int                          ← latest step number
└── started_at: datetime
```

When a user asks a question, `get_context_for_question()` builds a summary:
- Last 5 reasoning steps (with descriptions, types, files)
- Last 3 Q&A entries
- All files touched so far
- Session duration

This context is used to generate relevant answers.

## File Map

```
mcp_server/
├── server.py              Entry point. FastMCP server with 3 tools.
│                          Connects to voice agent on ws://localhost:8766.
├── narration_generator.py Converts ReasoningStep → speakable text.
│                          Template-based or LLM-powered.
├── context_manager.py     Thread-safe session state (steps, Q&A history).
├── trace_listener.py      Parses raw Cursor trace JSON into ReasoningSteps.
│                          Used by the demo; MCP tools bypass this.
└── models.py              Pydantic models: ReasoningStep, WebSocketMessage, etc.

voice_agent/
├── agent.py               Orchestrator. Builds pipeline, hosts MCP bridge on
│                          8766, handles narration/question routing.
├── pipeline.py            Pipecat pipeline: STT → QuestionHandler →
│                          NarrationInjector → TTS. Runs on port 8765.
└── config.py              Pydantic Settings. Loads from .env file.
```

## What's Not Connected Yet

- **Audio client**: Port 8765 needs a pipecat-compatible WebSocket client that
  streams microphone audio in and plays speaker audio out. Without this, the
  pipeline is idle (no StartFrame). A browser-based client or a local Python
  audio client would fill this role.

- **LLM-powered narration**: The `NarrationGenerator` supports it, but no
  Anthropic client is wired in. The MCP server creates `NarrationGenerator()`
  with no llm_client, so it uses templates.

- **Cursor agent prompt integration**: Cursor's agent needs to be instructed
  (via system prompt or rules) to call `stream_reasoning_step` at each thinking
  step. Without this, the MCP tools exist but are never called.
