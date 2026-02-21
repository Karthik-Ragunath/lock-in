"""Tests for the Lock-In voice agent components."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_agent.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------
class TestSettings:
    """Test the Settings configuration."""

    def test_default_values(self):
        settings = Settings()
        assert settings.tts_model == "sonic-3"
        assert settings.stt_model == "ink-whisper"
        assert settings.tts_sample_rate == 24000
        assert settings.stt_sample_rate == 16000
        assert settings.ws_port == 8765
        assert settings.mcp_ws_port == 8766
        assert settings.narration_speed == 1.1
        assert settings.enable_interruptions is True

    def test_validate_api_keys_missing(self):
        settings = Settings(cartesia_api_key="", anthropic_api_key="")
        assert settings.validate_api_keys() is False

    def test_validate_api_keys_placeholder(self):
        settings = Settings(
            cartesia_api_key="your_cartesia_api_key_here",
            anthropic_api_key="your_anthropic_api_key_here",
        )
        assert settings.validate_api_keys() is False

    def test_validate_api_keys_valid(self):
        settings = Settings(
            cartesia_api_key="sk-real-key-123",
            anthropic_api_key="sk-real-key-456",
        )
        assert settings.validate_api_keys() is True

    def test_cartesia_voice_id_default(self):
        settings = Settings()
        assert settings.cartesia_voice_id == "a0e99841-438c-4a64-b679-ae501e7d6091"

    def test_llm_settings(self):
        settings = Settings()
        assert settings.llm_model == "claude-sonnet-4-6"
        assert settings.llm_temperature == 0.7
        assert settings.max_narration_length == 150

    def test_debug_mode_default(self):
        settings = Settings()
        assert settings.debug_mode is False
        assert settings.save_traces is True

    def test_custom_settings(self):
        settings = Settings(
            ws_port=9000,
            mcp_ws_port=9001,
            log_level="DEBUG",
            debug_mode=True,
        )
        assert settings.ws_port == 9000
        assert settings.mcp_ws_port == 9001
        assert settings.log_level == "DEBUG"
        assert settings.debug_mode is True


# ---------------------------------------------------------------------------
# Pipeline Component Tests (unit-level, no actual audio)
# ---------------------------------------------------------------------------
class TestNarrationInjector:
    """Test the NarrationInjector processor."""

    @pytest.mark.asyncio
    async def test_inject_narration(self):
        from voice_agent.pipeline import NarrationInjector

        injector = NarrationInjector()
        await injector.inject_narration("Hello, I'm analyzing the code")
        assert injector._narration_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_pause_blocks_injection(self):
        from voice_agent.pipeline import NarrationInjector

        injector = NarrationInjector()
        await injector.pause()
        await injector.inject_narration("This should not queue")
        # When paused, narration is not queued
        assert injector._narration_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_resume_allows_injection(self):
        from voice_agent.pipeline import NarrationInjector

        injector = NarrationInjector()
        await injector.pause()
        await injector.resume()
        await injector.inject_narration("This should queue")
        assert injector._narration_queue.qsize() == 1

    def test_stop(self):
        from voice_agent.pipeline import NarrationInjector

        injector = NarrationInjector()
        injector.stop()
        assert injector._running is False


class TestUserQuestionHandler:
    """Test the UserQuestionHandler processor."""

    def test_creation_with_callback(self):
        from voice_agent.pipeline import UserQuestionHandler

        callback = AsyncMock()
        handler = UserQuestionHandler(on_question_callback=callback)
        assert handler._on_question is callback

    def test_creation_without_callback(self):
        from voice_agent.pipeline import UserQuestionHandler

        handler = UserQuestionHandler()
        assert handler._on_question is None


# ---------------------------------------------------------------------------
# Voice Agent Tests (mocked, no real audio/WebSocket)
# ---------------------------------------------------------------------------
class TestLockInVoiceAgent:
    """Test the LockInVoiceAgent orchestrator."""

    def test_agent_creation(self):
        from voice_agent.agent import LockInVoiceAgent

        config = Settings(
            cartesia_api_key="test-key",
            anthropic_api_key="test-key",
        )
        agent = LockInVoiceAgent(config)
        assert agent.session_id is not None
        assert agent._running is False

    def test_agent_default_config(self):
        from voice_agent.agent import LockInVoiceAgent

        agent = LockInVoiceAgent()
        assert agent.config is not None
        assert agent.config.ws_port == 8765

    @pytest.mark.asyncio
    async def test_shutdown(self):
        from voice_agent.agent import LockInVoiceAgent

        config = Settings(
            cartesia_api_key="test-key",
            anthropic_api_key="test-key",
        )
        agent = LockInVoiceAgent(config)
        agent._running = True
        await agent.shutdown()
        assert agent._running is False
