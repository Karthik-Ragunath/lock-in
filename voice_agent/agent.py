"""
Lock-In Voice Agent - Main orchestrator that connects all pieces via Pipecat.

This is the primary voice agent that:
1. Receives reasoning step narrations from the MCP server
2. Converts them to speech via Cartesia TTS
3. Listens for user questions via Cartesia STT
4. Routes questions to the MCP server for answers
5. Speaks answers back to the user
"""

import asyncio
import json
import logging
import sys
import uuid
from typing import Optional

import websockets
from loguru import logger

from pipecat.pipeline.runner import PipelineRunner

from .config import Settings, get_settings
from .pipeline import NarrationInjector, build_pipeline


class LockInVoiceAgent:
    """
    Main voice agent orchestrator for Lock-In.
    
    Manages the Pipecat voice pipeline and WebSocket connection to the
    MCP server for bidirectional narration/question flow.
    """

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or get_settings()
        self.session_id = str(uuid.uuid4())

        # Pipeline components (built in setup)
        self._transport = None
        self._task = None
        self._narration_injector: Optional[NarrationInjector] = None

        # MCP bridge WebSocket server + active connection
        self._mcp_bridge = None
        self._mcp_ws = None

        # State
        self._running = False
        self._narration_paused = False

        logger.info(f"LockInVoiceAgent created (session: {self.session_id})")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _setup_pipeline(self):
        """Build the Pipecat voice pipeline."""
        self._transport, self._task, self._narration_injector = build_pipeline(
            config=self.config,
            on_question_callback=self.handle_user_question,
        )
        logger.info("Voice pipeline setup complete")

    # ------------------------------------------------------------------
    # MCP Bridge WebSocket Server
    # ------------------------------------------------------------------
    async def _start_mcp_bridge(self):
        """Start a WebSocket server on mcp_ws_port for MCP server connections."""
        async def _handle_connection(websocket):
            self._mcp_ws = websocket
            logger.info("MCP server connected to bridge")
            try:
                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                        msg_type = msg.get("type", "")
                        payload = msg.get("payload", {})

                        if msg_type == "narration":
                            text = payload.get("narration_text", "")
                            if text:
                                await self.handle_narration_step_text(text)

                        elif msg_type == "answer":
                            text = payload.get("answer", "")
                            if text:
                                await self.speak(text)

                        elif msg_type == "session_end":
                            logger.info("MCP session ended")
                            break

                        else:
                            logger.debug(f"Unknown MCP message type: {msg_type}")

                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from MCP server")
                    except Exception as e:
                        logger.error(f"MCP message handling error: {e}")

            except websockets.ConnectionClosed:
                logger.info("MCP server disconnected from bridge")
            finally:
                self._mcp_ws = None

        ws_logger = logging.getLogger("websockets.server")
        ws_logger.setLevel(logging.CRITICAL)

        self._mcp_bridge = await websockets.serve(
            _handle_connection,
            "localhost",
            self.config.mcp_ws_port,
            logger=ws_logger,
        )
        logger.info(
            f"MCP bridge listening on ws://localhost:{self.config.mcp_ws_port}"
        )

    # ------------------------------------------------------------------
    # Narration Handling
    # ------------------------------------------------------------------
    async def handle_narration_step_text(self, narration_text: str):
        """Receive narration text and queue it for speaking."""
        if self._narration_injector and not self._narration_paused:
            await self._narration_injector.inject_narration(narration_text)
            logger.info(f"📢 Narrating: {narration_text[:60]}...")

    async def speak(self, text: str):
        """Speak arbitrary text through the pipeline."""
        if self._narration_injector:
            await self._narration_injector.inject_narration(text)
            logger.info(f"🔊 Speaking: {text[:60]}...")

    async def pause_narration(self):
        """Pause narration delivery (during Q&A)."""
        self._narration_paused = True
        if self._narration_injector:
            await self._narration_injector.pause()
        logger.info("⏸️  Narration paused")

    async def resume_narration(self):
        """Resume narration delivery."""
        self._narration_paused = False
        if self._narration_injector:
            await self._narration_injector.resume()
        logger.info("▶️  Narration resumed")

    # ------------------------------------------------------------------
    # User Question Handling
    # ------------------------------------------------------------------
    async def handle_user_question(self, question_text: str):
        """User asked a question - pause narration and route to MCP."""
        logger.info(f"❓ User question: {question_text}")

        # Pause current narration
        await self.pause_narration()

        # Try to send question to MCP server
        if self._mcp_ws:
            try:
                await self._mcp_ws.send(json.dumps({
                    "type": "question",
                    "payload": {"question": question_text},
                    "session_id": self.session_id,
                }))
                logger.info("Question sent to MCP server")
                # Answer will come back via _listen_for_mcp_messages
            except Exception as e:
                logger.error(f"Failed to send question to MCP: {e}")
                await self.speak(
                    "Sorry, I couldn't reach the reasoning engine. "
                    "Please try asking again."
                )
        else:
            # Standalone mode - give a generic response
            await self.speak(
                "I heard your question, but I'm not connected to the reasoning "
                "engine right now. The agent will address it when possible."
            )

        # Resume narration after a short delay
        await asyncio.sleep(1.0)
        await self.resume_narration()

    # ------------------------------------------------------------------
    # Main Run Loop
    # ------------------------------------------------------------------
    async def run(self):
        """Main entry point - start the voice agent."""
        self._running = True
        logger.info("🚀 Starting Lock-In Voice Agent...")

        # Build pipeline
        self._setup_pipeline()

        # Start MCP bridge WebSocket server
        await self._start_mcp_bridge()

        # Start narration delivery loop
        if self._narration_injector:
            asyncio.create_task(self._narration_injector.run_narration_loop())

        # Run the Pipecat pipeline
        logger.info(
            f"🎤 Voice agent listening on ws://{self.config.ws_host}:{self.config.ws_port}"
        )

        try:
            runner = PipelineRunner()
            await runner.run(self._task)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean shutdown of all components."""
        self._running = False
        logger.info("Shutting down Lock-In Voice Agent...")

        # Stop narration injector
        if self._narration_injector:
            self._narration_injector.stop()

        # Close MCP bridge server
        if self._mcp_bridge:
            self._mcp_bridge.close()
            await self._mcp_bridge.wait_closed()

        logger.info("✅ Voice agent shutdown complete")


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------
def main():
    """Run the Lock-In voice agent from command line."""
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    logger.add(
        "lock-in.log",
        rotation="10 MB",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    config = get_settings()

    if not config.validate_api_keys():
        logger.error(
            "❌ Missing API keys! Please set CARTESIA_API_KEY and ANTHROPIC_API_KEY in your .env file."
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("🔒 Lock-In: Live Voice Narration of Agent Reasoning")
    logger.info("=" * 60)
    logger.info(f"  Voice: {config.cartesia_voice_id}")
    logger.info(f"  TTS:   {config.tts_model} @ {config.tts_sample_rate}Hz")
    logger.info(f"  STT:   {config.stt_model} @ {config.stt_sample_rate}Hz")
    logger.info(f"  WS:    {config.ws_host}:{config.ws_port}")
    logger.info(f"  LLM:   {config.llm_model}")
    logger.info("=" * 60)

    agent = LockInVoiceAgent(config)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
