"""Pipecat Pipeline Setup - Build the voice processing pipeline for Lock-In."""

import asyncio
from typing import Optional

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TTSSpeakFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.cartesia.stt import CartesiaLiveOptions, CartesiaSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.transports.websocket.server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

from .config import Settings


class NarrationInjector(FrameProcessor):
    """
    Custom processor that injects narration text into the pipeline.
    
    Receives narration text from the MCP server (via the voice agent) and
    pushes TextFrames into the pipeline for TTS synthesis.
    """

    def __init__(self, name: str = "NarrationInjector"):
        super().__init__(name=name)
        self._narration_queue: asyncio.Queue[str] = asyncio.Queue()
        self._paused = False
        self._running = True

    async def inject_narration(self, text: str):
        """Queue narration text for speaking."""
        if not self._paused:
            await self._narration_queue.put(text)
            logger.debug(f"Narration queued: {text[:50]}...")

    async def pause(self):
        """Pause narration delivery (for user questions)."""
        self._paused = True
        logger.info("Narration paused")

    async def resume(self):
        """Resume narration delivery."""
        self._paused = False
        logger.info("Narration resumed")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames - pass through and check for queued narrations."""
        await super().process_frame(frame, direction)
        # Pass through all incoming frames
        await self.push_frame(frame, direction)

    async def run_narration_loop(self):
        """Background loop that delivers queued narrations to TTS."""
        while self._running:
            try:
                text = await asyncio.wait_for(
                    self._narration_queue.get(), timeout=0.5
                )
                if not self._paused and text.strip():
                    frame = TTSSpeakFrame(text=text)
                    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
                    logger.debug(f"Narration sent to TTS: {text[:50]}...")
                elif self._paused:
                    # Re-queue if paused
                    await self._narration_queue.put(text)
                    await asyncio.sleep(0.2)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Narration loop error: {e}")
                await asyncio.sleep(0.1)

    def stop(self):
        """Stop the narration loop."""
        self._running = False


class UserQuestionHandler(FrameProcessor):
    """
    Custom processor that detects user questions from STT transcriptions.
    
    Listens for TranscriptionFrames and routes detected questions
    to the voice agent for answering via the MCP server.
    """

    def __init__(
        self,
        on_question_callback=None,
        name: str = "UserQuestionHandler",
    ):
        super().__init__(name=name)
        self._on_question = on_question_callback

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames, detect questions from transcriptions."""
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip() if hasattr(frame, "text") else ""
            if text:
                logger.info(f"User said: {text}")
                if self._on_question:
                    try:
                        await self._on_question(text)
                    except Exception as e:
                        logger.error(f"Question callback error: {e}")

        # Pass through all frames
        await self.push_frame(frame, direction)


def build_pipeline(
    config: Settings,
    on_question_callback=None,
) -> tuple:
    """
    Build the complete Pipecat voice pipeline.
    
    Args:
        config: Application settings.
        on_question_callback: Async callback when user asks a question.
    
    Returns:
        Tuple of (transport, pipeline_task, narration_injector).
    """
    logger.info("Building Pipecat pipeline...")

    # ----- Transport (WebSocket) -----
    transport = WebsocketServerTransport(
        params=WebsocketServerParams(
            audio_in_enabled=True,
            audio_in_sample_rate=config.stt_sample_rate,
            audio_out_enabled=True,
            audio_out_sample_rate=config.tts_sample_rate,
            serializer=ProtobufFrameSerializer(),
        ),
        host=config.ws_host,
        port=config.ws_port,
    )

    # ----- STT (Cartesia) -----
    stt = CartesiaSTTService(
        api_key=config.cartesia_api_key,
        sample_rate=config.stt_sample_rate,
        live_options=CartesiaLiveOptions(
            model=config.stt_model,
            language="en",
        ),
    )

    # ----- TTS (Cartesia) -----
    tts = CartesiaTTSService(
        api_key=config.cartesia_api_key,
        voice_id=config.cartesia_voice_id,
        model=config.tts_model,
        sample_rate=config.tts_sample_rate,
        encoding="pcm_s16le",
    )

    # ----- LLM (Anthropic - for Q&A responses) -----
    llm = AnthropicLLMService(
        api_key=config.anthropic_api_key,
        model=config.llm_model,
    )

    # ----- Custom processors -----
    narration_injector = NarrationInjector()
    question_handler = UserQuestionHandler(
        on_question_callback=on_question_callback,
    )

    # ----- Pipeline assembly -----
    pipeline = Pipeline(
        [
            transport.input(),   # Audio from user's microphone
            stt,                 # Speech-to-text
            question_handler,    # Detect user questions
            narration_injector,  # Inject narration text
            tts,                 # Text-to-speech
            transport.output(),  # Audio to user's speakers
        ]
    )

    # ----- Pipeline task -----
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=config.enable_interruptions,
            audio_in_sample_rate=config.stt_sample_rate,
            audio_out_sample_rate=config.tts_sample_rate,
        ),
        idle_timeout_secs=None,
    )

    logger.info(
        f"Pipeline built: STT({config.stt_model}) → "
        f"QuestionHandler → NarrationInjector → "
        f"TTS({config.tts_model}) "
        f"[WS: {config.ws_host}:{config.ws_port}]"
    )

    return transport, task, narration_injector
