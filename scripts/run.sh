#!/bin/bash
# Lock-In Run Script
# Runs different components of the Lock-In system.
#
# Usage:
#   ./scripts/run.sh voice     - Start the voice agent
#   ./scripts/run.sh mcp       - Start the MCP server (stdio mode)
#   ./scripts/run.sh both      - Start both (voice agent + MCP server)
#   ./scripts/run.sh test      - Run tests
#   ./scripts/run.sh demo      - Run narration demo
#   ./scripts/run.sh lint      - Run linters

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "❌ Virtual environment not found. Run ./scripts/setup.sh first."
    exit 1
fi

# Load .env
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

COMMAND="${1:-help}"

case "$COMMAND" in

    voice)
        echo "🎤 Starting Lock-In Voice Agent..."
        echo "   WebSocket: ws://0.0.0.0:${WS_PORT:-8765}"
        echo ""
        PYTHONPATH="$PROJECT_DIR" python3 -m voice_agent.agent
        ;;

    mcp)
        echo "🔧 Starting Lock-In MCP Server (stdio mode for Cursor)..."
        echo ""
        MCP_TRANSPORT=stdio PYTHONPATH="$PROJECT_DIR" python3 -m mcp_server.server
        ;;

    mcp-http)
        MCP_PORT="${2:-8000}"
        echo "🌐 Starting Lock-In MCP Server (HTTP mode for ChatGPT/Claude)..."
        echo "   MCP endpoint: http://localhost:${MCP_PORT}/mcp"
        echo "   Inspector:    http://localhost:${MCP_PORT}/inspector"
        echo ""
        MCP_TRANSPORT=streamable-http MCP_SERVER_PORT="$MCP_PORT" PYTHONPATH="$PROJECT_DIR" python3 -m mcp_server.server
        ;;

    both)
        echo "🚀 Starting Lock-In (Voice Agent + MCP Server)..."
        echo ""

        # Start MCP server in background
        echo "Starting MCP server..."
        PYTHONPATH="$PROJECT_DIR" python3 -m mcp_server.server &
        MCP_PID=$!
        echo "   MCP server PID: $MCP_PID"

        # Give MCP server time to start
        sleep 2

        # Start voice agent in foreground
        echo "Starting voice agent..."
        PYTHONPATH="$PROJECT_DIR" python3 -m voice_agent.agent

        # Clean up MCP server on exit
        kill $MCP_PID 2>/dev/null || true
        ;;

    all)
        echo "🚀 Starting Lock-In (Voice Agent + MCP Server + Audio Client)..."
        echo ""
        CLIENT_PORT="${2:-8080}"
        # Get local IP (works on both macOS and Linux)
        if command -v ipconfig &> /dev/null; then
            HOST_IP="$(ipconfig getifaddr en0 2>/dev/null || echo 'localhost')"
        else
            HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
        fi

        # Start audio client HTTP server in background
        echo "Starting audio client on port ${CLIENT_PORT}..."
        (cd "$PROJECT_DIR/audio_client" && python3 -m http.server "$CLIENT_PORT" --bind 0.0.0.0 > /dev/null 2>&1) &
        CLIENT_PID=$!
        echo "   Audio client PID: $CLIENT_PID"
        echo "   Open: http://${HOST_IP}:${CLIENT_PORT}"

        # Start MCP server in background
        echo "Starting MCP server..."
        PYTHONPATH="$PROJECT_DIR" python3 -m mcp_server.server &
        MCP_PID=$!
        echo "   MCP server PID: $MCP_PID"

        sleep 2

        # Start voice agent in foreground
        echo "Starting voice agent..."
        PYTHONPATH="$PROJECT_DIR" python3 -m voice_agent.agent

        # Clean up on exit
        kill $MCP_PID 2>/dev/null || true
        kill $CLIENT_PID 2>/dev/null || true
        ;;

    test)
        echo "🧪 Running Lock-In tests..."
        echo ""
        PYTHONPATH="$PROJECT_DIR" python3 -m pytest tests/ -v --tb=short -x
        ;;

    test-coverage)
        echo "🧪 Running Lock-In tests with coverage..."
        echo ""
        PYTHONPATH="$PROJECT_DIR" python3 -m pytest tests/ -v --tb=short --cov=mcp_server --cov=voice_agent --cov-report=term-missing
        ;;

    demo)
        echo "🎤 Running Lock-In Narration Demo..."
        echo ""
        PYTHONPATH="$PROJECT_DIR" python3 examples/test_narration.py
        ;;

    demo-trace)
        TRACE_FILE="${2:-examples/example_traces.json}"
        echo "🎤 Running Lock-In Narration Demo (Trace: $TRACE_FILE)..."
        echo ""
        PYTHONPATH="$PROJECT_DIR" python3 examples/test_narration.py --trace-file "$TRACE_FILE"
        ;;

    client)
        CLIENT_PORT="${2:-8080}"
        # Get local IP (works on both macOS and Linux)
        if command -v ipconfig &> /dev/null; then
            # macOS
            HOST_IP="$(ipconfig getifaddr en0 2>/dev/null || echo 'localhost')"
        else
            # Linux
            HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
        fi
        echo "🔊 Serving Lock-In Audio Client..."
        echo "   Open: http://localhost:${CLIENT_PORT}"
        echo "   (or http://${HOST_IP}:${CLIENT_PORT} from another machine)"
        echo ""
        cd "$PROJECT_DIR/audio_client"
        python3 -m http.server "$CLIENT_PORT" --bind 0.0.0.0
        ;;

    lint)
        echo "🔍 Running linters..."
        echo ""
        echo "--- Black (formatter) ---"
        python3 -m black --check mcp_server/ voice_agent/ tests/ || true
        echo ""
        echo "--- Flake8 ---"
        python3 -m flake8 mcp_server/ voice_agent/ tests/ --max-line-length=120 --ignore=E501,W503 || true
        echo ""
        echo "--- MyPy ---"
        python3 -m mypy mcp_server/ voice_agent/ --ignore-missing-imports || true
        ;;

    format)
        echo "✨ Formatting code..."
        python3 -m black mcp_server/ voice_agent/ tests/
        ;;

    help|*)
        echo "========================================"
        echo "🔒 Lock-In - Voice Narration System"
        echo "========================================"
        echo ""
        echo "Usage: ./scripts/run.sh <command>"
        echo ""
        echo "Commands:"
        echo "  voice          Start the voice agent"
        echo "  mcp            Start the MCP server (stdio mode for Cursor)"
        echo "  mcp-http [port] Start the MCP server (HTTP mode for ChatGPT/Claude, default: 8000)"
        echo "  both           Start voice agent + MCP server (stdio)"
        echo "  all [port]     Start everything + audio client (default port: 8080)"
        echo "  test           Run tests"
        echo "  test-coverage  Run tests with coverage report"
        echo "  demo           Run narration demo"
        echo "  demo-trace     Run narration demo with trace file"
        echo "  lint           Run linters"
        echo "  client [port]  Serve the audio client (default port: 8080)"
        echo "  format         Format code with Black"
        echo "  help           Show this help message"
        echo ""
        ;;
esac
