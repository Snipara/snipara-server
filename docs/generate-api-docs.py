#!/usr/bin/env python3
"""
Script de generation de la documentation API depuis le code Python.
Utilise pdoc pour generer la documentation a partir des docstrings.

Usage:
    python docs/generate-api-docs.py
"""

import subprocess
import sys
from pathlib import Path

# Configuration
DOCS_OUTPUT_DIR = Path(__file__).parent.parent.parent / "docs" / "reference" / "api" / "generated"
SRC_DIR = Path(__file__).parent / "src"

# Modules a documenter (dans l'ordre de dependance)
MODULES = [
    # Core models - dependances de base
    "src.models",
    "src.models.enums",
    "src.models.requests",
    "src.models.responses",
    "src.models.context",
    "src.models.documents",
    "src.models.agent",
    "src.models.shared",
    "src.models.summary",
    # Engine core
    "src.engine",
    "src.engine.core",
    "src.engine.core.tokens",
    "src.engine.core.query",
    "src.engine.core.document",
    "src.engine.core.tips",
    # Scoring
    "src.engine.scoring",
    "src.engine.scoring.keyword_scorer",
    "src.engine.scoring.semantic_scorer",
    "src.engine.scoring.rrf_fusion",
    "src.engine.scoring.stemmer",
    # Handlers
    "src.engine.handlers",
    "src.engine.handlers.base",
    "src.engine.handlers.document",
    "src.engine.handlers.memory",
    "src.engine.handlers.session",
    "src.engine.handlers.summary",
    "src.engine.handlers.swarm",
    # MCP Protocol
    "src.mcp",
    "src.mcp.jsonrpc",
    "src.mcp.tool_defs",
    "src.mcp.validation",
    # API
    "src.api",
    "src.api.deps",
    # Services
    "src.services",
    "src.services.embeddings",
    "src.services.chunker",
    "src.services.cache",
    "src.services.indexer",
    "src.services.query_router",
    "src.services.agent_memory",
    "src.services.shared_context",
    # Main entry points
    "src.server",
    "src.rlm_engine",
    "src.mcp_transport",
]


def generate_docs():
    """Genere la documentation API avec pdoc."""
    
    print(f"Generation de la documentation API...")
    print(f"   Output: {DOCS_OUTPUT_DIR}")
    
    # Creer le repertoire de sortie
    DOCS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Options pdoc
    pdoc_options = [
        "--docformat", "google",
        "--show-source",
        "--indent", "4",
    ]
    
    # Generer pour chaque module
    generated = []
    failed = []
    
    for module in MODULES:
        try:
            print(f"   Processing: {module}...", end=" ")
            result = subprocess.run(
                [
                    sys.executable, "-m", "pdoc",
                    *pdoc_options,
                    "--output-dir", str(DOCS_OUTPUT_DIR),
                    module
                ],
                cwd=SRC_DIR.parent,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print("OK")
                generated.append(module)
            else:
                print(f"Warning ({result.returncode})")
                failed.append((module, result.stderr))
        except Exception as e:
            print(f"Error: {e}")
            failed.append((module, str(e)))
    
    # Generer un index
    generate_index(generated, failed)
    
    print(f"\nGeneration terminee!")
    print(f"   Modules generated: {len(generated)}")
    print(f"   Failures: {len(failed)}")


def generate_index(generated, failed):
    """Genere un fichier INDEX.md pour la doc generee."""
    
    lines = []
    lines.append("# API Reference - Generated")
    lines.append("")
    lines.append("Auto-generated from Python source code.")
    lines.append("")
    lines.append("## Modules")
    lines.append("")
    lines.append("| Module | Status |")
    lines.append("|--------|--------|")
    
    for module in generated:
        module_name = module.replace("src.", "")
        lines.append(f"| {module_name} | OK |")
    
    if failed:
        lines.append("")
        lines.append("### Modules with errors")
        for module, error in failed:
            lines.append(f"| {module} | Error |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Regenerate docs")
    lines.append("")
    lines.append("cd apps/mcp-server")
    lines.append("uv run python docs/generate-api-docs.py")
    lines.append("")
    lines.append("## Docstring format")
    lines.append("")
    lines.append("Uses Google style: https://google.github.io/styleguide/pyguide.html")
    
    index_content = "\n".join(lines)
    
    index_file = DOCS_OUTPUT_DIR / "INDEX.md"
    index_file.write_text(index_content)
    print(f"   Index generated: {index_file}")


if __name__ == "__main__":
    generate_docs()
