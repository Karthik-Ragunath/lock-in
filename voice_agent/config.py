"""Configuration with Pydantic Settings for Lock-In Voice Agent."""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Lock-In configuration loaded from environment variables and .env file."""

    # API Keys (required)
    cartesia_api_key: str = ""
    anthropic_api_key: str = ""

    # Cartesia Voice Settings
    cartesia_voice_id: str = "a33f7a4c-100f-41cf-a1fd-5822e8fc253f"  # Upbeat voice
    tts_model: str = "sonic-3"
    stt_model: str = "ink-whisper"
    tts_sample_rate: int = 44100  # CD quality - recommended for clean audio
    stt_sample_rate: int = 16000

    # WebSocket Settings
    ws_host: str = "0.0.0.0"
    ws_port: int = 8765
    mcp_ws_port: int = 8766

    # LLM Settings
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.7
    max_narration_length: int = 150  # characters

    # Narration Settings
    narration_speed: float = 1.1  # Slightly faster for efficiency
    enable_interruptions: bool = True
    question_detection_confidence: float = 0.7

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "lock-in.log"

    # Development
    debug_mode: bool = False
    save_traces: bool = True
    traces_dir: str = "./traces"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def validate_api_keys(self) -> bool:
        """Check that required API keys are set."""
        if not self.cartesia_api_key or self.cartesia_api_key == "your_cartesia_api_key_here":
            return False
        if not self.anthropic_api_key or self.anthropic_api_key == "your_anthropic_api_key_here":
            return False
        return True


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
