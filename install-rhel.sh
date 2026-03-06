#!/bin/bash
# RHEL Installation Script for Gitleaks MCP Server
# Supports RHEL 8 and RHEL 9

set -e

echo "============================================"
echo "Gitleaks MCP Server - RHEL Installation"
echo "============================================"
echo ""

# Detect RHEL version
if [ -f /etc/redhat-release ]; then
    RHEL_VERSION=$(grep -oE '[0-9]+' /etc/redhat-release | head -1)
    echo "✓ Detected RHEL version: $RHEL_VERSION"
else
    echo "⚠️  Warning: Not a RHEL system, continuing anyway..."
    RHEL_VERSION="unknown"
fi

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Running as root. Will create service user."
    RUN_AS_ROOT=true
else
    echo "✓ Running as regular user"
    RUN_AS_ROOT=false
fi

echo ""
echo "Step 1: Installing system dependencies..."
echo "============================================"

if $RUN_AS_ROOT; then
    # Install EPEL
    dnf install -y epel-release 2>/dev/null || true
    
    # Update system
    dnf update -y
    
    # Determine Python package based on RHEL version
    if [ "$RHEL_VERSION" = "9" ]; then
        PYTHON_PKG="python3.11"
    else
        PYTHON_PKG="python39"
    fi
    
    # Install packages
    dnf install -y \
        $PYTHON_PKG \
        ${PYTHON_PKG}-pip \
        ${PYTHON_PKG}-devel \
        git \
        curl \
        wget \
        tar \
        gzip \
        gcc \
        gcc-c++ \
        make
    
    echo "✓ System packages installed"
else
    echo "ℹ️  Skipping system package installation (requires sudo/root)"
    echo "   Please ensure Python 3.9+, git, and curl are installed"
    
    # Check for required commands
    for cmd in python3 git curl; do
        if ! command -v $cmd &> /dev/null; then
            echo "❌ Error: $cmd is not installed"
            exit 1
        fi
    done
fi

echo ""
echo "Step 2: Installing Gitleaks..."
echo "============================================"

GITLEAKS_VERSION="8.21.2"
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then ARCH="x64"; fi
if [ "$ARCH" = "aarch64" ]; then ARCH="arm64"; fi

if ! command -v gitleaks &> /dev/null; then
    echo "Downloading Gitleaks v${GITLEAKS_VERSION}..."
    cd /tmp
    curl -sL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${ARCH}.tar.gz" | tar xz
    
    if $RUN_AS_ROOT; then
        mv gitleaks /usr/local/bin/
        chmod +x /usr/local/bin/gitleaks
    else
        mkdir -p ~/.local/bin
        mv gitleaks ~/.local/bin/
        chmod +x ~/.local/bin/gitleaks
        export PATH="$HOME/.local/bin:$PATH"
        echo "ℹ️  Add ~/.local/bin to your PATH: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    fi
    
    gitleaks version
    echo "✓ Gitleaks installed successfully"
else
    echo "✓ Gitleaks already installed: $(gitleaks version)"
fi

echo ""
echo "Step 3: Setting up Python virtual environment..."
echo "============================================"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Determine Python command
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.9 &> /dev/null; then
    PYTHON_CMD="python3.9"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ Error: Python 3.9+ not found"
    exit 1
fi

echo "Using Python: $($PYTHON_CMD --version)"

# Create virtual environment
if [ -d ".venv" ]; then
    echo "Virtual environment already exists, removing..."
    rm -rf .venv
fi

$PYTHON_CMD -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

echo "✓ Virtual environment created"

echo ""
echo "Step 4: Installing Python dependencies..."
echo "============================================"

# Install server dependencies
echo "Installing server dependencies..."
pip install -r requirements.txt

# Install portal dependencies
echo "Installing portal dependencies..."
pip install -r portal_requirements.txt

echo "✓ Python dependencies installed"

echo ""
echo "Step 5: Creating directories..."
echo "============================================"

mkdir -p output
chmod 755 output
echo "✓ Output directory created: $SCRIPT_DIR/output"

echo ""
echo "Step 6: Creating configuration file..."
echo "============================================"

if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2

# Gitleaks Configuration
GITLEAKS_OUTPUT_DIR=./output
GITLEAKS_TIMEOUT=300
GITLEAKS_MAX_CONCURRENT=2
EOF
    echo "✓ Configuration file created: .env"
else
    echo "ℹ️  Configuration file already exists: .env"
fi

echo ""
echo "Step 7: Installing Ollama (optional)..."
echo "============================================"

if command -v ollama &> /dev/null; then
    echo "✓ Ollama already installed: $(ollama --version)"
else
    read -p "Install Ollama? (required for portal) [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        
        if $RUN_AS_ROOT; then
            systemctl enable ollama
            systemctl start ollama
            echo "✓ Ollama service enabled and started"
        else
            echo "ℹ️  Start Ollama with: ollama serve"
        fi
        
        # Pull default model
        echo "Pulling default model (llama3.2)..."
        ollama pull llama3.2 || echo "⚠️  Failed to pull model, you can do this later"
    fi
fi

echo ""
echo "Step 8: Making scripts executable..."
echo "============================================"

chmod +x start_portal.sh
echo "✓ Scripts are now executable"

echo ""
echo "============================================"
echo "Installation Complete!"
echo "============================================"
echo ""
echo "To start the portal:"
echo "  1. Activate the virtual environment: source .venv/bin/activate"
echo "  2. Run the startup script: ./start_portal.sh"
echo ""
echo "Or to run as systemd service (requires root):"
echo "  See RHEL_SETUP.md for instructions"
echo ""
echo "Configuration file: .env"
echo "Output directory: $SCRIPT_DIR/output"
echo ""
echo "For more details, see RHEL_SETUP.md"
echo ""
