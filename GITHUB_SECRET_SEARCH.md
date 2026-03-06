# GitHub Secret Search

A Python-based security tool that scans GitHub commit history and public code for accidentally leaked secrets — API keys, tokens, passwords, private keys, and more.

> ⚠️ **For authorized security research, red team engagements, and bug bounty hunting only.**  
> Do not use against repositories you do not own or have explicit written permission to test.

---

## Features

- 🔍 **30+ built-in secret patterns** — AWS, GitHub, Stripe, Slack, Google, Twilio, JWT, MongoDB, SSH keys, and more
- 📜 **Commit diff scanning** — walks through commit history and scans every file patch
- 🌐 **GitHub code search** — leverages the GitHub Search API to find files matching keywords, then scans raw content
- ⏱️ **Rate-limit aware** — automatically waits and retries when GitHub throttles requests
- 💾 **JSON output** — structured findings with repo, file path, commit SHA, URL, match, and timestamp

---

## Requirements

- Python 3.9+
- `requests` library

```bash
pip install requests
```

---

## Usage

```bash
python3 github_secret_search.py [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--repo owner/name` | Scan commits of a specific GitHub repo | — |
| `--query "..."` | GitHub code search query to find potential secret files | — |
| `--token ghp_xxx` | GitHub personal access token (highly recommended) | — |
| `--commits N` | Max number of commits to scan per repo | `50` |
| `--results N` | Max number of code-search results to process | `50` |
| `--output file.json` | Output file for findings | `secret_findings.json` |
| `--patterns` | List all built-in secret patterns and exit | — |

> At least one of `--repo` or `--query` is required.

---

## Examples

### Scan commits of a specific repository
```bash
python3 github_secret_search.py \
  --repo octocat/Hello-World \
  --token ghp_yourTokenHere
```

### Search GitHub for hardcoded API keys in Python files
```bash
python3 github_secret_search.py \
  --query "api_key language:python" \
  --token ghp_yourTokenHere
```

### Scan a repo AND run a keyword search, save results
```bash
python3 github_secret_search.py \
  --repo myorg/myapp \
  --query "password db_pass" \
  --token ghp_yourTokenHere \
  --output findings.json
```

### List all built-in detection patterns
```bash
python3 github_secret_search.py --patterns
```

---

## Built-in Secret Patterns

| Pattern | Example Match |
|---------|---------------|
| AWS Access Key | `AKIAIOSFODNN7EXAMPLE` |
| AWS Secret Key | `aws_secret = "wJalrXUtn..."` |
| GitHub Token | `ghp_16C7e42F292c6912E7710c838347Ae178B4a` |
| GitHub OAuth | `gho_...` |
| GitHub Actions | `ghs_...` |
| Slack Token | `xoxb-...` |
| Slack Webhook | `https://hooks.slack.com/services/T.../B.../...` |
| Stripe Live Key | `sk_live_...` |
| Stripe Test Key | `sk_test_...` |
| Twilio Account SID | `AC1234...` |
| Twilio Auth Token | `twilio_token = "abc123..."` |
| Google API Key | `AIzaSy...` |
| Firebase URL | `https://myapp.firebaseio.com` |
| Heroku API Key | `heroku_key: 12345678-...` |
| Private Key (PEM) | `-----BEGIN RSA PRIVATE KEY-----` |
| SSH Private Key | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| Generic Password | `password = "hunter2"` |
| Generic Secret | `client_secret = "abc..."` |
| Generic API Key | `api_key = "abc123xyz"` |
| Bearer Token | `Authorization: Bearer eyJ...` |
| Basic Auth (URL) | `https://user:pass@host.com` |
| JWT Token | `eyJhbGciOiJIUzI1NiJ9...` |
| MongoDB URI | `mongodb+srv://user:pass@cluster` |
| Telegram Bot Token | `123456789:AAF...` |
| Mailgun API Key | `key-1234567890abcdef` |
| SendGrid API Key | `SG.xxx.yyy` |
| DigitalOcean Token | `dop_v1_...` |
| NPM Token | `npm_...` |
| PyPI Token | `pypi-...` |
| Vault Token | `s.xxxxxxxx` |

---

## Output Format

Findings are printed to the console in real time and saved to a JSON file:

```json
[
  {
    "source": "commit",
    "repo": "owner/reponame",
    "sha": "a1b2c3d4e5f6",
    "file": "config/settings.py",
    "url": "https://github.com/owner/reponame/commit/a1b2c3...",
    "type": "AWS Access Key",
    "match": "AKIAIOSFODNN7EXAMPLE",
    "timestamp": "2024-03-01T12:00:00Z"
  }
]
```

---

## GitHub Token Setup

A personal access token increases your rate limit from **60 req/hour** (unauthenticated) to **5,000 req/hour**.

1. Go to **GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens**
2. Generate a token with **read-only public repository** access
3. Pass it via `--token ghp_yourtoken`

Or set it as an environment variable to avoid typing it each time:

```bash
export GITHUB_TOKEN=ghp_yourtoken
python3 github_secret_search.py --repo owner/repo --token $GITHUB_TOKEN
```

---

## Rate Limiting

| Auth State | Requests/Hour |
|------------|--------------|
| Unauthenticated | 60 |
| Authenticated (token) | 5,000 |
| GitHub Search API | 30 searches/min |

The tool automatically detects rate limit responses and waits until the window resets.

---

## Disclaimer

This tool is intended for:
- Security professionals auditing their own organization's repositories
- Bug bounty hunters operating within scope
- Developers checking their own repos for accidental secret exposure

**Unauthorized scanning of private or third-party repositories may violate GitHub's Terms of Service and applicable computer crime laws.**
