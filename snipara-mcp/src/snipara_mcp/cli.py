#!/usr/bin/env python3
"""
Snipara CLI - Unified command-line interface.

Usage:
    snipara init           # Initialize Snipara in current directory
    snipara login          # Sign in via browser (OAuth Device Flow)
    snipara logout         # Clear stored tokens
    snipara status         # Show current auth status
    snipara upload <file>  # Upload a document
    snipara query <text>   # Quick test query
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

from .auth import (
    TOKEN_FILE,
    clear_all_tokens,
    device_flow_login,
    load_tokens,
)

# Create main CLI app
app = typer.Typer(
    name="snipara",
    help="Snipara CLI - Context optimization for LLMs",
    no_args_is_help=True,
    add_completion=False,
)


# ANSI colors for terminal output
class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def color(text: str, c: str) -> str:
    """Wrap text in ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    return f"{c}{text}{Colors.END}"


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(color(title, Colors.BOLD))
    print("=" * 40)
    print()


def print_step(num: int, text: str) -> None:
    """Print a step indicator."""
    print(color(f"{num}. {text}", Colors.BLUE))


def print_success(text: str) -> None:
    """Print success message."""
    print(f"  {color('✓', Colors.GREEN)} {text}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"  {color('⚠', Colors.YELLOW)} {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"  {color('✗', Colors.RED)} {text}")


# =============================================================================
# Helper Functions
# =============================================================================


def detect_project_type() -> dict:
    """Detect the project type based on config files in current directory."""
    cwd = Path.cwd()

    if (cwd / "package.json").exists():
        pkg = json.loads((cwd / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        lang = "TypeScript" if (cwd / "tsconfig.json").exists() else "JavaScript"

        if "next" in deps:
            return {"type": "node", "framework": "Next.js", "language": lang}
        elif "react" in deps:
            return {"type": "node", "framework": "React", "language": lang}
        elif "vue" in deps:
            return {"type": "node", "framework": "Vue", "language": lang}
        elif "svelte" in deps:
            return {"type": "node", "framework": "Svelte", "language": lang}
        else:
            return {"type": "node", "framework": "Node.js", "language": lang}

    elif (cwd / "pyproject.toml").exists() or (cwd / "setup.py").exists():
        return {"type": "python", "framework": "Python", "language": "Python"}

    elif (cwd / "go.mod").exists():
        return {"type": "go", "framework": "Go", "language": "Go"}

    elif (cwd / "Cargo.toml").exists():
        return {"type": "rust", "framework": "Rust", "language": "Rust"}

    elif (cwd / "pom.xml").exists() or (cwd / "build.gradle").exists():
        return {"type": "java", "framework": "Java/Kotlin", "language": "Java"}

    else:
        return {"type": "unknown", "framework": "Unknown", "language": "Unknown"}


def get_git_remote() -> Optional[str]:
    """Get the git remote URL for the current repository."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    if "/" in name:
        name = name.split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    slug = slug.strip("-")
    return slug or "my-project"


def generate_mcp_json(
    slug: str,
    api_url: str = "https://api.snipara.com",
    api_key: str | None = None,
) -> dict:
    """Generate .mcp.json content for the project."""
    return {
        "mcpServers": {
            "snipara": {
                "type": "http",
                "url": f"{api_url}/mcp/{slug}",
                "headers": {"X-API-Key": api_key if api_key else "${SNIPARA_API_KEY}"},
            }
        }
    }


def write_mcp_json(slug: str, dry_run: bool = False, api_key: str | None = None) -> bool:
    """Write .mcp.json file to current directory."""
    mcp_path = Path.cwd() / ".mcp.json"
    content = generate_mcp_json(slug, api_key=api_key)

    if dry_run:
        print(f"  Would create: {mcp_path}")
        print(f"  Content: {json.dumps(content, indent=2)[:100]}...")
        return True

    if mcp_path.exists():
        existing = json.loads(mcp_path.read_text())
        if "snipara" in existing.get("mcpServers", {}):
            current_key = existing["mcpServers"]["snipara"].get("headers", {}).get("X-API-Key", "")
            new_key = content["mcpServers"]["snipara"]["headers"]["X-API-Key"]

            if api_key and current_key != new_key:
                existing["mcpServers"]["snipara"]["headers"]["X-API-Key"] = new_key
                mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
                print_success(f".mcp.json updated (API key: {new_key[:12]}...)")
                return True
            else:
                print_warning(".mcp.json already configured")
                return False

        existing.setdefault("mcpServers", {})
        existing["mcpServers"]["snipara"] = content["mcpServers"]["snipara"]
        content = existing

    mcp_path.write_text(json.dumps(content, indent=2) + "\n")
    if api_key:
        print_success(f".mcp.json created (API key: {api_key[:12]}...)")
    else:
        print_success(".mcp.json created (uses ${SNIPARA_API_KEY})")
    return True


def update_env_example(dry_run: bool = False) -> bool:
    """Add SNIPARA_API_KEY to .env.example if not present."""
    env_path = Path.cwd() / ".env.example"
    env_local_path = Path.cwd() / ".env.local.example"
    target_path = env_path if env_path.exists() else env_local_path if env_local_path.exists() else env_path

    line_to_add = "SNIPARA_API_KEY=rlm_your_api_key_here\n"

    if dry_run:
        print(f"  Would update: {target_path}")
        return True

    if target_path.exists():
        content = target_path.read_text()
        if "SNIPARA_API_KEY" in content:
            print_warning(f"{target_path.name} already has SNIPARA_API_KEY")
            return False
        with open(target_path, "a") as f:
            if not content.endswith("\n"):
                f.write("\n")
            f.write("\n# Snipara API Key (get from https://snipara.com/dashboard)\n")
            f.write(line_to_add)
    else:
        with open(target_path, "w") as f:
            f.write("# Environment Variables\n\n")
            f.write("# Snipara API Key (get from https://snipara.com/dashboard)\n")
            f.write(line_to_add)

    print_success(f"{target_path.name} updated")
    return True


async def upload_document_async(
    api_url: str,
    slug: str,
    path: str,
    content: str,
    auth_header: str,
) -> bool:
    """Upload a document to Snipara."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Content-Type": "application/json"}
            if auth_header.startswith("Bearer"):
                headers["Authorization"] = auth_header
            else:
                headers["X-API-Key"] = auth_header

            response = await client.post(
                f"{api_url}/mcp/{slug}",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "rlm_upload_document",
                        "arguments": {"path": path, "content": content},
                    },
                },
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return True
                elif "error" in result:
                    print_error(result["error"].get("message", "Unknown error"))
            else:
                print_error(f"HTTP {response.status_code}")

    except Exception as e:
        print_error(str(e))

    return False


async def test_connection(api_url: str, slug: str, auth_header: str) -> bool:
    """Test connection to Snipara API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"Content-Type": "application/json"}
            if auth_header.startswith("Bearer"):
                headers["Authorization"] = auth_header
            else:
                headers["X-API-Key"] = auth_header

            response = await client.post(
                f"{api_url}/mcp/{slug}",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "rlm_stats", "arguments": {}},
                },
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return True
    except Exception:
        pass
    return False


async def query_async(api_url: str, slug: str, query: str, auth_header: str, max_tokens: int = 2000) -> dict | None:
    """Execute a query against Snipara."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Content-Type": "application/json"}
            if auth_header.startswith("Bearer"):
                headers["Authorization"] = auth_header
            else:
                headers["X-API-Key"] = auth_header

            response = await client.post(
                f"{api_url}/mcp/{slug}",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "rlm_context_query",
                        "arguments": {"query": query, "max_tokens": max_tokens},
                    },
                },
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return result["result"]
                elif "error" in result:
                    print_error(result["error"].get("message", "Unknown error"))
            else:
                print_error(f"HTTP {response.status_code}")
    except Exception as e:
        print_error(str(e))
    return None


# =============================================================================
# CLI Commands
# =============================================================================


@app.command()
def init(
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Project slug (default: auto-detect)"),
    upload: bool = typer.Option(True, "--upload/--no-upload", help="Upload docs after init"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without making changes"),
    skip_test: bool = typer.Option(False, "--skip-test", help="Skip connection test"),
) -> None:
    """Initialize Snipara in the current project."""

    async def _init() -> int:
        cwd = Path.cwd()
        api_url = os.environ.get("SNIPARA_API_URL", "https://api.snipara.com")

        print_header("Snipara Init")

        # Step 1: Detect project
        print_step(1, "Detecting project...")
        project = detect_project_type()
        git_remote = get_git_remote()

        print(f"   Type: {project['framework']} ({project['language']})")
        if git_remote:
            print(f"   Git: {git_remote}")

        # Determine slug
        project_slug = slug
        if not project_slug:
            if git_remote:
                project_slug = slugify(git_remote)
            else:
                project_slug = slugify(cwd.name)
        print(f"   Slug: {color(project_slug, Colors.GREEN)}")
        print()

        # Step 2: Check auth
        auth_header = None
        api_key = os.environ.get("SNIPARA_API_KEY")
        oauth_api_key = None

        print_step(2, "Authentication")
        if api_key:
            auth_header = api_key
            print(f"   Using SNIPARA_API_KEY from environment")
        else:
            tokens = load_tokens()
            if tokens:
                matching_token = None
                for _, token_data in tokens.items():
                    if token_data.get("project_slug") == project_slug:
                        matching_token = token_data
                        break
                if not matching_token:
                    matching_token = next(iter(tokens.values()))

                if matching_token.get("access_token"):
                    auth_header = f"Bearer {matching_token['access_token']}"
                    oauth_api_key = matching_token.get("api_key")
                    print(f"   Using OAuth token from {TOKEN_FILE}")
                    if oauth_api_key:
                        print(f"   API key: {oauth_api_key[:12]}...")
                    else:
                        print_warning("No API key in token. Re-run `snipara login`")

        if not auth_header:
            print_warning("Not authenticated - will use placeholder in .mcp.json")
        print()

        # Step 3: Generate config files
        print_step(3, "Creating configuration...")
        mcp_api_key = api_key or oauth_api_key
        write_mcp_json(project_slug, dry_run, api_key=mcp_api_key)
        update_env_example(dry_run)
        print()

        # Step 4: Upload docs
        if auth_header and upload and not dry_run:
            print_step(4, "Uploading initial docs...")

            docs_to_upload = []

            if (cwd / "CLAUDE.md").exists():
                docs_to_upload.append(("CLAUDE.md", (cwd / "CLAUDE.md").read_text()))

            if (cwd / "README.md").exists():
                docs_to_upload.append(("README.md", (cwd / "README.md").read_text()))

            docs_dir = cwd / "docs"
            if docs_dir.exists() and docs_dir.is_dir():
                for md_file in docs_dir.rglob("*.md"):
                    rel_path = str(md_file.relative_to(cwd))
                    try:
                        content = md_file.read_text()
                        docs_to_upload.append((rel_path, content))
                    except Exception:
                        pass

            if docs_to_upload:
                uploaded = 0
                total_tokens = 0

                for path, content in docs_to_upload:
                    tokens_est = len(content) // 4
                    total_tokens += tokens_est

                    success = await upload_document_async(api_url, project_slug, path, content, auth_header)
                    if success:
                        uploaded += 1
                        print_success(f"{path} (~{tokens_est:,} tokens)")
                    else:
                        print_error(f"Failed: {path}")

                print(f"\n   Total: {uploaded}/{len(docs_to_upload)} files (~{total_tokens:,} tokens)")
            else:
                print("   No docs found (CLAUDE.md, README.md, or docs/)")
            print()
        elif not auth_header:
            print_step(4, "Uploading docs... SKIPPED")
            print("   No API key. Set SNIPARA_API_KEY or run `snipara login`")
            print()

        # Step 5: Test connection
        if auth_header and not skip_test and not dry_run:
            print_step(5, "Testing connection...")
            if await test_connection(api_url, project_slug, auth_header):
                print_success("Connected to Snipara API")
            else:
                print_warning("Could not connect. Check your API key.")
            print()

        # Done
        print(color("Setup Complete!", Colors.GREEN + Colors.BOLD))
        print("=" * 40)
        print()
        print(f"  MCP endpoint: {color(f'{api_url}/mcp/{project_slug}', Colors.BLUE)}")
        print(f"  Dashboard:    {color(f'https://snipara.com/projects/{project_slug}', Colors.BLUE)}")
        print()

        if not auth_header:
            print(color("Next steps:", Colors.BOLD))
            print("  1. Run `snipara login` to authenticate")
            print("  2. Run `snipara init` again to update .mcp.json")
            print("  3. Restart Claude Code / Cursor")
            print()
        elif mcp_api_key:
            print(color("Next steps:", Colors.BOLD))
            print("  1. Restart Claude Code / Cursor to load MCP config")
            print('  2. Try: rlm_context_query("how does this project work?")')
            print()

        return 0

    try:
        exit_code = asyncio.run(_init())
        raise typer.Exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        raise typer.Exit(1)


@app.command()
def login() -> None:
    """Sign in via browser (OAuth Device Flow)."""
    print_header("Snipara Login")

    try:
        asyncio.run(device_flow_login())
    except KeyboardInterrupt:
        print("\n\nLogin cancelled.")
        raise typer.Exit(1)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command()
def logout(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Clear all stored tokens."""
    print_header("Snipara Logout")

    tokens = load_tokens()
    if not tokens:
        print("No stored tokens found.")
        raise typer.Exit(0)

    print(f"Found {len(tokens)} stored token(s):")
    for project_id, data in tokens.items():
        slug = data.get("project_slug", project_id)
        print(f"  - {slug}")
    print()

    if not force:
        confirm = typer.confirm("Clear all tokens?", default=False)
        if not confirm:
            print("Cancelled.")
            raise typer.Exit(0)

    count = clear_all_tokens()
    print_success(f"Cleared {count} token(s)")


@app.command()
def status() -> None:
    """Show current authentication status."""
    print_header("Snipara Status")

    from datetime import datetime, timezone

    # Check environment variables
    api_key = os.environ.get("SNIPARA_API_KEY")
    project_id = os.environ.get("SNIPARA_PROJECT_ID")

    if api_key:
        print(color("Environment:", Colors.BOLD))
        print(f"  SNIPARA_API_KEY: {api_key[:12]}...")
        if project_id:
            print(f"  SNIPARA_PROJECT_ID: {project_id}")
        print()

    # Check stored tokens
    tokens = load_tokens()
    if tokens:
        print(color("OAuth Tokens:", Colors.BOLD))
        for pid, data in tokens.items():
            slug = data.get("project_slug", pid)
            expires_at = data.get("expires_at", "unknown")
            try:
                exp_time = datetime.fromisoformat(expires_at)
                if exp_time.tzinfo is None:
                    exp_time = exp_time.replace(tzinfo=timezone.utc)
                if exp_time < datetime.now(timezone.utc):
                    status_text = color("EXPIRED", Colors.RED)
                else:
                    remaining = exp_time - datetime.now(timezone.utc)
                    mins = remaining.total_seconds() / 60
                    status_text = color(f"valid ({mins:.0f} min)", Colors.GREEN)
            except (ValueError, TypeError):
                status_text = "unknown"
            print(f"  {slug}: {status_text}")
        print()
    else:
        print("No stored OAuth tokens.")
        print()

    if not api_key and not tokens:
        print(f"Not authenticated. Run `{color('snipara login', Colors.BLUE)}` to sign in.")


@app.command()
def upload(
    file: Path = typer.Argument(..., help="File to upload", exists=True),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Project slug"),
) -> None:
    """Upload a document to Snipara."""

    async def _upload() -> None:
        api_url = os.environ.get("SNIPARA_API_URL", "https://api.snipara.com")

        # Determine slug
        project_slug = slug
        if not project_slug:
            git_remote = get_git_remote()
            if git_remote:
                project_slug = slugify(git_remote)
            else:
                project_slug = slugify(Path.cwd().name)

        # Get auth
        auth_header = None
        api_key = os.environ.get("SNIPARA_API_KEY")
        if api_key:
            auth_header = api_key
        else:
            tokens = load_tokens()
            if tokens:
                matching = next(iter(tokens.values()))
                if matching.get("access_token"):
                    auth_header = f"Bearer {matching['access_token']}"

        if not auth_header:
            print_error("Not authenticated. Run `snipara login` first.")
            raise typer.Exit(1)

        # Upload
        content = file.read_text()
        rel_path = str(file.relative_to(Path.cwd())) if file.is_relative_to(Path.cwd()) else file.name
        tokens_est = len(content) // 4

        print(f"Uploading {rel_path} (~{tokens_est:,} tokens)...")

        success = await upload_document_async(api_url, project_slug, rel_path, content, auth_header)
        if success:
            print_success(f"Uploaded to project: {project_slug}")
        else:
            raise typer.Exit(1)

    asyncio.run(_upload())


@app.command()
def query(
    text: str = typer.Argument(..., help="Query text"),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Project slug"),
    max_tokens: int = typer.Option(2000, "--max-tokens", "-t", help="Max tokens to return"),
) -> None:
    """Execute a quick test query."""

    async def _query() -> None:
        api_url = os.environ.get("SNIPARA_API_URL", "https://api.snipara.com")

        # Determine slug
        project_slug = slug
        if not project_slug:
            git_remote = get_git_remote()
            if git_remote:
                project_slug = slugify(git_remote)
            else:
                project_slug = slugify(Path.cwd().name)

        # Get auth
        auth_header = None
        api_key = os.environ.get("SNIPARA_API_KEY")
        if api_key:
            auth_header = api_key
        else:
            tokens = load_tokens()
            if tokens:
                matching = next(iter(tokens.values()))
                if matching.get("access_token"):
                    auth_header = f"Bearer {matching['access_token']}"

        if not auth_header:
            print_error("Not authenticated. Run `snipara login` first.")
            raise typer.Exit(1)

        print(f"Querying: {color(text, Colors.BLUE)}")
        print(f"Project: {project_slug}")
        print()

        result = await query_async(api_url, project_slug, text, auth_header, max_tokens)
        if result:
            # Parse result content
            try:
                if isinstance(result, dict) and "content" in result:
                    for item in result["content"]:
                        if item.get("type") == "text":
                            data = json.loads(item["text"])
                            sections = data.get("sections", [])
                            print(f"Found {len(sections)} section(s), {data.get('total_tokens', 0)} tokens")
                            print()
                            for section in sections[:3]:
                                print(color(f"── {section.get('title', 'Untitled')} ──", Colors.BOLD))
                                print(color(f"   {section.get('file', '')}", Colors.DIM))
                                content = section.get("content", "")[:500]
                                print(content)
                                print()
                else:
                    print(json.dumps(result, indent=2))
            except Exception:
                print(result)
        else:
            raise typer.Exit(1)

    asyncio.run(_query())


# =============================================================================
# Backward Compatibility Entry Points
# =============================================================================


def init_cli() -> None:
    """Legacy entry point for snipara-init."""
    sys.argv = ["snipara", "init"] + sys.argv[1:]
    app()


def login_cli() -> None:
    """Legacy entry point for snipara-mcp-login."""
    sys.argv = ["snipara", "login"] + sys.argv[1:]
    app()


def logout_cli() -> None:
    """Legacy entry point for snipara-mcp-logout."""
    sys.argv = ["snipara", "logout"] + sys.argv[1:]
    app()


def status_cli() -> None:
    """Legacy entry point for snipara-mcp-status."""
    sys.argv = ["snipara", "status"] + sys.argv[1:]
    app()


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
