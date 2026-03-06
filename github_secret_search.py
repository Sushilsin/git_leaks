#!/usr/bin/env python3
"""
GitHub Secret Scanner - Search for leaked secrets in GitHub commits
Searches commit history for common secret patterns (API keys, tokens, passwords, etc.)
"""

import re
import sys
import json
import time
import argparse
import requests
from datetime import datetime
from urllib.parse import quote

# ─── Secret Patterns ────────────────────────────────────────────────────────

SECRET_PATTERNS = {
    "AWS Access Key":        r"AKIA[0-9A-Z]{16}",
    "AWS Secret Key":        r"(?i)aws(.{0,20})?['\"][0-9a-zA-Z/+]{40}['\"]",
    "GitHub Token":          r"ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82}",
    "GitHub OAuth":          r"gho_[0-9a-zA-Z]{36}",
    "GitHub Actions":        r"ghs_[0-9a-zA-Z]{36}",
    "Slack Token":           r"xox[baprs]-[0-9a-zA-Z\-]{10,48}",
    "Slack Webhook":         r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+",
    "Stripe Live Key":       r"sk_live_[0-9a-zA-Z]{24,}",
    "Stripe Test Key":       r"sk_test_[0-9a-zA-Z]{24,}",
    "Twilio Account SID":    r"AC[a-z0-9]{32}",
    "Twilio Auth Token":     r"(?i)twilio(.{0,20})?['\"][0-9a-f]{32}['\"]",
    "Google API Key":        r"AIza[0-9A-Za-z\-_]{35}",
    "Firebase URL":          r"https://[a-z0-9\-]+\.firebaseio\.com",
    "Heroku API Key":        r"[hH]eroku.{0,30}[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
    "Private Key (PEM)":     r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    "Generic Password":      r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?.{6,}['\"]?",
    "Generic Secret":        r"(?i)(secret|api_secret|client_secret)\s*[:=]\s*['\"]?.{8,}['\"]?",
    "Generic API Key":       r"(?i)(api_key|apikey|api-key)\s*[:=]\s*['\"]?[0-9a-zA-Z\-_]{16,}['\"]?",
    "Bearer Token":          r"[Bb]earer\s+[0-9a-zA-Z\-_\.]{20,}",
    "Basic Auth (URL)":      r"https?://[^:@\s]+:[^@\s]+@[^\s]+",
    "JWT Token":             r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
    "MongoDB URI":           r"mongodb(\+srv)?://[^\s\"']+",
    "SSH Private Key":       r"-----BEGIN OPENSSH PRIVATE KEY-----",
    "Telegram Bot Token":    r"[0-9]{8,10}:[a-zA-Z0-9_-]{35}",
    "Mailgun API Key":       r"key-[0-9a-zA-Z]{32}",
    "SendGrid API Key":      r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
    "DigitalOcean Token":    r"dop_v1_[a-f0-9]{64}",
    "NPM Token":             r"npm_[a-zA-Z0-9]{36}",
    "PyPI Token":            r"pypi-[a-zA-Z0-9_-]{50,}",
    "Vault Token":           r"s\.[a-zA-Z0-9]{24}",
}

# ─── GitHub API Client ───────────────────────────────────────────────────────

class GitHubSecretScanner:
    def __init__(self, token: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHubSecretScanner/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"

        self.findings = []
        self.rate_limit_remaining = 60

    def _get(self, url: str, params: dict = None):
        """Make a GET request with rate limit handling."""
        while True:
            resp = self.session.get(url, params=params)
            self.rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", 0))

            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - int(time.time()), 5)
                print(f"  [!] Rate limited. Waiting {wait}s ...", flush=True)
                time.sleep(wait)
                continue

            if resp.status_code == 422:
                return None  # query too complex / no results

            resp.raise_for_status()
            return resp.json()

    # ── Scan a single patch/diff text ────────────────────────────────────────

    def scan_text(self, text: str) -> list[dict]:
        """Return list of {pattern_name, match} found in text."""
        hits = []
        for name, pattern in SECRET_PATTERNS.items():
            for m in re.finditer(pattern, text):
                val = m.group(0)
                # Skip obvious placeholders
                if re.fullmatch(r"[*x\-_\.]{4,}", val.split("=")[-1].strip(" '\"")):
                    continue
                hits.append({"type": name, "match": val[:120]})
        return hits

    # ── Scan commits in a repo ────────────────────────────────────────────────

    def scan_repo_commits(self, owner: str, repo: str, max_commits: int = 100):
        """Scan recent commits of a repo for secrets."""
        print(f"\n[*] Scanning repo commits: {owner}/{repo}")
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        commits = self._get(url, params={"per_page": min(max_commits, 100)}) or []

        for c in commits:
            sha = c["sha"]
            detail = self._get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}")
            if not detail:
                continue

            for f in detail.get("files", []):
                patch = f.get("patch", "")
                if not patch:
                    continue
                hits = self.scan_text(patch)
                for h in hits:
                    finding = {
                        "source":    "commit",
                        "repo":      f"{owner}/{repo}",
                        "sha":       sha[:12],
                        "file":      f["filename"],
                        "url":       f"https://github.com/{owner}/{repo}/commit/{sha}",
                        "type":      h["type"],
                        "match":     h["match"],
                        "timestamp": c["commit"]["committer"]["date"],
                    }
                    self.findings.append(finding)
                    self._print_finding(finding)

            time.sleep(0.1)  # be polite

    # ── GitHub code search ────────────────────────────────────────────────────

    def search_github(self, query: str, max_results: int = 50):
        """Use GitHub code search to find potential secrets."""
        print(f"\n[*] GitHub code search: {query!r}")
        url = "https://api.github.com/search/code"
        page = 1
        found = 0

        while found < max_results:
            data = self._get(url, params={"q": query, "per_page": 30, "page": page})
            if not data:
                break
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if found >= max_results:
                    break
                # fetch raw file content
                raw_url = item.get("html_url", "").replace(
                    "github.com", "raw.githubusercontent.com"
                ).replace("/blob/", "/")
                try:
                    raw = requests.get(raw_url, timeout=10).text
                except Exception:
                    raw = ""

                hits = self.scan_text(raw or item.get("name", ""))
                for h in hits:
                    finding = {
                        "source":  "code_search",
                        "repo":    item["repository"]["full_name"],
                        "file":    item["path"],
                        "url":     item["html_url"],
                        "type":    h["type"],
                        "match":   h["match"],
                        "sha":     item.get("sha", "")[:12],
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    self.findings.append(finding)
                    self._print_finding(finding)

                found += 1
                time.sleep(0.3)

            if len(items) < 30:
                break
            page += 1
            time.sleep(1)

    # ── Utility ───────────────────────────────────────────────────────────────

    def _print_finding(self, f: dict):
        print(
            f"  \033[91m[FOUND]\033[0m {f['type']}\n"
            f"         Repo : {f['repo']}\n"
            f"         File : {f['file']}\n"
            f"         Match: {f['match']}\n"
            f"         URL  : {f['url']}\n"
        )

    def save_results(self, output_file: str):
        with open(output_file, "w") as fh:
            json.dump(self.findings, fh, indent=2)
        print(f"\n[+] {len(self.findings)} finding(s) saved to {output_file}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Search GitHub commits and code for leaked secrets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan commits in a specific repo
  python3 github_secret_search.py --repo owner/reponame --token ghp_xxx

  # Search all of GitHub for a keyword (requires token)
  python3 github_secret_search.py --query "password db_pass" --token ghp_xxx

  # Scan a repo AND run a keyword search
  python3 github_secret_search.py --repo owner/repo --query "api_key" --token ghp_xxx --output results.json
        """
    )
    parser.add_argument("--repo",    help="Target repo in owner/name format (e.g. octocat/Hello-World)")
    parser.add_argument("--query",   help="GitHub code-search query (e.g. 'api_key language:python')")
    parser.add_argument("--token",   help="GitHub personal access token (increases rate limits)")
    parser.add_argument("--commits", type=int, default=50, help="Max commits to scan per repo (default: 50)")
    parser.add_argument("--results", type=int, default=50, help="Max code-search results (default: 50)")
    parser.add_argument("--output",  default="secret_findings.json", help="Output JSON file (default: secret_findings.json)")
    parser.add_argument("--patterns", action="store_true", help="List all built-in secret patterns and exit")

    args = parser.parse_args()

    if args.patterns:
        print("\nBuilt-in secret patterns:\n")
        for name in SECRET_PATTERNS:
            print(f"  • {name}")
        print()
        sys.exit(0)

    if not args.repo and not args.query:
        parser.print_help()
        sys.exit(1)

    scanner = GitHubSecretScanner(token=args.token)

    try:
        if args.repo:
            parts = args.repo.strip("/").split("/")
            if len(parts) != 2:
                print("[!] --repo must be in owner/name format")
                sys.exit(1)
            scanner.scan_repo_commits(parts[0], parts[1], max_commits=args.commits)

        if args.query:
            scanner.search_github(args.query, max_results=args.results)

    except KeyboardInterrupt:
        print("\n[!] Interrupted.")
    except requests.HTTPError as e:
        print(f"[!] HTTP error: {e}")

    if scanner.findings:
        scanner.save_results(args.output)
    else:
        print("\n[-] No secrets found.")


if __name__ == "__main__":
    main()
