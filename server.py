#!/usr/bin/env python3
"""
Gitleaks MCP Server

A Model Context Protocol server that provides secrets detection
capabilities using Gitleaks.

Tools:
    - gitleaks_scan_repo: Scan a git repository for secrets
    - gitleaks_scan_dir: Scan a directory for secrets
    - gitleaks_detect: Quick scan provided content for secrets
    - get_scan_results: Retrieve previous scan results
    - list_active_scans: Show running scans
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gitleaks-mcp")


class Settings(BaseSettings):
    """Server configuration from environment variables."""

    output_dir: str = Field(default="/app/output", alias="GITLEAKS_OUTPUT_DIR")
    default_timeout: int = Field(default=300, alias="GITLEAKS_TIMEOUT")
    max_concurrent_scans: int = Field(default=2, alias="GITLEAKS_MAX_CONCURRENT")

    class Config:
        env_prefix = "GITLEAKS_"


settings = Settings()


class SecretFinding(BaseModel):
    """Model for a single secret finding."""

    rule_id: str
    description: str | None = None
    secret: str | None = None
    file: str | None = None
    line: int | None = None
    start_column: int | None = None
    end_column: int | None = None
    commit: str | None = None
    author: str | None = None
    email: str | None = None
    date: str | None = None
    message: str | None = None
    fingerprint: str | None = None
    tags: list[str] = []


class ScanResult(BaseModel):
    """Model for scan results."""

    scan_id: str
    target: str
    scan_type: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"
    findings: list[SecretFinding] = []
    stats: dict[str, Any] = {}
    error: str | None = None
    raw_output: str | None = None


# In-memory storage for scan results
scan_results: dict[str, ScanResult] = {}
active_scans: set[str] = set()


def parse_gitleaks_json(output: str) -> list[SecretFinding]:
    """Parse gitleaks JSON output into findings."""
    findings = []

    try:
        data = json.loads(output)
        if isinstance(data, list):
            for item in data:
                finding = SecretFinding(
                    rule_id=item.get("RuleID", "unknown"),
                    description=item.get("Description"),
                    secret=mask_secret(item.get("Secret", "")),
                    file=item.get("File"),
                    line=item.get("StartLine"),
                    start_column=item.get("StartColumn"),
                    end_column=item.get("EndColumn"),
                    commit=item.get("Commit"),
                    author=item.get("Author"),
                    email=item.get("Email"),
                    date=item.get("Date"),
                    message=item.get("Message"),
                    fingerprint=item.get("Fingerprint"),
                    tags=item.get("Tags", []),
                )
                findings.append(finding)
    except json.JSONDecodeError:
        logger.warning("Failed to parse gitleaks JSON output")

    return findings


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask a secret, showing only first few characters."""
    if not secret or len(secret) <= visible_chars:
        return "****"
    return secret[:visible_chars] + "*" * (len(secret) - visible_chars)


async def clone_repository(repo_url: str, auth_token: str | None = None, timeout: int = 300) -> tuple[str | None, str | None]:
    """Clone a remote repository to a temporary directory.
    
    Args:
        repo_url: URL of the repository (GitHub, Bitbucket, etc.)
        auth_token: Optional authentication token for private repos
        timeout: Timeout for clone operation in seconds (default: 300)
        
    Returns:
        Tuple of (cloned_path, error_message)
    """
    temp_dir = tempfile.mkdtemp(prefix="gitleaks_clone_")
    
    try:
        # Inject token into URL if provided
        clone_url = repo_url
        if auth_token:
            # Handle different URL formats
            if "github.com" in repo_url:
                clone_url = re.sub(r"https://", f"https://{auth_token}@", repo_url)
            elif "bitbucket.org" in repo_url:
                clone_url = re.sub(r"https://", f"https://x-token-auth:{auth_token}@", repo_url)
        
        logger.info(f"Cloning repository from {repo_url} to {temp_dir} (timeout: {timeout}s)")
        
        process = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", clone_url, temp_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Use half the total timeout for cloning, leave rest for scanning
        clone_timeout = min(timeout // 2, 300)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=clone_timeout)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Clone failed"
            logger.error(f"Failed to clone repository: {error_msg}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, error_msg
            
        logger.info(f"Successfully cloned repository to {temp_dir}")
        return temp_dir, None
        
    except asyncio.TimeoutError:
        logger.error(f"Repository clone timed out after {clone_timeout}s")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, f"Clone operation timed out (exceeded {clone_timeout} seconds)"
    except Exception as e:
        logger.error(f"Error cloning repository: {str(e)}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, str(e)


async def run_gitleaks_scan(
    target: str,
    scan_type: str = "dir",
    timeout: int | None = None,
    no_git: bool = False,
) -> ScanResult:
    """Execute a gitleaks scan asynchronously."""
    scan_id = str(uuid.uuid4())[:8]
    output_file = Path(settings.output_dir) / f"scan_{scan_id}.json"

    result = ScanResult(
        scan_id=scan_id,
        target=target,
        scan_type=scan_type,
        started_at=datetime.now(),
    )
    scan_results[scan_id] = result
    active_scans.add(scan_id)

    # Build gitleaks command
    cmd = [
        "gitleaks",
        "detect",
        "--source", target,
        "--report-format", "json",
        "--report-path", str(output_file),
        "--exit-code", "0",  # Don't fail on findings
    ]

    if no_git:
        cmd.append("--no-git")

    logger.info(f"Starting gitleaks {scan_type} scan {scan_id} for target: {target}")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=float(timeout or settings.default_timeout),
        )

        result.completed_at = datetime.now()

        # Read output file if exists
        if output_file.exists():
            output_content = output_file.read_text()
            result.raw_output = output_content
            result.findings = parse_gitleaks_json(output_content)
        else:
            # No findings
            result.findings = []

        # Generate stats
        rules_triggered = {}
        for finding in result.findings:
            rule = finding.rule_id
            rules_triggered[rule] = rules_triggered.get(rule, 0) + 1

        files_with_secrets = set(f.file for f in result.findings if f.file)

        result.stats = {
            "total_findings": len(result.findings),
            "unique_rules_triggered": len(rules_triggered),
            "files_with_secrets": len(files_with_secrets),
            "rules_breakdown": rules_triggered,
        }

        result.status = "completed"
        logger.info(f"Scan {scan_id} completed: {len(result.findings)} findings")

        if stderr:
            stderr_text = stderr.decode()
            if "error" in stderr_text.lower():
                logger.warning(f"Scan {scan_id} warnings: {stderr_text}")

    except asyncio.TimeoutError:
        result.status = "timeout"
        result.error = f"Scan timed out after {timeout or settings.default_timeout} seconds"
        result.completed_at = datetime.now()
        logger.error(f"Scan {scan_id} timed out")

    except Exception as e:
        result.status = "error"
        result.error = str(e)
        result.completed_at = datetime.now()
        logger.exception(f"Scan {scan_id} error: {e}")

    finally:
        active_scans.discard(scan_id)
        scan_results[scan_id] = result

    return result


async def scan_content(content: str, timeout: int | None = None) -> ScanResult:
    """Scan provided content for secrets."""
    scan_id = str(uuid.uuid4())[:8]

    result = ScanResult(
        scan_id=scan_id,
        target="<content>",
        scan_type="content",
        started_at=datetime.now(),
    )
    scan_results[scan_id] = result
    active_scans.add(scan_id)

    # Write content to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name

    output_file = Path(settings.output_dir) / f"scan_{scan_id}.json"

    try:
        cmd = [
            "gitleaks",
            "detect",
            "--source", temp_path,
            "--report-format", "json",
            "--report-path", str(output_file),
            "--exit-code", "0",
            "--no-git",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await asyncio.wait_for(
            process.communicate(),
            timeout=float(timeout or settings.default_timeout),
        )

        result.completed_at = datetime.now()

        if output_file.exists():
            output_content = output_file.read_text()
            result.raw_output = output_content
            result.findings = parse_gitleaks_json(output_content)

        rules_triggered = {}
        for finding in result.findings:
            rule = finding.rule_id
            rules_triggered[rule] = rules_triggered.get(rule, 0) + 1

        result.stats = {
            "total_findings": len(result.findings),
            "rules_breakdown": rules_triggered,
        }

        result.status = "completed"

    except asyncio.TimeoutError:
        result.status = "timeout"
        result.error = f"Scan timed out"
        result.completed_at = datetime.now()

    except Exception as e:
        result.status = "error"
        result.error = str(e)
        result.completed_at = datetime.now()

    finally:
        active_scans.discard(scan_id)
        scan_results[scan_id] = result
        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)

    return result


def format_scan_summary(result: ScanResult) -> dict[str, Any]:
    """Format scan result for response."""
    findings_summary = []
    for finding in result.findings[:50]:  # Limit to 50 findings
        # Build location string
        location_parts = []
        if finding.file:
            location_parts.append(f"File: {finding.file}")
        if finding.line:
            location_parts.append(f"Line: {finding.line}")
        if finding.start_column and finding.end_column:
            location_parts.append(f"Columns: {finding.start_column}-{finding.end_column}")
        
        location = " | ".join(location_parts) if location_parts else "Unknown location"
        
        finding_detail = {
            "rule_id": finding.rule_id,
            "description": finding.description or f"Secret detected: {finding.rule_id}",
            "secret": finding.secret,
            "location": location,
            "file": finding.file,
            "line": finding.line,
            "start_column": finding.start_column,
            "end_column": finding.end_column,
        }
        
        # Add commit info if available
        if finding.commit:
            finding_detail["commit"] = finding.commit[:8]
            finding_detail["author"] = finding.author
            finding_detail["email"] = finding.email
            finding_detail["commit_date"] = finding.date
            finding_detail["commit_message"] = finding.message[:100] if finding.message else None
        
        # Add tags if available
        if finding.tags:
            finding_detail["tags"] = finding.tags
            
        findings_summary.append(finding_detail)

    return {
        "scan_id": result.scan_id,
        "target": result.target,
        "scan_type": result.scan_type,
        "status": result.status,
        "stats": result.stats,
        "findings": findings_summary,
        "findings_count": len(result.findings),
        "showing": f"Showing {len(findings_summary)} of {len(result.findings)} findings" if len(result.findings) > 50 else f"All {len(result.findings)} findings",
        "error": result.error,
    }


# Create MCP server
app = Server("gitleaks-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="gitleaks_scan_repo",
            description="Scan a git repository for secrets and credentials. "
            "Analyzes commit history for leaked API keys, passwords, tokens, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the git repository to scan",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Scan timeout in seconds",
                        "default": 300,
                    },
                },
                "required": ["repo_path"],
            },
        ),        Tool(
            name="gitleaks_scan_remote_repo",
            description="Clone and scan a remote git repository (GitHub, Bitbucket, etc.) for secrets. "
            "Supports public and private repositories with authentication.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "URL of the remote repository (e.g., https://github.com/user/repo.git)",
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "Optional authentication token for private repositories",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Scan timeout in seconds (default: 300)",
                        "default": 300,
                    },
                },
                "required": ["repo_url"],
            },
        ),        Tool(
            name="gitleaks_scan_dir",
            description="Scan a directory for secrets without git history analysis. "
            "Useful for scanning non-git directories or specific folders.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "Directory path to scan",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Scan timeout in seconds",
                        "default": 300,
                    },
                },
                "required": ["dir_path"],
            },
        ),
        Tool(
            name="gitleaks_detect",
            description="Quick scan provided content (text/code) for secrets. "
            "Useful for checking config files, environment variables, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Text content to scan for secrets",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Scan timeout in seconds",
                        "default": 60,
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="get_scan_results",
            description="Retrieve results from a previous scan by scan ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scan_id": {
                        "type": "string",
                        "description": "Scan ID returned from a previous scan",
                    },
                    "include_raw": {
                        "type": "boolean",
                        "description": "Include raw gitleaks JSON output",
                        "default": False,
                    },
                },
                "required": ["scan_id"],
            },
        ),
        Tool(
            name="list_active_scans",
            description="List currently running scans.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "gitleaks_scan_repo":
            if len(active_scans) >= settings.max_concurrent_scans:
                return [
                    TextContent(
                        type="text",
                        text=f"Maximum concurrent scans ({settings.max_concurrent_scans}) reached.",
                    )
                ]

            repo_path = arguments["repo_path"]
            if not Path(repo_path).exists():
                return [
                    TextContent(type="text", text=f"Repository not found: {repo_path}")
                ]

            if not (Path(repo_path) / ".git").exists():
                return [
                    TextContent(
                        type="text",
                        text=f"Not a git repository: {repo_path}. Use gitleaks_scan_dir for non-git directories.",
                    )
                ]

            # Convert timeout to int if it's a string
            timeout = arguments.get("timeout", 300)
            timeout = int(timeout) if timeout else 300

            result = await run_gitleaks_scan(
                target=repo_path,
                scan_type="repo",
                timeout=timeout,
                no_git=False,
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(format_scan_summary(result), indent=2),
                )
            ]

        elif name == "gitleaks_scan_remote_repo":
            if len(active_scans) >= settings.max_concurrent_scans:
                return [
                    TextContent(
                        type="text",
                        text=f"Maximum concurrent scans ({settings.max_concurrent_scans}) reached.",
                    )
                ]

            repo_url = arguments["repo_url"]
            auth_token = arguments.get("auth_token")
            
            # Convert timeout to int if it's a string
            timeout = arguments.get("timeout", 300)
            timeout = int(timeout) if timeout else 300
            
            # Clone the repository with timeout
            cloned_path, error = await clone_repository(repo_url, auth_token, timeout)
            
            if error:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to clone repository: {error}"
                    )
                ]
            
            try:
                # Scan the cloned repository
                result = await run_gitleaks_scan(
                    target=cloned_path,
                    scan_type="remote_repo",
                    timeout=timeout,
                    no_git=False,
                )
                
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(format_scan_summary(result), indent=2),
                    )
                ]
            finally:
                # Clean up cloned directory
                if cloned_path and Path(cloned_path).exists():
                    shutil.rmtree(cloned_path, ignore_errors=True)
                    logger.info(f"Cleaned up cloned repository at {cloned_path}")

        elif name == "gitleaks_scan_dir":
            if len(active_scans) >= settings.max_concurrent_scans:
                return [
                    TextContent(
                        type="text",
                        text=f"Maximum concurrent scans ({settings.max_concurrent_scans}) reached.",
                    )
                ]

            dir_path = arguments["dir_path"]
            if not Path(dir_path).exists():
                return [
                    TextContent(type="text", text=f"Directory not found: {dir_path}")
                ]

            # Convert timeout to int if it's a string
            timeout = arguments.get("timeout", 300)
            timeout = int(timeout) if timeout else 300

            result = await run_gitleaks_scan(
                target=dir_path,
                scan_type="dir",
                timeout=timeout,
                no_git=True,
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(format_scan_summary(result), indent=2),
                )
            ]

        elif name == "gitleaks_detect":
            if len(active_scans) >= settings.max_concurrent_scans:
                return [
                    TextContent(
                        type="text",
                        text=f"Maximum concurrent scans ({settings.max_concurrent_scans}) reached.",
                    )
                ]

            content = arguments["content"]
            if not content.strip():
                return [
                    TextContent(type="text", text="Content cannot be empty")
                ]

            result = await scan_content(
                content=content,
                timeout=arguments.get("timeout", 60),
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(format_scan_summary(result), indent=2),
                )
            ]

        elif name == "get_scan_results":
            scan_id = arguments["scan_id"]
            result = scan_results.get(scan_id)

            if result:
                output = format_scan_summary(result)
                if arguments.get("include_raw") and result.raw_output:
                    output["raw_output"] = result.raw_output[:10000]
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(output, indent=2),
                    )
                ]
            else:
                return [
                    TextContent(type="text", text=f"Scan '{scan_id}' not found")
                ]

        elif name == "list_active_scans":
            active = [
                {
                    "scan_id": scan_id,
                    "target": scan_results[scan_id].target,
                    "scan_type": scan_results[scan_id].scan_type,
                    "started_at": scan_results[scan_id].started_at.isoformat(),
                }
                for scan_id in active_scans
                if scan_id in scan_results
            ]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "active_scans": active,
                            "count": len(active),
                            "max_concurrent": settings.max_concurrent_scans,
                        },
                        indent=2,
                    ),
                )
            ]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    resources = []

    for scan_id, result in scan_results.items():
        if result.status == "completed":
            finding_count = len(result.findings)
            resources.append(
                Resource(
                    uri=f"gitleaks://results/{scan_id}",
                    name=f"Scan Results: {result.target} ({finding_count} secrets)",
                    description=f"{result.scan_type} scan completed at {result.completed_at}",
                    mimeType="application/json",
                )
            )

    return resources


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource."""
    if uri.startswith("gitleaks://results/"):
        scan_id = uri.replace("gitleaks://results/", "")
        result = scan_results.get(scan_id)

        if result:
            return json.dumps(format_scan_summary(result), indent=2)

    return json.dumps({"error": "Resource not found"})


async def main():
    """Run the MCP server."""
    logger.info("Starting Gitleaks MCP Server")
    logger.info(f"Output directory: {settings.output_dir}")

    # Ensure output directory exists
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

