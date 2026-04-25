"""Deterministic benchmark for Snipara code-graph MCP tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import BenchmarkConfig, resolve_snipara_project_ref
from .snipara_client import SniparaClient


@dataclass(frozen=True)
class CodeGraphCase:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    expected_fragments: tuple[str, ...]
    description: str


@dataclass
class CaseRun:
    duration_ms: int
    response_bytes: int
    success: bool


def default_cases() -> list[CodeGraphCase]:
    """Benchmark cases anchored to the Snipara backend itself."""
    return [
        CodeGraphCase(
            id="hybrid_context_callers",
            tool_name="rlm_context_query",
            arguments={
                "query": "who calls src.rlm_engine.RLMEngine._handle_context_query?",
                "max_tokens": 4000,
                "search_mode": "hybrid",
            },
            expected_fragments=(
                "rlm_code_callers",
                "src.rlm_engine.RLMEngine._handle_context_query",
            ),
            description="Hybrid structural summary via rlm_context_query",
        ),
        CodeGraphCase(
            id="hybrid_context_neighbors_doc_first",
            tool_name="rlm_context_query",
            arguments={
                "query": (
                    "Explain how src.rlm_engine.RLMEngine._handle_context_query works "
                    "during request handling"
                ),
                "max_tokens": 4000,
                "search_mode": "hybrid",
            },
            expected_fragments=(
                '"graph_hybrid_used": true',
                '"recommended_tool": "rlm_code_neighbors"',
                "Code Graph: Neighborhood of",
            ),
            description="Doc-first mixed retrieval with appended code graph neighborhood",
        ),
        CodeGraphCase(
            id="code_callers",
            tool_name="rlm_code_callers",
            arguments={
                "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                "depth": 1,
                "limit": 10,
            },
            expected_fragments=(
                "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
            ),
            description="Reverse call lookup for _handle_context_query",
        ),
        CodeGraphCase(
            id="code_imports",
            tool_name="rlm_code_imports",
            arguments={
                "file_path": "src/rlm_engine.py",
                "direction": "out",
                "limit": 12,
            },
            expected_fragments=("imports", "src/rlm_engine.py"),
            description="Outbound imports for rlm_engine.py",
        ),
        CodeGraphCase(
            id="code_neighbors",
            tool_name="rlm_code_neighbors",
            arguments={
                "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                "depth": 2,
                "limit": 20,
            },
            expected_fragments=(
                "src.rlm_engine.RLMEngine._handle_context_query",
                "src.db.get_db",
            ),
            description="Local structural neighborhood around _handle_context_query",
        ),
        CodeGraphCase(
            id="code_shortest_path",
            tool_name="rlm_code_shortest_path",
            arguments={
                "from": "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
                "to": "src.rlm_engine.RLMEngine._handle_context_query",
                "max_hops": 6,
            },
            expected_fragments=(
                '"found": true',
                "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
                "src.rlm_engine.RLMEngine._handle_context_query",
            ),
            description="Shortest structural path from execute_single_query to _handle_context_query",
        ),
    ]


def compute_percentile(values: list[int], percentile: float) -> int:
    """Compute a simple percentile for small sample sizes."""
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def evaluate_success(serialized_response: str, expected_fragments: tuple[str, ...]) -> bool:
    """Check whether all expected fragments are present in the serialized payload."""
    return all(fragment in serialized_response for fragment in expected_fragments)


async def execute_case(client: SniparaClient, case: CodeGraphCase, runs: int) -> dict[str, Any]:
    """Execute one benchmark case repeatedly and aggregate latency stats."""
    run_results: list[CaseRun] = []
    last_payload: Any = {}

    for _ in range(runs):
        started = time.perf_counter()
        if case.tool_name == "rlm_context_query":
            result = await client.context_query(
                query=case.arguments["query"],
                max_tokens=case.arguments.get("max_tokens", 4000),
                search_mode=case.arguments.get("search_mode", "hybrid"),
            )
            payload = result.to_dict()
        else:
            payload = await client.call_tool(case.tool_name, case.arguments)

        duration_ms = int((time.perf_counter() - started) * 1000)
        serialized = json.dumps(payload, default=str, sort_keys=True)
        run_results.append(
            CaseRun(
                duration_ms=duration_ms,
                response_bytes=len(serialized.encode("utf-8")),
                success=evaluate_success(serialized, case.expected_fragments),
            )
        )
        last_payload = payload

    durations = [run.duration_ms for run in run_results]
    sizes = [run.response_bytes for run in run_results]
    successes = [run.success for run in run_results]

    return {
        "id": case.id,
        "tool_name": case.tool_name,
        "description": case.description,
        "runs": runs,
        "success_rate": sum(1 for success in successes if success) / len(successes),
        "latency_ms": {
            "min": min(durations),
            "p50": compute_percentile(durations, 0.5),
            "p95": compute_percentile(durations, 0.95),
            "max": max(durations),
            "mean": round(statistics.mean(durations), 2),
        },
        "response_bytes": {
            "min": min(sizes),
            "mean": round(statistics.mean(sizes), 2),
            "max": max(sizes),
        },
        "latest_payload": last_payload,
        "run_details": [asdict(run) for run in run_results],
    }


async def maybe_probe_runtime(project_ref: str) -> dict[str, Any]:
    """Optionally validate that rlm-runtime can start for this project."""
    if not os.getenv("OPENAI_API_KEY"):
        return {
            "attempted": False,
            "available": False,
            "reason": "OPENAI_API_KEY is not set",
        }

    prompt = (
        "Use Snipara tools to inspect the code graph for "
        "src.rlm_engine.RLMEngine._handle_context_query and summarize one caller."
    )
    result = subprocess.run(
        ["rlm", "run", "--json", "--timeout", "45", prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = result.stdout.strip()
    parsed: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            parsed = {"raw": stdout}

    return {
        "attempted": True,
        "available": result.returncode == 0,
        "return_code": result.returncode,
        "stderr_tail": result.stderr.strip().splitlines()[-5:],
        "result": parsed,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a concise markdown report."""
    lines = [
        "# Code Graph Benchmark",
        "",
        f"- Project: `{report['project_ref']}`",
        f"- Base URL: `{report['base_url']}`",
        f"- Runs per case: `{report['runs']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Results",
        "",
        "| Case | Tool | Success | p50 | p95 | Avg bytes |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]

    for case in report["cases"]:
        lines.append(
            "| "
            f"{case['id']} | {case['tool_name']} | {case['success_rate']:.0%} | "
            f"{case['latency_ms']['p50']} ms | {case['latency_ms']['p95']} ms | "
            f"{int(case['response_bytes']['mean'])} |"
        )

    runtime_probe = report.get("runtime_probe")
    if runtime_probe:
        lines.extend(["", "## RLM Runtime Probe", ""])
        if not runtime_probe.get("attempted"):
            lines.append(f"- Skipped: {runtime_probe.get('reason', 'not requested')}")
        else:
            lines.append(f"- Available: `{runtime_probe.get('available')}`")
            if runtime_probe.get("stderr_tail"):
                lines.append("- stderr tail:")
                lines.extend(f"  - `{line}`" for line in runtime_probe["stderr_tail"])

    return "\n".join(lines) + "\n"


async def run_benchmark(
    *,
    project_ref: str,
    base_url: str,
    runs: int,
    output_dir: Path,
    include_runtime_probe: bool,
    prefer_api_key: bool,
) -> dict[str, Any]:
    """Run the code graph benchmark and write JSON/markdown reports."""
    cfg = BenchmarkConfig(snipara_project_slug=project_ref, snipara_api_url=base_url)
    client = SniparaClient(
        api_key=cfg.snipara_api_key,
        access_token=cfg.snipara_oauth_token,
        project_slug=project_ref,
        base_url=base_url,
        prefer_api_key=prefer_api_key,
    )

    try:
        case_reports = [await execute_case(client, case, runs) for case in default_cases()]
    finally:
        await client.close()

    report = {
        "project_ref": project_ref,
        "base_url": base_url,
        "runs": runs,
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": case_reports,
        "runtime_probe": await maybe_probe_runtime(project_ref) if include_runtime_probe else None,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"code_graph_benchmark_{timestamp}.json"
    md_path = output_dir / f"code_graph_benchmark_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(render_markdown_report(report))

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic code graph MCP benchmarks.")
    parser.add_argument(
        "--project",
        default=resolve_snipara_project_ref(),
        help="Snipara project slug or identifier",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SNIPARA_BASE_URL", "https://api.snipara.com/mcp"),
        help="Base MCP URL, without the trailing project slug",
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per case")
    parser.add_argument(
        "--output-dir",
        default="apps/mcp-server/benchmarks/reports",
        help="Directory for JSON and markdown reports",
    )
    parser.add_argument(
        "--probe-runtime",
        action="store_true",
        help="Also probe rlm-runtime if OPENAI_API_KEY is configured",
    )
    parser.add_argument(
        "--prefer-api-key",
        action="store_true",
        help="Skip local OAuth tokens and authenticate with SNIPARA_API_KEY directly",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(
        run_benchmark(
            project_ref=args.project,
            base_url=args.base_url,
            runs=max(1, args.runs),
            output_dir=Path(args.output_dir),
            include_runtime_probe=args.probe_runtime,
            prefer_api_key=args.prefer_api_key,
        )
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
