"""Deterministic benchmark for snipara-companion versus direct hosted MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .config import BenchmarkConfig, resolve_snipara_project_ref
from .snipara_client import SniparaClient


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class CompanionBenchmarkCase:
    id: str
    mode: Literal["direct", "companion"]
    description: str
    expected_fragments: tuple[str, ...]
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    command: tuple[str, ...] | None = None
    comparison_group: str | None = None


@dataclass
class CaseRun:
    duration_ms: int
    response_bytes: int
    success: bool


def normalize_companion_api_url(base_url: str) -> str:
    """Convert an MCP base URL into the root API URL expected by companion."""
    return base_url[:-4] if base_url.endswith("/mcp") else base_url


def token_store_path() -> Path:
    """Resolve the token store lazily so tests can override Path.home()."""
    return Path.home() / ".snipara" / "tokens.json"


def load_project_api_key(project_ref: str) -> str | None:
    """Resolve a project-scoped API key from ~/.snipara/tokens.json."""
    path = token_store_path()
    if not path.exists():
        return None

    try:
        tokens = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None

    direct = tokens.get(project_ref)
    if isinstance(direct, dict) and direct.get("api_key"):
        return direct["api_key"]

    for token_data in tokens.values():
        if not isinstance(token_data, dict):
            continue
        if token_data.get("project_slug") == project_ref or token_data.get("project_id") == project_ref:
            api_key = token_data.get("api_key")
            if api_key:
                return api_key

    return None


def default_cases(companion_bin: str = "rlm-hook") -> list[CompanionBenchmarkCase]:
    """Benchmark direct hosted calls against companion wrappers."""
    return [
        CompanionBenchmarkCase(
            id="direct_code_callers",
            mode="direct",
            description="Direct MCP rlm_code_callers",
            tool_name="rlm_code_callers",
            arguments={
                "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                "depth": 1,
                "limit": 50,
            },
            expected_fragments=(
                "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
            ),
            comparison_group="code_callers",
        ),
        CompanionBenchmarkCase(
            id="companion_code_callers",
            mode="companion",
            description="Companion code callers command",
            command=(
                companion_bin,
                "code",
                "callers",
                "--qualified-name",
                "src.rlm_engine.RLMEngine._handle_context_query",
                "--json",
            ),
            expected_fragments=(
                "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
            ),
            comparison_group="code_callers",
        ),
        CompanionBenchmarkCase(
            id="direct_code_imports",
            mode="direct",
            description="Direct MCP rlm_code_imports",
            tool_name="rlm_code_imports",
            arguments={
                "file_path": "src/rlm_engine.py",
                "direction": "out",
                "limit": 50,
            },
            expected_fragments=(
                '"total_imports"',
                "src/rlm_engine.py",
            ),
            comparison_group="code_imports",
        ),
        CompanionBenchmarkCase(
            id="companion_code_imports",
            mode="companion",
            description="Companion code imports command",
            command=(
                companion_bin,
                "code",
                "imports",
                "--file-path",
                "src/rlm_engine.py",
                "--json",
            ),
            expected_fragments=(
                '"total_imports"',
                "src/rlm_engine.py",
            ),
            comparison_group="code_imports",
        ),
        CompanionBenchmarkCase(
            id="direct_context_query",
            mode="direct",
            description="Direct MCP hybrid context query",
            tool_name="rlm_context_query",
            arguments={
                "query": "who calls src.rlm_engine.RLMEngine._handle_context_query",
                "max_tokens": 8000,
                "search_mode": "hybrid",
            },
            expected_fragments=(
                '"recommended_tool": "rlm_code_callers"',
                "src.rlm_engine.RLMEngine._handle_context_query",
            ),
        ),
        CompanionBenchmarkCase(
            id="companion_workflow_auto",
            mode="companion",
            description="Companion workflow auto with structural follow-up",
            command=(
                companion_bin,
                "workflow",
                "run",
                "--mode",
                "auto",
                "--query",
                "who calls src.rlm_engine.RLMEngine._handle_context_query",
                "--json",
            ),
            expected_fragments=(
                '"toolName": "rlm_code_callers"',
                "src.rlm_engine.RLMEngine._handle_multi_query.execute_single_query",
            ),
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


async def execute_direct_case(
    client: SniparaClient,
    case: CompanionBenchmarkCase,
) -> tuple[int, int, dict[str, Any]]:
    started = time.perf_counter()
    assert case.tool_name is not None
    assert case.arguments is not None

    if case.tool_name == "rlm_context_query":
        result = await client.context_query(
            query=case.arguments["query"],
            max_tokens=case.arguments.get("max_tokens", 8000),
            search_mode=case.arguments.get("search_mode", "hybrid"),
        )
        payload = result.to_dict()
    else:
        payload = await client.call_tool(case.tool_name, case.arguments)

    duration_ms = int((time.perf_counter() - started) * 1000)
    serialized = json.dumps(payload, default=str, sort_keys=True)
    return duration_ms, len(serialized.encode("utf-8")), payload


def execute_companion_case(
    case: CompanionBenchmarkCase,
    *,
    companion_api_key: str,
    project_ref: str,
    base_url: str,
) -> tuple[int, int, dict[str, Any]]:
    assert case.command is not None
    started = time.perf_counter()
    env = os.environ.copy()
    env["SNIPARA_API_KEY"] = companion_api_key
    env["SNIPARA_PROJECT_ID"] = project_ref
    env["SNIPARA_API_URL"] = normalize_companion_api_url(base_url)

    completed = subprocess.run(
        list(case.command),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    if completed.returncode != 0:
        raise RuntimeError(
            f"Companion command failed ({' '.join(case.command)}):\n"
            f"stdout={completed.stdout}\n"
            f"stderr={completed.stderr}"
        )

    payload = json.loads(completed.stdout)
    serialized = json.dumps(payload, default=str, sort_keys=True)
    return duration_ms, len(serialized.encode("utf-8")), payload


async def execute_case(
    case: CompanionBenchmarkCase,
    *,
    project_ref: str,
    base_url: str,
    runs: int,
    prefer_api_key: bool,
    companion_api_key: str,
) -> dict[str, Any]:
    """Execute one companion benchmark case repeatedly and aggregate latency stats."""
    run_results: list[CaseRun] = []
    latest_payload: dict[str, Any] = {}

    if case.mode == "direct":
        cfg = BenchmarkConfig(snipara_project_slug=project_ref, snipara_api_url=base_url)
        client = SniparaClient(
            api_key=cfg.snipara_api_key,
            access_token=cfg.snipara_oauth_token,
            project_slug=project_ref,
            base_url=base_url,
            prefer_api_key=prefer_api_key,
        )
        try:
            for _ in range(runs):
                duration_ms, response_bytes, payload = await execute_direct_case(client, case)
                serialized = json.dumps(payload, default=str, sort_keys=True)
                run_results.append(
                    CaseRun(
                        duration_ms=duration_ms,
                        response_bytes=response_bytes,
                        success=evaluate_success(serialized, case.expected_fragments),
                    )
                )
                latest_payload = payload
        finally:
            await client.close()
    else:
        for _ in range(runs):
            duration_ms, response_bytes, payload = execute_companion_case(
                case,
                companion_api_key=companion_api_key,
                project_ref=project_ref,
                base_url=base_url,
            )
            serialized = json.dumps(payload, default=str, sort_keys=True)
            run_results.append(
                CaseRun(
                    duration_ms=duration_ms,
                    response_bytes=response_bytes,
                    success=evaluate_success(serialized, case.expected_fragments),
                )
            )
            latest_payload = payload

    durations = [run.duration_ms for run in run_results]
    sizes = [run.response_bytes for run in run_results]
    successes = [run.success for run in run_results]

    return {
        "id": case.id,
        "mode": case.mode,
        "description": case.description,
        "comparison_group": case.comparison_group,
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
        "latest_payload": latest_payload,
        "run_details": [asdict(run) for run in run_results],
    }


def build_comparisons(case_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for case in case_reports:
        group = case.get("comparison_group")
        if not group:
            continue
        grouped.setdefault(group, {})[case["mode"]] = case

    comparisons: list[dict[str, Any]] = []
    for group, pair in sorted(grouped.items()):
        direct = pair.get("direct")
        companion = pair.get("companion")
        if not direct or not companion:
            continue

        comparisons.append(
            {
                "group": group,
                "direct_case": direct["id"],
                "companion_case": companion["id"],
                "p50_delta_ms": companion["latency_ms"]["p50"] - direct["latency_ms"]["p50"],
                "p95_delta_ms": companion["latency_ms"]["p95"] - direct["latency_ms"]["p95"],
                "mean_delta_ms": round(
                    companion["latency_ms"]["mean"] - direct["latency_ms"]["mean"], 2
                ),
                "mean_overhead_pct": round(
                    ((companion["latency_ms"]["mean"] / direct["latency_ms"]["mean"]) - 1) * 100,
                    2,
                )
                if direct["latency_ms"]["mean"]
                else None,
            }
        )

    return comparisons


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a concise markdown report."""
    lines = [
        "# Companion Benchmark",
        "",
        f"- Project: `{report['project_ref']}`",
        f"- Base URL: `{report['base_url']}`",
        f"- Companion binary: `{report['companion_bin']}`",
        f"- Runs per case: `{report['runs']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Results",
        "",
        "| Case | Mode | Success | p50 | p95 | Avg bytes |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]

    for case in report["cases"]:
        lines.append(
            "| "
            f"{case['id']} | {case['mode']} | {case['success_rate']:.0%} | "
            f"{case['latency_ms']['p50']} ms | {case['latency_ms']['p95']} ms | "
            f"{int(case['response_bytes']['mean'])} |"
        )

    comparisons = report.get("comparisons") or []
    if comparisons:
        lines.extend(["", "## Direct vs Companion", "", "| Group | p50 Δ | p95 Δ | Mean overhead |", "| --- | ---: | ---: | ---: |"])
        for comparison in comparisons:
            lines.append(
                "| "
                f"{comparison['group']} | {comparison['p50_delta_ms']} ms | "
                f"{comparison['p95_delta_ms']} ms | {comparison['mean_overhead_pct']}% |"
            )

    return "\n".join(lines) + "\n"


async def run_benchmark(
    *,
    project_ref: str,
    base_url: str,
    runs: int,
    output_dir: Path,
    companion_bin: str,
    prefer_api_key: bool,
) -> dict[str, Any]:
    """Run the companion benchmark and write JSON/markdown reports."""
    if not shutil.which(companion_bin):
        raise FileNotFoundError(f"Companion binary not found on PATH: {companion_bin}")

    companion_api_key = load_project_api_key(project_ref) or os.getenv("SNIPARA_API_KEY")
    if not companion_api_key:
        raise RuntimeError(
            "Companion benchmark requires a project API key. "
            "Either set SNIPARA_API_KEY or ensure ~/.snipara/tokens.json contains api_key "
            f"for project '{project_ref}'."
        )

    case_reports = [
        await execute_case(
            case,
            project_ref=project_ref,
            base_url=base_url,
            runs=runs,
            prefer_api_key=prefer_api_key,
            companion_api_key=companion_api_key,
        )
        for case in default_cases(companion_bin)
    ]

    report = {
        "project_ref": project_ref,
        "base_url": base_url,
        "companion_bin": companion_bin,
        "runs": runs,
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": case_reports,
        "comparisons": build_comparisons(case_reports),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"companion_benchmark_{timestamp}.json"
    md_path = output_dir / f"companion_benchmark_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(render_markdown_report(report))

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic snipara-companion vs hosted MCP benchmarks."
    )
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
    parser.add_argument("--runs", type=int, default=5, help="Runs per case")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "reports"),
        help="Directory for JSON and markdown reports",
    )
    parser.add_argument(
        "--companion-bin",
        default="rlm-hook",
        help="Companion binary to execute",
    )
    parser.add_argument(
        "--prefer-api-key",
        action="store_true",
        help="Skip local OAuth tokens and authenticate direct MCP calls with SNIPARA_API_KEY",
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
            companion_bin=args.companion_bin,
            prefer_api_key=args.prefer_api_key,
        )
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
