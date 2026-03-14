"""
Snipara Benchmark Suite

Compares LLM performance with and without Snipara context optimization.
Measures: token efficiency, context quality, hallucination rate, answer accuracy.

Usage:
    python -m benchmarks.runner --all
    python -m benchmarks.runner --token-efficiency
    python -m benchmarks.runner --hallucination
"""

from .config import BenchmarkConfig
from .runner import run_benchmarks

__all__ = ["BenchmarkConfig", "run_benchmarks"]
