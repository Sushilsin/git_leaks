# Ollama Configuration Guide

## ✅ What's New

The portal now:
- **Auto-detects** all installed Ollama models
- **Configurable** Ollama API endpoint
- **Refresh button** to reload models without restart
- **Environment variables** for easy configuration

## 🔧 Configuration Options

### Environment Variables

Create a `.env` file in the project directory:

```bash
# Ollama API Configuration
OLLAMA_HOST=http://localhost:11434          # Ollama API endpoint
OLLAMA_DEFAULT_MODEL=llama3.2               # Default model to use

# Gitleaks Configuration
GITLEAKS_OUTPUT_DIR=./output                # Scan results directory
GITLEAKS_TIMEOUT=300                        # Scan timeout (seconds)
GITLEAKS_MAX_CONCURRENT=2                   # Max concurrent scans

# Portal Configuration
PORTAL_HOST=0.0.0.0                         # Server host
PORTAL_PORT=5001                            # Server port
```

### Using Custom Ollama Host

#### Local Ollama (default)
```bash
OLLAMA_HOST=http://localhost:11434
```

#### Remote Ollama Server
```bash
OLLAMA_HOST=http://192.168.1.100:11434
```

#### Different Port
```bash
OLLAMA_HOST=http://localhost:8080
```

## 📥 Installing Models

The portal automatically detects all installed models. To add more:

```bash
# Popular models
ollama pull llama3.2
ollama pull llama3.1
ollama pull mistral
ollama pull codellama
ollama pull gemma
ollama pull phi3

# Specialized models
ollama pull deepseek-coder
ollama pull solar
ollama pull qwen
```

## 🔄 Using the Refresh Feature

1. **Install a new model** while the portal is running:
   ```bash
   ollama pull mistral
   ```

2. **Click "🔄 Refresh Models"** in the portal sidebar

3. **Select the new model** from the dropdown

No restart needed!

## 🚀 Starting with Custom Configuration

### Method 1: Environment Variables
```bash
cd /Users/B0024335/code/git_leaks
OLLAMA_HOST=http://localhost:11434 \
OLLAMA_DEFAULT_MODEL=mistral \
./.venv/bin/python portal.py
```

### Method 2: Using .env file
```bash
# Create .env file
cp .env.example .env

# Edit .env with your settings
nano .env

# Start portal (loads .env automatically)
./start_portal.sh
```

### Method 3: Export Variables
```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_DEFAULT_MODEL=llama3.2
./start_portal.sh
```

## 🌐 Remote Ollama Setup

### On Ollama Server
```bash
# Start Ollama with network access
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

### On Portal Machine
```bash
# Configure to use remote server
OLLAMA_HOST=http://remote-server-ip:11434 \
./.venv/bin/python portal.py
```

## 🔍 Checking Available Models

### Via API
```bash
curl http://localhost:5001/api/models
```

Response:
```json
{
  "success": true,
  "models": [
    "llama3.2:latest",
    "mistral:latest",
    "codellama:latest"
  ],
  "default": "llama3.2:latest",
  "host": "http://localhost:11434"
}
```

### Via Ollama CLI
```bash
ollama list
```

## 📊 Status Endpoint

Check portal and Ollama status:

```bash
curl http://localhost:5001/api/status
```

Response:
```json
{
  "success": true,
  "status": "running",
  "mcp_connected": true,
  "ollama_available": true,
  "ollama_host": "http://localhost:11434",
  "output_dir": "/Users/B0024335/code/git_leaks/output"
}
```

## 🐛 Troubleshooting

### No Models Showing
```bash
# Check if Ollama is running
pgrep ollama

# Start Ollama if not running
ollama serve

# Check available models
ollama list

# Pull a model if none available
ollama pull llama3.2

# Refresh in portal
# Click "🔄 Refresh Models" button
```

### Connection Error
```bash
# Check Ollama is accessible
curl http://localhost:11434/api/tags

# Check configured host
curl http://localhost:5001/api/config

# Verify environment variable
echo $OLLAMA_HOST
```

### Wrong Default Model
```bash
# Set default model
export OLLAMA_DEFAULT_MODEL=mistral

# Or edit .env file
echo "OLLAMA_DEFAULT_MODEL=mistral" >> .env

# Restart portal
./start_portal.sh
```

## 💡 Pro Tips

1. **Pre-load models** before starting for faster startup
2. **Use .env file** for persistent configuration
3. **Use refresh button** when adding models - no restart needed
4. **Check status endpoint** to verify Ollama connectivity
5. **Use remote Ollama** for better resource management

## 🔐 Security Notes

- Ollama API has no authentication by default
- Only expose Ollama to trusted networks
- Use firewall rules for remote access
- Consider using reverse proxy with auth for production

## 📝 Example Configurations

### Development (Local)
```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2
PORTAL_PORT=5001
PORTAL_DEBUG=true
```

### Production (Remote Ollama)
```env
OLLAMA_HOST=http://ollama-server.internal:11434
OLLAMA_DEFAULT_MODEL=mistral
PORTAL_PORT=8080
PORTAL_DEBUG=false
GITLEAKS_MAX_CONCURRENT=5
```

### Team Setup (Shared Ollama)
```env
OLLAMA_HOST=http://shared-ollama.company.com:11434
OLLAMA_DEFAULT_MODEL=codellama
GITLEAKS_TIMEOUT=600
```

## 🚀 Current Status

✅ **Portal Running**: http://localhost:5001  
✅ **Ollama Connected**: http://localhost:11434  
✅ **Auto-detect Models**: Active  
✅ **Refresh Feature**: Enabled  
✅ **MCP Tools**: 5 loaded
