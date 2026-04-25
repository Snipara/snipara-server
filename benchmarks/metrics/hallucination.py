"""Hallucination Detection Benchmark.

Measures how often the LLM fabricates information when given different
amounts of context.

IMPROVED METHODOLOGY:
Instead of just checking grounding against provided context (which unfairly
penalizes focused context), we use a two-stage approach:

1. Check grounding against PROVIDED context (context_grounded)
2. Check grounding against FULL documentation (factually_correct)
3. Distinguish between:
   - TRUE HALLUCINATIONS: Claims not in any documentation
   - CONTEXT GAPS: Claims that are true but not in provided context
   - PROPERLY GROUNDED: Claims found in provided context

This gives a fair comparison because:
- Snipara won't be penalized for not including irrelevant sections
- True hallucinations are properly identified regardless of context size

LARGE DOCS HANDLING:
For documents exceeding MAX_REFERENCE_CHARS (100K), we use RLM-Runtime's
execute_python for programmatic verification instead of passing to LLM.
This avoids context overflow and provides deterministic keyword matching.
"""

import json
import os
import re
from typing import Optional

from openai import AsyncOpenAI

from ..config import THRESHOLDS
from ..snipara_client import SniparaClient
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


# Prompt for extracting claims from a response
CLAIM_EXTRACTION_PROMPT = """Extract all factual claims from the following response.
A claim is a statement that can be verified as true or false.

Response:
{response}

Output a JSON array of claims. Each claim should be:
- A single, atomic fact
- Directly stated or strongly implied in the response
- Not an opinion or subjective statement

Example output format:
["The system uses PostgreSQL for database storage", "Authentication is handled by NextAuth.js"]

Output only the JSON array, nothing else."""


# Prompt for checking if claims are grounded in context
GROUNDING_CHECK_PROMPT = """Determine if each claim is supported by the given context.

Context:
{context}

Claims to verify:
{claims}

For each claim, output a JSON object with:
- "claim": the claim text
- "grounded": true if the claim is supported by the context, false if not
- "evidence": quote from context supporting the claim, or "NOT_FOUND" if not grounded
- "confidence": "high", "medium", or "low"

Output only a JSON array of these objects, nothing else."""


# Prompt for checking factual accuracy against ground truth
FACTUAL_CHECK_PROMPT = """Determine if each claim is factually accurate based on the reference documentation.

Reference Documentation:
{full_docs}

Claims to verify:
{claims}

For each claim, determine if it is:
- CORRECT: The claim matches information in the documentation
- INCORRECT: The claim contradicts information in the documentation
- UNVERIFIABLE: The documentation doesn't contain information to verify this claim

Output a JSON array with:
- "claim": the claim text
- "status": "correct", "incorrect", or "unverifiable"
- "evidence": relevant quote if correct, contradiction if incorrect, or "NOT_FOUND"

Output only the JSON array, nothing else."""


class HallucinationBenchmark(BenchmarkMetric):
    """Benchmark measuring TRUE hallucination rate using two-stage verification.

    IMPROVED METHODOLOGY:
    1. Generate response with provided context
    2. Extract factual claims from response
    3. Check claims against FULL documentation (not just provided context)
    4. Categorize claims as:
       - CORRECT: Factually accurate (found in full docs)
       - INCORRECT: Factually wrong (contradicts full docs) = TRUE HALLUCINATION
       - UNVERIFIABLE: Not mentioned in docs (may or may not be true)

    This gives fair comparison because both contexts are evaluated against
    the same ground truth (full documentation).

    LARGE DOCS HANDLING:
    For docs > 100K chars, uses RLM-Runtime execute_python for programmatic
    verification instead of LLM-based checking (avoids context overflow).
    """

    name = "hallucination"
    description = "Measures TRUE hallucination rate (factually incorrect claims)"

    # Threshold for using execute_python instead of LLM verification
    LARGE_DOCS_THRESHOLD = 100000  # 100K chars

    def __init__(self, config):
        super().__init__(config)
        self._client: Optional[AsyncOpenAI] = None
        self._full_docs: Optional[str] = None
        self._snipara_client: Optional[SniparaClient] = None
        self._docs_indexed_in_repl: bool = False

    def set_full_docs(self, full_docs: str):
        """Set the full documentation for factual verification."""
        self._full_docs = full_docs
        self._docs_indexed_in_repl = False  # Reset when docs change

    def set_snipara_client(self, client: SniparaClient):
        """Set Snipara client for execute_python calls."""
        self._snipara_client = client

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
        """Run hallucination detection for a single test case."""
        query = test_case.get("query", "")
        ground_truth_claims = test_case.get("ground_truth_claims", [])

        # Store full docs for factual verification
        if self._full_docs is None:
            self._full_docs = without_snipara_context

        client = await self._get_client()

        # Generate responses with both contexts
        response_with = await self._generate_response(client, query, with_snipara_context)
        response_without = await self._generate_response(client, query, without_snipara_context)

        # Analyze with TWO-STAGE verification (against full docs)
        metrics_with = await self._analyze_hallucinations_v2(
            client, response_with, with_snipara_context, ground_truth_claims
        )
        metrics_without = await self._analyze_hallucinations_v2(
            client, response_without, without_snipara_context, ground_truth_claims
        )

        # Calculate improvements (lower true_hallucination = better)
        true_halluc_reduction = (
            metrics_without["true_hallucination_rate"] - metrics_with["true_hallucination_rate"]
        )
        accuracy_improvement = (
            metrics_with["factual_accuracy"] - metrics_without["factual_accuracy"]
        )

        return BenchmarkResult(
            benchmark_name=self.name,
            test_case=test_case.get("id", query[:50]),
            with_snipara={
                "total_claims": metrics_with["total_claims"],
                "correct_claims": metrics_with["correct_claims"],
                "incorrect_claims": metrics_with["incorrect_claims"],
                "unverifiable_claims": metrics_with["unverifiable_claims"],
                "factual_accuracy": round(metrics_with["factual_accuracy"], 3),
                "true_hallucination_rate": round(metrics_with["true_hallucination_rate"], 3),
                "context_grounded": metrics_with["context_grounded"],
                "response_length": len(response_with),
            },
            without_snipara={
                "total_claims": metrics_without["total_claims"],
                "correct_claims": metrics_without["correct_claims"],
                "incorrect_claims": metrics_without["incorrect_claims"],
                "unverifiable_claims": metrics_without["unverifiable_claims"],
                "factual_accuracy": round(metrics_without["factual_accuracy"], 3),
                "true_hallucination_rate": round(metrics_without["true_hallucination_rate"], 3),
                "context_grounded": metrics_without["context_grounded"],
                "response_length": len(response_without),
            },
            improvement={
                "true_hallucination_reduction": round(true_halluc_reduction, 3),
                "accuracy_improvement": round(accuracy_improvement, 3),
                "hallucination_reduction_pct": round(
                    true_halluc_reduction * 100 if metrics_without["true_hallucination_rate"] > 0 else 0, 1
                ),
            },
        )

    async def _generate_response(
        self, client: AsyncOpenAI, query: str, context: str
    ) -> str:
        """Generate LLM response given query and context."""
        system_prompt = (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Only use information from the context. If the context doesn't contain the answer, "
            "say so clearly. Do not make up information."
        )

        user_prompt = f"""Context:
{context}

Question: {query}

Answer based only on the provided context:"""

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
                    temperature=0.0,  # Reduce randomness for more grounded responses
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error generating response: {e}"

    async def _analyze_hallucinations_v2(
        self,
        client: AsyncOpenAI,
        response: str,
        provided_context: str,
        ground_truth_claims: list[str],
    ) -> dict:
        """Two-stage hallucination analysis.

        Stage 1: Extract claims from response
        Stage 2: Verify claims against FULL documentation (not just provided context)

        Returns metrics that fairly compare focused vs full context.
        """
        # Extract claims from response
        claims = await self._extract_claims(client, response)

        if not claims:
            return {
                "total_claims": 0,
                "correct_claims": 0,
                "incorrect_claims": 0,
                "unverifiable_claims": 0,
                "factual_accuracy": 1.0,
                "true_hallucination_rate": 0.0,
                "context_grounded": 0,
            }

        # Stage 1: Check grounding in PROVIDED context (informational only)
        context_grounding = await self._check_grounding(client, claims, provided_context)
        context_grounded = sum(1 for r in context_grounding if r.get("grounded", False))

        # Stage 2: Check factual accuracy against FULL documentation
        factual_results = await self._check_factual_accuracy(client, claims, ground_truth_claims)

        correct = sum(1 for r in factual_results if r.get("status") == "correct")
        incorrect = sum(1 for r in factual_results if r.get("status") == "incorrect")
        unverifiable = sum(1 for r in factual_results if r.get("status") == "unverifiable")

        total = len(claims)
        verifiable = correct + incorrect

        return {
            "total_claims": total,
            "correct_claims": correct,
            "incorrect_claims": incorrect,  # TRUE hallucinations
            "unverifiable_claims": unverifiable,
            "factual_accuracy": correct / verifiable if verifiable > 0 else 1.0,
            "true_hallucination_rate": incorrect / total if total > 0 else 0.0,
            "context_grounded": context_grounded,
        }

    async def _extract_claims(self, client: AsyncOpenAI, response: str) -> list[str]:
        """Extract factual claims from a response using LLM."""
        try:
            result = await client.chat.completions.create(
                model=self.config.model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": CLAIM_EXTRACTION_PROMPT.format(response=response),
                }],
            )
            claims_text = (result.choices[0].message.content or "").strip()
            # Handle markdown code blocks
            if "```" in claims_text:
                claims_text = re.search(r'```(?:json)?\s*(.*?)\s*```', claims_text, re.DOTALL)
                claims_text = claims_text.group(1) if claims_text else "[]"
            claims = json.loads(claims_text)
            return claims if isinstance(claims, list) else []
        except (json.JSONDecodeError, Exception):
            # Fallback: split by sentences if JSON parsing fails
            sentences = re.split(r'[.!?]+', response)
            return [s.strip() for s in sentences if len(s.strip()) > 20]

    async def _check_grounding(
        self, client: AsyncOpenAI, claims: list[str], context: str
    ) -> list[dict]:
        """Check if claims are grounded in provided context."""
        if not claims:
            return []

        try:
            result = await client.chat.completions.create(
                model=self.config.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": GROUNDING_CHECK_PROMPT.format(
                        context=context[:10000],
                        claims=json.dumps(claims),
                    ),
                }],
            )
            results_text = (result.choices[0].message.content or "").strip()
            if "```" in results_text:
                results_text = re.search(r'```(?:json)?\s*(.*?)\s*```', results_text, re.DOTALL)
                results_text = results_text.group(1) if results_text else "[]"
            return json.loads(results_text)
        except (json.JSONDecodeError, Exception):
            # Fallback: simple keyword matching
            results = []
            for claim in claims:
                words = set(claim.lower().split())
                context_lower = context.lower()
                matches = sum(1 for w in words if w in context_lower and len(w) > 3)
                grounded = matches >= len(words) * 0.5
                results.append({"claim": claim, "grounded": grounded, "confidence": "low"})
            return results

    async def _verify_claims_with_execute_python(
        self, claims: list[str], ground_truth_claims: list[str]
    ) -> list[dict]:
        """Verify claims using RLM-Runtime execute_python for large docs.

        Uses programmatic keyword matching in sandboxed Python environment
        instead of passing full docs to LLM (avoids context overflow).

        Args:
            claims: List of claims to verify
            ground_truth_claims: Known correct claims for comparison

        Returns:
            List of verification results with status (correct/incorrect/unverifiable)
        """
        if not self._snipara_client or not self._full_docs:
            # Fallback to simple keyword matching if no client
            return self._verify_claims_keyword_fallback(claims, ground_truth_claims)

        try:
            # Store docs in REPL context (only once per session)
            if not self._docs_indexed_in_repl:
                # Store docs as JSON-encoded string
                await self._snipara_client.set_repl_context(
                    key="full_docs",
                    value=json.dumps(self._full_docs.lower()),
                    session_id="hallucination_benchmark",
                )
                await self._snipara_client.set_repl_context(
                    key="ground_truth",
                    value=json.dumps([gt.lower() for gt in ground_truth_claims]),
                    session_id="hallucination_benchmark",
                )
                self._docs_indexed_in_repl = True

            # Build verification code
            verification_code = '''
import json
import re

# Claims to verify (passed as JSON)
claims = json.loads(CLAIMS_JSON)

# Already in context: full_docs (str), ground_truth (list)
results = []

for claim in claims:
    claim_lower = claim.lower()
    found_in_gt = False
    found_in_docs = False

    # Check against ground truth claims
    claim_words = set(re.findall(r'\\b\\w{4,}\\b', claim_lower))
    for gt in ground_truth:
        gt_words = set(re.findall(r'\\b\\w{4,}\\b', gt))
        if gt_words and len(claim_words & gt_words) >= len(gt_words) * 0.5:
            found_in_gt = True
            break

    # Check against full docs
    if not found_in_gt:
        key_terms = [w for w in claim_words if len(w) > 4]
        if key_terms:
            matches = sum(1 for t in key_terms if t in full_docs)
            if matches >= len(key_terms) * 0.6:
                found_in_docs = True

    # Determine status
    if found_in_gt:
        status = "correct"
        evidence = "matched ground truth claim"
    elif found_in_docs:
        status = "unverifiable"
        evidence = "keywords found in docs but no direct match"
    else:
        status = "incorrect"
        evidence = "NOT_FOUND - potential hallucination"

    results.append({
        "claim": claim,
        "status": status,
        "evidence": evidence,
    })

result = json.dumps(results)
'''
            # Replace placeholder with actual claims
            verification_code = verification_code.replace(
                "CLAIMS_JSON", json.dumps(json.dumps(claims))
            )

            # Execute verification
            exec_result = await self._snipara_client.execute_python(
                code=verification_code,
                session_id="hallucination_benchmark",
                profile="analysis",  # 120s timeout for large docs
            )

            # Parse result
            if exec_result.get("success") and exec_result.get("result"):
                return json.loads(exec_result["result"])
            elif exec_result.get("output"):
                # Try to extract JSON from output
                output = exec_result["output"]
                if "result =" in output:
                    json_start = output.find("[")
                    json_end = output.rfind("]") + 1
                    if json_start >= 0 and json_end > json_start:
                        return json.loads(output[json_start:json_end])

            # Fallback if execute_python didn't return parseable results
            return self._verify_claims_keyword_fallback(claims, ground_truth_claims)

        except Exception as e:
            print(f"  ⚠️  execute_python failed: {e}, using keyword fallback")
            return self._verify_claims_keyword_fallback(claims, ground_truth_claims)

    def _verify_claims_keyword_fallback(
        self, claims: list[str], ground_truth_claims: list[str]
    ) -> list[dict]:
        """Simple keyword-based verification fallback."""
        results = []
        for claim in claims:
            claim_lower = claim.lower()
            found = False

            # Check against ground truth claims
            for gt in ground_truth_claims:
                gt_words = set(gt.lower().split())
                claim_words = set(claim_lower.split())
                if len(gt_words & claim_words) >= len(gt_words) * 0.5:
                    found = True
                    break

            # If not found in ground truth, check against full docs
            if not found and self._full_docs:
                key_terms = [w for w in claim_lower.split() if len(w) > 4]
                docs_lower = self._full_docs.lower()
                if key_terms:
                    matches = sum(1 for t in key_terms if t in docs_lower)
                    if matches >= len(key_terms) * 0.6:
                        results.append({
                            "claim": claim,
                            "status": "unverifiable",
                            "evidence": "partial keyword match in docs",
                        })
                        continue

            if found:
                results.append({
                    "claim": claim,
                    "status": "correct",
                    "evidence": "keyword match with ground truth",
                })
            else:
                results.append({
                    "claim": claim,
                    "status": "incorrect",
                    "evidence": "NOT_FOUND - potential hallucination",
                })
        return results

    async def _check_factual_accuracy(
        self, client: AsyncOpenAI, claims: list[str], ground_truth_claims: list[str]
    ) -> list[dict]:
        """Check factual accuracy against full documentation and ground truth.

        For large docs (>100K chars), uses execute_python for programmatic
        verification. For smaller docs, uses LLM-based verification.
        """
        if not claims:
            return []

        # For large docs, use execute_python (programmatic verification)
        if self._full_docs and len(self._full_docs) > self.LARGE_DOCS_THRESHOLD:
            print(f"  📊 Large docs ({len(self._full_docs):,} chars), using execute_python for verification")
            return await self._verify_claims_with_execute_python(claims, ground_truth_claims)

        # For smaller docs, use LLM-based verification
        if self._full_docs:
            reference = self._full_docs
        else:
            reference = "\n".join(f"- {c}" for c in ground_truth_claims)

        try:
            result = await client.chat.completions.create(
                model=self.config.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": FACTUAL_CHECK_PROMPT.format(
                        full_docs=reference,
                        claims=json.dumps(claims),
                    ),
                }],
            )
            results_text = (result.choices[0].message.content or "").strip()
            if "```" in results_text:
                results_text = re.search(r'```(?:json)?\s*(.*?)\s*```', results_text, re.DOTALL)
                results_text = results_text.group(1) if results_text else "[]"
            return json.loads(results_text)
        except (json.JSONDecodeError, Exception):
            # Fallback to keyword matching
            return self._verify_claims_keyword_fallback(claims, ground_truth_claims)

    def _generate_summary(
        self, mean_with: dict, mean_without: dict, mean_improvement: dict
    ) -> str:
        """Generate human-readable summary."""
        halluc_with = mean_with.get("true_hallucination_rate", 0)
        halluc_without = mean_without.get("true_hallucination_rate", 0)
        accuracy_with = mean_with.get("factual_accuracy", 0)
        accuracy_without = mean_without.get("factual_accuracy", 0)
        reduction = mean_improvement.get("hallucination_reduction_pct", 0)

        acceptable = halluc_with <= THRESHOLDS["hallucination_acceptable"]
        quality = "excellent" if halluc_with < 0.05 else (
            "acceptable" if acceptable else "needs improvement"
        )

        return (
            f"Hallucination Detection (v2 - True Hallucinations): {quality}\n"
            f"  With Snipara:\n"
            f"    - True hallucination rate: {halluc_with:.1%}\n"
            f"    - Factual accuracy: {accuracy_with:.1%}\n"
            f"  Without Snipara:\n"
            f"    - True hallucination rate: {halluc_without:.1%}\n"
            f"    - Factual accuracy: {accuracy_without:.1%}\n"
            f"  Hallucination reduced by: {reduction:+.1f}%"
        )
