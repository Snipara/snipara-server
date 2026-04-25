"""Targeted hybrid-search regression benchmark for the audit cases.

This benchmark uses a small, controlled corpus that mirrors the sections
discussed in the Claude Code audit:
- model selection guidance
- gstack browser architecture
- UI/UX preferences

It is intentionally independent from the remote project index so we can
measure `keyword`, `semantic`, and `hybrid` ranking quality even when the
hosted backend has no indexed sections.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass

from src.engine.core.document import Section
from src.engine.scoring import (
    adjust_score_for_query_intent,
    calculate_keyword_score,
    calculate_semantic_scores,
    compute_keyword_weights,
    expand_keywords,
    extract_keywords,
    hybrid_search,
    is_list_query,
)
from src.engine.scoring.rrf_fusion import normalize_scores_graded
from src.services.embeddings import EmbeddingsService, LIGHT_MODEL_NAME


@dataclass(frozen=True)
class QueryCase:
    id: str
    query: str
    expected_section_id: str
    rationale: str


@dataclass(frozen=True)
class ModeResult:
    query_id: str
    mode: str
    top_section_id: str | None
    top_title: str | None
    top_score: float | None
    reciprocal_rank: float
    found_rank: int | None
    top_titles: list[str]


def build_audit_sections() -> list[Section]:
    """Build the controlled benchmark corpus."""
    docs = [
        (
            "model-selection.md",
            [
                (
                    "HAIKU (Fast & Cheap)",
                    "Use Haiku for sub-agents, broad fan-out tasks, and quick iterative checks. "
                    "It is the default recommendation when the task is bounded and cost-sensitive.",
                ),
                (
                    "SONNET (Balanced)",
                    "Use Sonnet for mainline implementation work, synthesis, and most product tasks. "
                    "It balances quality, speed, and reasoning depth for general engineering work.",
                ),
                (
                    "OPUS (Most Capable)",
                    "Reserve Opus for security audits, deep code review, hard debugging, and high-stakes "
                    "architecture work where reasoning quality matters more than speed.",
                ),
                (
                    "Performance Impact",
                    "Haiku is fastest and cheapest, Sonnet is balanced, and Opus is slowest but strongest. "
                    "Pick the model based on workload shape and quality requirements.",
                ),
            ],
        ),
        (
            "gstack-architecture.md",
            [
                (
                    "Gstack Browser Architecture",
                    "The browser daemon manages browser lifecycle, stack adapters, and request orchestration. "
                    "It coordinates sessions and delegates stack-specific behavior to adapters.",
                ),
                (
                    "The Daemon Model",
                    "The daemon model explains why a long-lived browser process improves throughput and "
                    "reduces startup overhead for repeated automation tasks.",
                ),
                (
                    "Security Model",
                    "The security model covers bearer tokens, trust boundaries, and process isolation. "
                    "It defines how the daemon authenticates and constrains incoming requests.",
                ),
                (
                    "Port Selection",
                    "On startup, the browser daemon probes the preferred port and falls back to the next "
                    "available port when a collision is detected. The retry path is deterministic and avoids "
                    "reusing an occupied port.",
                ),
                (
                    "Available Stacks",
                    "Supported stacks include html-tailwind, react, vue, and svelte. Stack selection controls "
                    "template generation, framework adapters, and build pipeline assumptions.",
                ),
            ],
        ),
        (
            "ui-ux-pro-max.md",
            [
                (
                    "Preferred Visual Style",
                    "The preferred direction is neumorphic, tactile, and polished rather than flat default UI. "
                    "Interfaces should feel intentional and visually soft without losing clarity.",
                ),
                (
                    "Common Rules for Professional UI",
                    "Choose a strong visual direction, avoid generic component soup, and maintain contrast. "
                    "Typography, hierarchy, and spacing should support fast comprehension.",
                ),
                (
                    "Light/Dark Mode Contrast",
                    "Light and dark themes need explicit contrast checks so text, icons, and surfaces remain "
                    "readable. Never assume a palette works in both modes without validation.",
                ),
            ],
        ),
    ]

    sections: list[Section] = []
    for file_name, file_sections in docs:
        line = 1
        for index, (title, body) in enumerate(file_sections, start=1):
            content = f"## {title}\n\n{body}"
            start_line = line
            end_line = line + content.count("\n")
            sections.append(
                Section(
                    id=f"{file_name}:{index}",
                    title=title,
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                    level=2,
                )
            )
            line = end_line + 1
    return sections


def build_query_cases() -> list[QueryCase]:
    """Regression cases derived from the audit findings."""
    return [
        QueryCase(
            id="security_audit_model",
            query="which model should I use for a security audit",
            expected_section_id="model-selection.md:3",
            rationale="Selection intent should favor Opus over generic headings containing 'model' or 'security'.",
        ),
        QueryCase(
            id="sub_agent_model",
            query="which model should I use for sub-agents",
            expected_section_id="model-selection.md:1",
            rationale="Sub-agent recommendation should prefer Haiku rather than generic performance guidance.",
        ),
        QueryCase(
            id="port_collisions",
            query="how does the gstack browser daemon handle port collisions",
            expected_section_id="gstack-architecture.md:4",
            rationale="Port collision handling should outrank daemon/security/stack distractors.",
        ),
        QueryCase(
            id="ui_style",
            query="what UI style is preferred",
            expected_section_id="ui-ux-pro-max.md:1",
            rationale="Preference queries should retrieve the explicit preferred visual style section.",
        ),
    ]


def _keyword_scores(sections: list[Section], query: str) -> dict[str, float]:
    keywords = expand_keywords(extract_keywords(query))
    keyword_weights = compute_keyword_weights(sections, keywords)
    list_query = is_list_query(query)
    return {
        section.id: calculate_keyword_score(
            section,
            keywords,
            list_query,
            keyword_weights=keyword_weights,
            query=query,
        )
        for section in sections
    }


def _semantic_scores_to_ranked(scores: dict[str, float]) -> list[tuple[str, float]]:
    ranked = sorted(
        ((section_id, score) for section_id, score in scores.items() if score > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    return normalize_scores_graded(ranked)


def _top_titles_from_ranked(
    ranked: list[tuple[str, float]], section_map: dict[str, Section], limit: int
) -> list[str]:
    return [section_map[section_id].title for section_id, _ in ranked[:limit]]


def _build_mode_result(
    *,
    query_id: str,
    mode: str,
    ranked: list[tuple[str, float]],
    expected_section_id: str,
    section_map: dict[str, Section],
    top_k: int,
) -> ModeResult:
    top_section_id = ranked[0][0] if ranked else None
    top_title = section_map[top_section_id].title if top_section_id else None
    top_score = ranked[0][1] if ranked else None
    found_rank = next(
        (index for index, (section_id, _) in enumerate(ranked, start=1) if section_id == expected_section_id),
        None,
    )
    reciprocal_rank = 1.0 / found_rank if found_rank else 0.0
    return ModeResult(
        query_id=query_id,
        mode=mode,
        top_section_id=top_section_id,
        top_title=top_title,
        top_score=top_score,
        reciprocal_rank=reciprocal_rank,
        found_rank=found_rank,
        top_titles=_top_titles_from_ranked(ranked, section_map, top_k),
    )


async def run_benchmark(top_k: int = 3) -> dict:
    """Run the targeted regression benchmark."""
    sections = build_audit_sections()
    cases = build_query_cases()
    section_map = {section.id: section for section in sections}
    embeddings = EmbeddingsService.get_instance(LIGHT_MODEL_NAME)

    results: list[ModeResult] = []

    for case in cases:
        kw_scores = _keyword_scores(sections, case.query)
        kw_ranked = normalize_scores_graded(
            sorted(
                ((section_id, score) for section_id, score in kw_scores.items() if score > 0),
                key=lambda item: item[1],
                reverse=True,
            )
        )
        results.append(
            _build_mode_result(
                query_id=case.id,
                mode="keyword",
                ranked=kw_ranked,
                expected_section_id=case.expected_section_id,
                section_map=section_map,
                top_k=top_k,
            )
        )

        sem_scores = await calculate_semantic_scores(
            query=case.query,
            sections=sections,
            embeddings_service=embeddings,
            max_sections=len(sections),
        )
        sem_scores = {
            section.id: adjust_score_for_query_intent(
                section,
                case.query,
                sem_scores.get(section.id, 0.0) * 100,
                keywords=expand_keywords(extract_keywords(case.query)),
            ) / 100.0
            for section in sections
        }
        sem_ranked = _semantic_scores_to_ranked(sem_scores)
        results.append(
            _build_mode_result(
                query_id=case.id,
                mode="semantic",
                ranked=sem_ranked,
                expected_section_id=case.expected_section_id,
                section_map=section_map,
                top_k=top_k,
            )
        )

        hybrid_ranked = hybrid_search(kw_scores, sem_scores, case.query)
        results.append(
            _build_mode_result(
                query_id=case.id,
                mode="hybrid",
                ranked=hybrid_ranked,
                expected_section_id=case.expected_section_id,
                section_map=section_map,
                top_k=top_k,
            )
        )

    summary = {}
    for mode in ("keyword", "semantic", "hybrid"):
        mode_results = [result for result in results if result.mode == mode]
        summary[mode] = {
            "top1_accuracy": sum(1 for result in mode_results if result.found_rank == 1) / len(mode_results),
            "mrr": sum(result.reciprocal_rank for result in mode_results) / len(mode_results),
            "queries": len(mode_results),
        }

    return {
        "summary": summary,
        "cases": [
            {
                "id": case.id,
                "query": case.query,
                "expected_section_id": case.expected_section_id,
                "expected_title": section_map[case.expected_section_id].title,
                "rationale": case.rationale,
                "results": [
                    {
                        "mode": result.mode,
                        "top_title": result.top_title,
                        "top_score": result.top_score,
                        "found_rank": result.found_rank,
                        "reciprocal_rank": result.reciprocal_rank,
                        "top_titles": result.top_titles,
                    }
                    for result in results
                    if result.query_id == case.id
                ],
            }
            for case in cases
        ],
    }


def _print_report(report: dict) -> None:
    print("\nHybrid Audit Regression Benchmark")
    print("=" * 40)
    for mode, metrics in report["summary"].items():
        print(
            f"{mode:8s} top1={metrics['top1_accuracy']:.0%} "
            f"mrr={metrics['mrr']:.3f} queries={metrics['queries']}"
        )

    print("\nCases")
    print("-" * 40)
    for case in report["cases"]:
        print(f"{case['id']}: {case['query']}")
        print(f"  expected: {case['expected_title']}")
        for result in case["results"]:
            rank = result["found_rank"] if result["found_rank"] is not None else "-"
            print(
                f"  {result['mode']:8s} top={result['top_title']} "
                f"rank={rank} top_titles={', '.join(result['top_titles'])}"
            )
        print()


async def _main(args: argparse.Namespace) -> int:
    report = await run_benchmark(top_k=args.top_k)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of the text report")
    parser.add_argument("--top-k", type=int, default=3, help="How many top titles to show per mode")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
