# Gitleaks MCP-Ollama Portal

## 🎉 Portal is Running!

Your MCP-Ollama portal is now active and ready to use.

## 🌐 Access the Portal

Open your browser and navigate to:
- **http://localhost:5001**

Or access from other devices on your network:
- **http://10.86.184.1:5001**

## ✨ Features

### Available MCP Tools (5)
1. **gitleaks_scan_repo** - Scan git repositories for secrets
2. **gitleaks_scan_dir** - Scan directories without git history
3. **gitleaks_detect** - Quick scan text content for secrets
4. **get_scan_results** - Retrieve previous scan results
5. **list_active_scans** - Show currently running scans

### AI Models (via Ollama)
- Select from available Ollama models in the sidebar
- Default: llama3.2

## 💬 How to Use

### Chat Interface
Simply type natural language requests like:
- "Scan the repository at /Users/B0024335/code/my-project"
- "Check this code for secrets: [paste your code]"
- "List all active scans"
- "Show me the results from scan abc123"

### Quick Actions
- Click any tool button in the sidebar to populate the chat input
- Modify the prompt as needed

### Direct API Access

#### Chat Endpoint
```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Scan /path/to/repo for secrets",
    "model": "llama3.2"
  }'
```

#### Direct Scan (No AI)
```bash
curl -X POST http://localhost:5001/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "gitleaks_scan_dir",
    "arguments": {"dir_path": "/path/to/directory"}
  }'
```

#### List Models
```bash
curl http://localhost:5001/api/models
```

#### List Tools
```bash
curl http://localhost:5001/api/tools
```

#### Check Status
```bash
curl http://localhost:5001/api/status
```

## 🚀 Starting/Stopping

### Start
```bash
cd /Users/B0024335/code/git_leaks
./start_portal.sh
```

Or manually:
```bash
cd /Users/B0024335/code/git_leaks
GITLEAKS_OUTPUT_DIR=/Users/B0024335/code/git_leaks/output \
  .venv/bin/python portal.py
```

### Stop
Press `CTRL+C` in the terminal where the portal is running

## 📊 Architecture

```
Browser/Client
      ↓
Flask Web Portal (port 5001)
      ↓
   ┌──┴──┐
   ↓     ↓
Ollama  Gitleaks MCP Server
(AI)    (Security Scanning)
```

1. **Frontend**: Beautiful web UI with real-time chat
2. **Backend**: Flask server managing connections
3. **AI**: Ollama models for natural language processing
4. **MCP Server**: Gitleaks security scanning tools

## 🔧 Configuration

### Environment Variables
- `GITLEAKS_OUTPUT_DIR`: Where scan results are stored
- `GITLEAKS_TIMEOUT`: Scan timeout (default: 300s)
- `GITLEAKS_MAX_CONCURRENT`: Max concurrent scans (default: 2)

### Adding More Ollama Models
```bash
ollama pull mistral
ollama pull codellama
ollama pull llama3.1
```

## 📝 Example Conversations

**User**: "Can you scan my project at /Users/B0024335/code/myapp for secrets?"

**AI**: *Uses gitleaks_scan_dir tool, then responds with findings*

---

**User**: "Check this environment file for leaked credentials:
```
API_KEY=sk_live_12345abcde
DB_PASSWORD=super_secret_123
```
"

**AI**: *Uses gitleaks_detect tool, identifies the secrets*

---

**User**: "Show me all active scans"

**AI**: *Uses list_active_scans tool, displays status*

## 🛡️ Security Notes

- The portal runs on your local machine
- MCP server only scans local files/repositories
- Secrets are automatically masked in output (first 4 chars visible)
- Always get authorization before scanning repositories
- Scan results stored in: `/Users/B0024335/code/git_leaks/output`

## 🐛 Troubleshooting

### Ollama Connection Issues
```bash
# Check if Ollama is running
pgrep ollama

# Start Ollama
ollama serve
```

### MCP Server Issues
Check logs in the terminal where portal.py is running

### Port Already in Use
Edit `portal.py` and change port 5001 to another port

## 📚 Learn More

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
- [Ollama](https://ollama.ai/)
