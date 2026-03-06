#!/bin/bash
# Startup script for Gitleaks MCP Portal

echo "🚀 Starting Gitleaks MCP Portal..."
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load environment variables if .env exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "📝 Loading configuration from .env"
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Set defaults
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export OLLAMA_DEFAULT_MODEL="${OLLAMA_DEFAULT_MODEL:-llama3.2}"
export GITLEAKS_OUTPUT_DIR="${GITLEAKS_OUTPUT_DIR:-$SCRIPT_DIR/output}"

# Detect Python virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON_BIN="python3"
fi

# Check if Ollama is running (check both service and process)
OLLAMA_RUNNING=false
if systemctl is-active --quiet ollama 2>/dev/null; then
    OLLAMA_RUNNING=true
elif pgrep -f "ollama serve" > /dev/null 2>&1; then
    OLLAMA_RUNNING=true
fi

if [ "$OLLAMA_RUNNING" = false ]; then
    echo "⚠️  Ollama is not running. Attempting to start..."
    # Try systemd first (RHEL preferred method)
    if systemctl is-enabled --quiet ollama 2>/dev/null; then
        sudo systemctl start ollama
        sleep 3
    else
        # Fallback to manual start
        echo "⚠️  Starting Ollama manually (consider setting up systemd service)..."
        nohup ollama serve > /dev/null 2>&1 &
        sleep 5
    fi
fi

# Check available models
echo "🔍 Checking available models..."
AVAILABLE_MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')

if [ -z "$AVAILABLE_MODELS" ]; then
    echo "📥 No models found. Pulling $OLLAMA_DEFAULT_MODEL (this may take a while)..."
    ollama pull "$OLLAMA_DEFAULT_MODEL"
else
    echo "✅ Found models:"
    echo "$AVAILABLE_MODELS" | while IFS= read -r model; do
        if [ -n "$model" ]; then
            echo "   - $model"
        fi
    done
fi

echo ""
echo "✅ Starting portal..."
echo "🌐 Open your browser to: http://localhost:5001"
echo "🤖 Ollama API: $OLLAMA_HOST"
echo "📁 Output directory: $GITLEAKS_OUTPUT_DIR"
echo "🐍 Python: $PYTHON_BIN"
echo ""

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" portal.py
