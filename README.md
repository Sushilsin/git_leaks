# Gitleaks MCP Toolkit

Repository: https://github.com/Sushilsin/git_leaks/

Security toolkit for secret detection with three components:

- `server.py`: MCP server wrapping [Gitleaks](https://github.com/gitleaks/gitleaks)
- `portal.py`: Flask web portal with Ollama-powered chat + tool calling
- `github_secret_search.py`: standalone GitHub commit/code search scanner

## MCP Tools

| Tool | Description |
|------|-------------|
| `gitleaks_scan_repo` | Scan a local git repository including commit history |
| `gitleaks_scan_remote_repo` | Clone and scan a remote repository (public/private) |
| `gitleaks_scan_dir` | Scan a directory without git history |
| `gitleaks_detect` | Quick scan text content for secrets |
| `get_scan_results` | Retrieve previous scan results by scan ID |
| `list_active_scans` | Show currently running scans |

## Quick Start (Local Portal)

1. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r portal_requirements.txt
```

2. Ensure prerequisites are installed and running:

- `gitleaks` available in `PATH`
- `ollama` running (`ollama serve`)

3. Start the portal:

```bash
./start_portal.sh
```

4. Open:

- `http://localhost:5001`

5. Optional smoke test:

```bash
python3 test_api.py
```

## Ollama Integration and Configuration

The portal uses Ollama for model inference and tool-call orchestration.

How Ollama is included:

- `portal.py` creates an Ollama client from `OLLAMA_HOST`
- `start_portal.sh` sets defaults and starts Ollama if needed
- the portal loads available models dynamically from Ollama
- chat requests to `/api/chat` run through the selected Ollama model

Default configuration:

- `OLLAMA_HOST=http://localhost:11434`
- `OLLAMA_DEFAULT_MODEL=llama3.2`

Configure with environment variables:

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_DEFAULT_MODEL=llama3.2
./start_portal.sh
```

Or use a `.env` file (loaded by `start_portal.sh`):

```bash
cp .env.example .env
```

Then add/update values in `.env`:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2
GITLEAKS_OUTPUT_DIR=./output
```

Remote Ollama configuration:

```bash
export OLLAMA_HOST=http://<ollama-server-ip>:11434
./start_portal.sh
```

Useful verification endpoints:

- `GET /api/models`: list models visible to the portal
- `GET /api/status`: confirms `ollama_available` and active host
- `GET /api/config`: returns active portal configuration
- `POST /api/test-ollama`: test a custom Ollama host

## Direct API Endpoints

- `GET /api/status`: portal, MCP, and Ollama status
- `GET /api/models`: available Ollama models
- `GET /api/tools`: available MCP tools
- `POST /api/chat`: chat with model + tool calling
- `POST /api/scan`: direct MCP tool call without chat

Examples:

```bash
curl -s http://localhost:5001/api/status
```

```bash
curl -X POST http://localhost:5001/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "gitleaks_scan_dir",
    "arguments": {"dir_path": "/path/to/project"}
  }'
```

## Docker (MCP Server)

```bash
docker build -t gitleaks-mcp .
docker run -it --rm gitleaks-mcp
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GITLEAKS_OUTPUT_DIR` | `/app/output` | Scan output directory |
| `GITLEAKS_TIMEOUT` | `300` | Default scan timeout (seconds) |
| `GITLEAKS_MAX_CONCURRENT` | `2` | Maximum concurrent scans |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API host |
| `OLLAMA_DEFAULT_MODEL` | `llama3.2` | Default model for chat |

## Standalone GitHub Scanner

For GitHub API-based scanning (separate from MCP), use:

```bash
python3 github_secret_search.py --help
```

Detailed guide: `GITHUB_SECRET_SEARCH.md`

## Security Notes

- Secrets in scan output are masked (first 4 chars visible)
- Only scan repositories/systems you are authorized to test
- Treat output files in `output/` as sensitive data

## License

MIT

