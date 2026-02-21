#!/bin/bash
# Lock-In Setup Script
# Sets up the virtual environment, dependencies, and configuration.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "🔒 Lock-In Setup"
echo "========================================"
echo "Project directory: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

# 1. Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   Created: venv/"
else
    echo "   Already exists: venv/"
fi

# Activate
source venv/bin/activate
echo "   Activated: $(which python3)"

# 2. Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "   Done."

# 3. Create .env if not exists
echo ""
echo "⚙️  Checking .env file..."
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# Lock-In Configuration
# =====================

# API Keys (REQUIRED - fill these in!)
CARTESIA_API_KEY=your_cartesia_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Cartesia Voice Configuration
CARTESIA_VOICE_ID=a0e99841-438c-4a64-b679-ae501e7d6091
TTS_MODEL=sonic-3
STT_MODEL=ink-whisper
TTS_SAMPLE_RATE=24000
STT_SAMPLE_RATE=16000

# Server Configuration
WS_HOST=0.0.0.0
WS_PORT=8765
MCP_WS_PORT=8766

# LLM Configuration
LLM_MODEL=claude-sonnet-4-6
LLM_TEMPERATURE=0.7
MAX_NARRATION_LENGTH=150

# Narration Settings
NARRATION_SPEED=1.1
ENABLE_INTERRUPTIONS=true
QUESTION_DETECTION_CONFIDENCE=0.7

# Logging
LOG_LEVEL=INFO
LOG_FILE=lock-in.log

# Development
DEBUG_MODE=false
SAVE_TRACES=true
TRACES_DIR=./traces
ENVEOF
    echo "   Created .env file. ⚠️  Please edit .env and add your API keys!"
else
    echo "   .env already exists."
fi

# 4. Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p traces
mkdir -p logs
echo "   Done."

# 5. Verify installation
echo ""
echo "🔍 Verifying installation..."
python3 -c "
import sys
errors = []
try:
    from pipecat.services.cartesia.tts import CartesiaTTSService
except ImportError as e:
    errors.append(f'pipecat/cartesia: {e}')
try:
    from pipecat.services.anthropic.llm import AnthropicLLMService
except ImportError as e:
    errors.append(f'pipecat/anthropic: {e}')
try:
    from pipecat.services.cartesia.stt import CartesiaSTTService
except ImportError as e:
    errors.append(f'pipecat/cartesia_stt: {e}')
try:
    import pipecat.audio.vad.silero
except ImportError as e:
    errors.append(f'pipecat/silero: {e}')
try:
    from pipecat.transports.websocket.server import WebsocketServerTransport
except ImportError as e:
    errors.append(f'pipecat/websocket: {e}')
try:
    import websockets
except ImportError as e:
    errors.append(f'websockets: {e}')
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    errors.append(f'mcp: {e}')
try:
    from loguru import logger
except ImportError as e:
    errors.append(f'loguru: {e}')
try:
    from pydantic_settings import BaseSettings
except ImportError as e:
    errors.append(f'pydantic-settings: {e}')

if errors:
    print('   ❌ Some dependencies have issues:')
    for err in errors:
        print(f'      - {err}')
    sys.exit(1)
else:
    print('   ✅ All dependencies verified!')
"

echo ""
echo "========================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your CARTESIA_API_KEY and ANTHROPIC_API_KEY"
echo "  2. Run the voice agent:  ./scripts/run.sh voice"
echo "  3. Run the MCP server:   ./scripts/run.sh mcp"
echo "  4. Run tests:            ./scripts/run.sh test"
echo "  5. Run narration demo:   ./scripts/run.sh demo"
echo "========================================"
