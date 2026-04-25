"""Answer Quality Benchmark.

Measures overall response quality using multiple dimensions:
- Correctness: Is the answer factually correct?
- Completeness: Does it cover all aspects of the question?
- Relevance: Is the answer directly relevant to the question?
- Faithfulness: Is it consistent with the source material?
"""

import json
import os
from typing import Optional

from openai import AsyncOpenAI

from ..config import THRESHOLDS
from .base import BenchmarkMetric, BenchmarkResult


# Supported LLM providers
LLM_PROVIDERS = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-4o-mini",
    },
    "minimax": {
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "default_model": "abab6.5s-chat",
    },
    "together": {
        "api_key_env": "TOGETHER_API_KEY",
        "base_url": None,
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    },
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": None,
        "default_model": "claude-3-5-sonnet-20241022",
    },
}


# Prompt for evaluating answer quality
EVALUATION_PROMPT = """You are an expert evaluator assessing the quality of an AI assistant's response.

Question asked:
{query}

Reference answer (ground truth):
{expected_answer}

Context provided to the assistant:
{context}

Assistant's response:
{response}

Evaluate the response on these dimensions (score 0-10 for each):

1. CORRECTNESS: Is the response factually accurate? Does it match the reference answer?
2. COMPLETENESS: Does the response cover all important aspects of the question?
3. RELEVANCE: Is the response directly relevant to what was asked?
4. FAITHFULNESS: Is the response consistent with the provided context? No made-up info?
5. CLARITY: Is the response clear, well-organized, and easy to understand?

Output a JSON object with:
- "correctness": score 0-10
- "completeness": score 0-10
- "relevance": score 0-10
- "faithfulness": score 0-10
- "clarity": score 0-10
- "overall": weighted average (correctness 30%, completeness 25%, relevance 20%, faithfulness 15%, clarity 10%)
- "issues": list of specific issues found (empty list if none)
- "strengths": list of specific strengths

Output only the JSON object, nothing else."""


class AnswerQualityBenchmark(BenchmarkMetric):
    """Benchmark measuring overall answer quality.

    Uses LLM-as-judge to evaluate responses on multiple dimensions.
    Compares quality with optimized vs. unoptimized context.
    """

    name = "answer_quality"
    description = "Measures correctness, completeness, relevance, and faithfulness"

    def __init__(self, config):
        super().__init__(config)
        self._client: Optional[AsyncOpenAI] = None

    async def _get_client(self) -> AsyncOpenAI:
        """Lazy init LLM client based on provider configuration."""
        if self._client is None:
            # Get API key from provider config or environment
            provider_config = LLM_PROVIDERS.get(self.config.llm_provider, LLM_PROVIDERS["openai"])
            api_key_env = provider_config["api_key_env"]
            
            api_key = self.config.api_key or os.environ.get(api_key_env)
            if not api_key:
                raise ValueError(f"{api_key_env} not configured")
            
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.base_url or provider_config.get("base_url"),
                timeout=60.0,
            )
        return self._client

    async def run_single(
        self,
        test_case: dict,
        with_snipara_context: str,
        without_snipara_context: str,
    ) -> BenchmarkResult:
        """Run answer quality evaluation for a single test case.

        Args:
            test_case: - query: The question to ask
 Must contain:
                               - expected_answer: The reference/correct answer
        """
        query = test_case.get("query", "")
        expected_answer = test_case.get("expected_answer", "")

        client = await self._get_client()

        # Generate responses with both contexts
        response_with = await self._generate_response(client, query, with_snipara_context)
        response_without = await self._generate_response(client, query, without_snipara_context)

        # Evaluate both responses
        eval_with = await self._evaluate_response(
            client, query, expected_answer, with_snipara_context, response_with
        )
        eval_without = await self._evaluate_response(
            client, query, expected_answer, without_snipara_context, response_without
        )

        # Calculate improvements
        improvements = {}
        for metric in ["correctness", "completeness", "relevance", "faithfulness", "clarity", "overall"]:
            with_val = eval_with.get(metric, 0)
            without_val = eval_without.get(metric, 0)
            improvements[f"{metric}_improvement"] = round(with_val - without_val, 2)

        return BenchmarkResult(
            benchmark_name=self.name,
            test_case=test_case.get("id", query[:50]),
            with_snipara={
                "correctness": eval_with.get("correctness", 0),
                "completeness": eval_with.get("completeness", 0),
                "relevance": eval_with.get("relevance", 0),
                "faithfulness": eval_with.get("faithfulness", 0),
                "clarity": eval_with.get("clarity", 0),
                "overall": eval_with.get("overall", 0),
                "issues_count": len(eval_with.get("issues", [])),
                "response_preview": response_with[:200] + "..." if len(response_with) > 200 else response_with,
            },
            without_snipara={
                "correctness": eval_without.get("correctness", 0),
                "completeness": eval_without.get("completeness", 0),
                "relevance": eval_without.get("relevance", 0),
                "faithfulness": eval_without.get("faithfulness", 0),
                "clarity": eval_without.get("clarity", 0),
                "overall": eval_without.get("overall", 0),
                "issues_count": len(eval_without.get("issues", [])),
                "response_preview": response_without[:200] + "..." if len(response_without) > 200 else response_without,
            },
            improvement=improvements,
        )

    async def _generate_response(
        self, client: AsyncOpenAI, query: str, context: str
    ) -> str:
        """Generate LLM response given query and context."""
        system_prompt = (
            "You are a helpful assistant that answers questions based on the provided documentation. "
            "Be accurate, comprehensive, and cite specific details when relevant."
        )

        user_prompt = f"""Documentation:
{context}

Question: {query}

Please provide a detailed and accurate answer:"""

        try:
            # Handle MiniMax-specific format
            if self.config.llm_provider == "minimax":
                response = await client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                )
            else:
                response = await client.chat.completions.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens_response,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error generating response: {e}"

    async def _evaluate_response(
        self,
        client: AsyncOpenAI,
        query: str,
        expected_answer: str,
        context: str,
        response: str,
    ) -> dict:
        """Evaluate response quality using LLM-as-judge."""
        try:
            # Use a more capable model for evaluation if available
            eval_model = self.config.model

            # Handle MiniMax-specific format
            if self.config.llm_provider == "minimax":
                result = await client.chat.completions.create(
                    model=eval_model,
                    messages=[{
                        "role": "user",
                        "content": EVALUATION_PROMPT.format(
                            query=query,
                            expected_answer=expected_answer or "No reference answer provided.",
                            context=context[:8000],  # Limit context for evaluation
                            response=response,
                        ),
                    }],
                    temperature=0.7,
                )
            else:
                result = await client.chat.completions.create(
                    model=eval_model,
                    max_tokens=1000,
                    messages=[{
                        "role": "user",
                        "content": EVALUATION_PROMPT.format(
                            query=query,
                            expected_answer=expected_answer or "No reference answer provided.",
                            context=context[:8000],  # Limit context for evaluation
                            response=response,
                        ),
                    }],
                )
            eval_text = (result.choices[0].message.content or "").strip()
            return json.loads(eval_text)
        except json.JSONDecodeError:
            # Fallback scores
            return self._fallback_evaluation(response, context, expected_answer)
        except Exception as e:
            return {
                "correctness": 0,
                "completeness": 0,
                "relevance": 0,
                "faithfulness": 0,
                "clarity": 0,
                "overall": 0,
                "issues": [str(e)],
                "strengths": [],
            }

    def _fallback_evaluation(
        self, response: str, context: str, expected: str
    ) -> dict:
        """Simple heuristic-based evaluation when LLM evaluation fails."""
        response_lower = response.lower()
        context_lower = context.lower()
        expected_lower = expected.lower() if expected else ""

        # Basic metrics
        has_content = len(response) > 50
        mentions_context_terms = sum(
            1 for word in context_lower.split()[:100]
            if len(word) > 4 and word in response_lower
        )

        # Score estimation
        relevance = min(10, mentions_context_terms / 5) if has_content else 0
        completeness = min(10, len(response) / 100) if has_content else 0

        # Check against expected answer
        if expected:
            expected_words = set(expected_lower.split())
            response_words = set(response_lower.split())
            overlap = len(expected_words & response_words) / len(expected_words) if expected_words else 0
            correctness = overlap * 10
        else:
            correctness = relevance  # Use relevance as proxy

        faithfulness = relevance * 0.8  # Assume somewhat faithful if relevant
        clarity = 7 if has_content else 0

        overall = (
            correctness * 0.30 +
            completeness * 0.25 +
            relevance * 0.20 +
            faithfulness * 0.15 +
            clarity * 0.10
        )

        return {
            "correctness": round(correctness, 1),
            "completeness": round(completeness, 1),
            "relevance": round(relevance, 1),
            "faithfulness": round(faithfulness, 1),
            "clarity": round(clarity, 1),
            "overall": round(overall, 1),
            "issues": ["Fallback evaluation used"],
            "strengths": [],
        }

    def _generate_summary(
        self, mean_with: dict, mean_without: dict, mean_improvement: dict
    ) -> str:
        """Generate human-readable summary."""
        overall_with = mean_with.get("overall", 0)
        overall_without = mean_without.get("overall", 0)
        improvement = mean_improvement.get("overall_improvement", 0)

        # Quality rating
        if overall_with >= 8:
            quality = "excellent"
        elif overall_with >= 6:
            quality = "good"
        elif overall_with >= 4:
            quality = "acceptable"
        else:
            quality = "needs improvement"

        return (
            f"Answer Quality: {quality} ({overall_with:.1f}/10)\n"
            f"  With Snipara:\n"
            f"    - Correctness: {mean_with.get('correctness', 0):.1f}/10\n"
            f"    - Completeness: {mean_with.get('completeness', 0):.1f}/10\n"
            f"    - Faithfulness: {mean_with.get('faithfulness', 0):.1f}/10\n"
            f"  Without Snipara:\n"
            f"    - Overall: {overall_without:.1f}/10\n"
            f"  Quality improvement: {improvement:+.1f} points"
        )
