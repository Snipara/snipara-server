"""MoltBot resolved issues dataset for benchmarking.

Contains test cases derived from real resolved GitHub issues/PRs from MoltBot.
Each test case represents a verified fix with:
- query: The problem description / question
- expected_answer: Reference solution from the actual fix
- relevant_sections: Code locations that should be retrieved
- ground_truth_claims: Verifiable facts from the implementation
- difficulty: easy, medium, hard
- category: bug_fix, validation, streaming, media, edge_case
- source: PR reference in MoltBot repository

This dataset tests Snipara/RLM-Runtime's ability to:
1. Retrieve relevant code context for real-world issues
2. Understand fix patterns from codebase analysis
3. Guide agents toward correct solutions
"""

from pathlib import Path
from typing import Optional


# ============ PR #7277 - AbortSignal Validation ============
ABORTSIGNAL_TEST_CASES = [
    {
        "id": "moltbot_7277_abortsignal_validation",
        "query": "How do I safely combine multiple AbortSignals in environments where AbortSignal.any() might not exist?",
        "context_query": "AbortSignal combine multiple signals AbortSignal.any fallback AbortController addEventListener",
        "expected_answer": (
            "Check if AbortSignal.any exists before calling it using `typeof AbortSignal.any === 'function'`. "
            "If it exists, use `AbortSignal.any([signalA, signalB])`. If not, create a fallback: "
            "instantiate a new AbortController, add 'abort' event listeners to both signals that "
            "call controller.abort(), and return controller.signal. Also check if either signal is "
            "already aborted before combining."
        ),
        "relevant_sections": [
            "pi-tools.abort.ts",
            "combineAbortSignals",
            "wrapToolWithAbortSignal",
        ],
        "ground_truth_claims": [
            "Check typeof AbortSignal.any === 'function' before calling",
            "Fall back to AbortController with addEventListener pattern",
            "Check if signals are already aborted before combining",
            "Use { once: true } option on event listeners",
            "Return undefined if both signals are undefined",
        ],
        "difficulty": "medium",
        "category": "validation",
        "source": {
            "repo": "MoltBot",
            "pr": 7277,
            "file": "src/agents/pi-tools.abort.ts",
            "lines": "9-23",
        },
    },
    {
        "id": "moltbot_7277_abortsignal_edge_cases",
        "query": "What are the edge cases when combining AbortSignals?",
        "context_query": "AbortSignal edge cases undefined aborted already signal validation",
        "expected_answer": (
            "Edge cases to handle: 1) Both signals undefined - return undefined. "
            "2) One signal undefined - return the defined one. 3) One signal already "
            "aborted - return that signal immediately. 4) AbortSignal.any not available "
            "in runtime - use fallback with AbortController and event listeners."
        ),
        "relevant_sections": [
            "pi-tools.abort.ts",
            "combineAbortSignals",
        ],
        "ground_truth_claims": [
            "Return undefined if both signals are undefined",
            "Return the defined signal if only one is present",
            "Return aborted signal immediately if already aborted",
            "Fallback pattern works when AbortSignal.any is unavailable",
        ],
        "difficulty": "easy",
        "category": "edge_case",
        "source": {
            "repo": "MoltBot",
            "pr": 7277,
            "file": "src/agents/pi-tools.abort.ts",
            "lines": "9-23",
        },
    },
]


# ============ PR #7451 - file_path Alias Validation ============
FILE_PATH_ALIAS_TEST_CASES = [
    {
        "id": "moltbot_7451_file_path_alias",
        "query": "How do I support both 'path' and 'file_path' parameter aliases in read/write tools for Claude Code compatibility?",
        "context_query": "file_path path alias Claude Code parameter validation read write edit tool schema",
        "expected_answer": (
            "Define parameter groups that specify valid aliases, e.g., `{ keys: ['path', 'file_path'], label: 'path (path or file_path)' }`. "
            "At runtime, normalize the parameters by checking which alias was provided and mapping to "
            "the canonical name. The schema should include both parameters with the aliased one marked "
            "as optional. Apply sandbox path guards to both the canonical and aliased parameters."
        ),
        "relevant_sections": [
            "pi-tools.read.ts",
            "CLAUDE_PARAM_GROUPS",
            "createReadTool",
            "createWriteTool",
            "createEditTool",
        ],
        "ground_truth_claims": [
            "CLAUDE_PARAM_GROUPS defines parameter aliases",
            "Read tool accepts both 'path' and 'file_path'",
            "Write tool accepts both 'path' and 'file_path'",
            "Edit tool accepts both 'path' and 'file_path'",
            "Sandbox path guards apply to aliased parameters",
            "Parameter groups have labels for error messages",
        ],
        "difficulty": "medium",
        "category": "validation",
        "source": {
            "repo": "MoltBot",
            "pr": 7451,
            "file": "src/agents/pi-tools.read.ts",
            "lines": "93-100",
        },
    },
    {
        "id": "moltbot_7451_schema_compatibility",
        "query": "How should tool schemas be structured for cross-provider compatibility (OpenAI, Anthropic, Google)?",
        "context_query": "tool schema OpenAI Anthropic Claude Gemini compatibility anyOf enum JSON Schema",
        "expected_answer": (
            "Keep schemas union-free by avoiding anyOf/oneOf/allOf. Flatten anyOf-of-literals to enum "
            "for provider compatibility. Inline local $ref before removing unsupported keywords. "
            "Remove unsupported JSON Schema keywords for Cloud Code Assist API compatibility. "
            "Drop null-only union variants without flattening other unions. Clean tuple items schemas."
        ),
        "relevant_sections": [
            "pi-tools.create-clawdbot-coding-tools",
            "flattens anyOf-of-literals to enum",
            "removes unsupported JSON Schema keywords",
        ],
        "ground_truth_claims": [
            "Flatten anyOf-of-literals to enum for provider compatibility",
            "Inline local $ref before removing unsupported keywords",
            "Keep raw core tool schemas union-free",
            "Remove unsupported JSON Schema keywords",
            "Drop null-only union variants",
        ],
        "difficulty": "hard",
        "category": "validation",
        "source": {
            "repo": "MoltBot",
            "pr": 7451,
            "file": "src/agents/pi-tools.create-clawdbot-coding-tools.adds-claude-style-aliases-schemas-without-dropping.test.ts",
        },
    },
]


# ============ PR #7014 - Block Streaming Paragraph Boundaries ============
BLOCK_STREAMING_TEST_CASES = [
    {
        "id": "moltbot_7014_block_streaming_paragraphs",
        "query": "How should block streaming flush content on paragraph boundaries rather than arbitrary positions?",
        "context_query": "block streaming paragraph boundaries flush newline chunking coalesce idle",
        "expected_answer": (
            "Block streaming should be paragraph-aware: only split on blank lines (double newlines), "
            "not single newlines. Configure minChars and maxChars for chunk sizes, with defaults around "
            "800-1200 characters. Use idle timeout (default 1000ms) to coalesce rapid updates. "
            "The breakPreference should be 'paragraph' rather than 'newline' or 'sentence' for most cases."
        ),
        "relevant_sections": [
            "block-streaming.ts",
            "resolveBlockStreamingChunking",
            "BlockStreamingCoalescing",
        ],
        "ground_truth_claims": [
            "Default block stream min is 800 characters",
            "Default block stream max is 1200 characters",
            "Default coalesce idle time is 1000ms",
            "Paragraph-aware chunking splits on blank lines",
            "chunkMode no longer alters block streaming behavior",
            "breakPreference can be paragraph, newline, or sentence",
        ],
        "difficulty": "medium",
        "category": "streaming",
        "source": {
            "repo": "MoltBot",
            "pr": 7014,
            "file": "src/auto-reply/reply/block-streaming.ts",
            "lines": "12-14, 53-80",
        },
    },
    {
        "id": "moltbot_7014_coalesce_config",
        "query": "How do I configure block streaming coalescing per-provider and per-account?",
        "context_query": "block streaming coalesce config provider account telegram discord whatsapp",
        "expected_answer": (
            "Block streaming coalescing can be configured at multiple levels: global defaults in "
            "agents.defaults.blockStreamingChunk, per-provider (e.g., telegram.blockStreamingCoalesce), "
            "and per-account (e.g., telegram.accounts['myaccount'].blockStreamingCoalesce). "
            "The resolution order is: account config > provider config > global defaults."
        ),
        "relevant_sections": [
            "block-streaming.ts",
            "resolveProviderBlockStreamingCoalesce",
            "ProviderBlockStreamingConfig",
        ],
        "ground_truth_claims": [
            "Config can be set per-provider",
            "Config can be set per-account within a provider",
            "Account config overrides provider config",
            "Provider config is resolved by normalizing provider key",
            "Account ID is normalized before lookup",
        ],
        "difficulty": "easy",
        "category": "streaming",
        "source": {
            "repo": "MoltBot",
            "pr": 7014,
            "file": "src/auto-reply/reply/block-streaming.ts",
            "lines": "26-44",
        },
    },
]


# ============ PR #7475 - Skip Audio from Text Extraction ============
MEDIA_UNDERSTANDING_TEST_CASES = [
    {
        "id": "moltbot_7475_skip_audio_extraction",
        "query": "How should media understanding skip audio files when they exceed size limits?",
        "context_query": "skip audio transcription maxBytes attachment size limit media understanding",
        "expected_answer": (
            "Audio transcription should be skipped when the attachment exceeds maxBytes configuration. "
            "The system should check file size before attempting transcription. When skipped, "
            "raise a MediaUnderstandingSkipError rather than failing. This allows the pipeline to "
            "continue processing other attachments while logging that this one was skipped."
        ),
        "relevant_sections": [
            "apply.ts",
            "applyMediaUnderstanding",
            "MediaUnderstandingSkipError",
            "resolveMaxBytes",
        ],
        "ground_truth_claims": [
            "Audio transcription is skipped when attachment exceeds maxBytes",
            "MediaUnderstandingSkipError is used for skip conditions",
            "File size is checked before attempting transcription",
            "Pipeline continues processing other attachments",
            "isMediaUnderstandingSkipError checks error type",
        ],
        "difficulty": "easy",
        "category": "media",
        "source": {
            "repo": "MoltBot",
            "pr": 7475,
            "file": "src/media-understanding/apply.test.ts",
            "lines": "175-178",
        },
    },
    {
        "id": "moltbot_7475_auto_audio_disable",
        "query": "How do I disable automatic audio transcription in MoltBot?",
        "context_query": "auto audio transcription disable skip enabled provider keys",
        "expected_answer": (
            "Auto audio transcription can be disabled by not providing API keys for audio providers "
            "(openai, groq, deepgram, google) or by explicitly disabling it in configuration. "
            "The system uses provider keys to auto-enable audio transcription, so without keys, "
            "the feature remains disabled. You can also configure mediaUnderstanding.audio.enabled = false."
        ),
        "relevant_sections": [
            "runner.ts",
            "AUTO_AUDIO_KEY_PROVIDERS",
            "runner.auto-audio.test.ts",
        ],
        "ground_truth_claims": [
            "Auto audio uses provider keys to auto-enable",
            "Supported audio providers are openai, groq, deepgram, google",
            "Auto audio can be explicitly disabled",
            "Provider keys control automatic enablement",
        ],
        "difficulty": "easy",
        "category": "media",
        "source": {
            "repo": "MoltBot",
            "pr": 7475,
            "file": "src/media-understanding/runner.ts",
            "lines": "52",
        },
    },
]


# ============ PR #7473 - Repair Malformed Tool Calls ============
TOOL_CALL_REPAIR_TEST_CASES = [
    {
        "id": "moltbot_7473_strip_minimax_tool_xml",
        "query": "How do I strip malformed Minimax tool invocations that leak into text content?",
        "context_query": "Minimax tool call XML invoke tag strip malformed text content",
        "expected_answer": (
            "Use stripMinimaxToolCallXml to remove leaked tool invocations. First check if the text "
            "contains 'minimax:tool_call' marker. If so, remove <invoke name='...'>...</invoke> blocks "
            "using regex with non-greedy matching. Also remove stray </minimax:tool_call> closing tags. "
            "This handles cases where Minimax embeds tool calls as XML in text blocks instead of "
            "proper structured tool calls."
        ),
        "relevant_sections": [
            "pi-embedded-utils.ts",
            "stripMinimaxToolCallXml",
            "extractAssistantText",
        ],
        "ground_truth_claims": [
            "Check for minimax:tool_call marker before processing",
            "Remove <invoke ...>...</invoke> blocks with regex",
            "Remove stray </minimax:tool_call> closing tags",
            "Use non-greedy regex to handle multiple invocations",
            "Return original text if no marker found",
        ],
        "difficulty": "medium",
        "category": "bug_fix",
        "source": {
            "repo": "MoltBot",
            "pr": 7473,
            "file": "src/agents/pi-embedded-utils.ts",
            "lines": "6-24",
        },
    },
    {
        "id": "moltbot_7473_strip_downgraded_tool_calls",
        "query": "How do I strip downgraded tool call text representations from Gemini history replay?",
        "context_query": "downgraded tool call text Gemini history replay Tool Call Tool Result strip",
        "expected_answer": (
            "Use stripDowngradedToolCallText to remove text like '[Tool Call: name (ID: ...)]' and "
            "'[Tool Result (ID: ...)]' that appear when replaying history to Gemini without "
            "thought_signature. Check for '[Tool Call' or '[Tool Result' markers first. "
            "Parse JSON-ish content following the markers using balanced bracket matching. "
            "Preserve text around the tool call blocks."
        ),
        "relevant_sections": [
            "pi-embedded-utils.ts",
            "stripDowngradedToolCallText",
            "consumeJsonish",
        ],
        "ground_truth_claims": [
            "Check for [Tool Call or [Tool Result markers",
            "Use balanced bracket matching to find JSON content",
            "Preserve text before and after tool call blocks",
            "Handle multiple tool calls and results in one message",
            "Return original text if no markers found",
        ],
        "difficulty": "hard",
        "category": "bug_fix",
        "source": {
            "repo": "MoltBot",
            "pr": 7473,
            "file": "src/agents/pi-embedded-utils.ts",
            "lines": "26-80",
        },
    },
]


# ============ COMBINE ALL TEST CASES ============
MOLTBOT_TEST_CASES = (
    ABORTSIGNAL_TEST_CASES
    + FILE_PATH_ALIAS_TEST_CASES
    + BLOCK_STREAMING_TEST_CASES
    + MEDIA_UNDERSTANDING_TEST_CASES
    + TOOL_CALL_REPAIR_TEST_CASES
)


class MoltbotIssuesDataset:
    """Dataset of resolved issues from MoltBot for benchmarking context retrieval."""

    def __init__(self, moltbot_dir: Optional[Path] = None):
        """Initialize dataset.

        Args:
            moltbot_dir: Directory containing MoltBot codebase.
                        Defaults to ~/Devs/MoltBot if not specified.
        """
        self.moltbot_dir = moltbot_dir or Path.home() / "Devs" / "MoltBot"
        self._full_docs: Optional[str] = None

    def load_full_docs(self) -> str:
        """Load full documentation content (simulates 'without Snipara').

        Loads the source files referenced in test cases to simulate having
        all relevant code available without optimization.
        """
        if self._full_docs is not None:
            return self._full_docs

        content_parts = []

        # Load CLAUDE.md if exists
        claude_md = self.moltbot_dir / "CLAUDE.md"
        if claude_md.exists():
            content_parts.append(f"# CLAUDE.md\n\n{claude_md.read_text()}")

        # Load README.md if exists
        readme_md = self.moltbot_dir / "README.md"
        if readme_md.exists():
            content_parts.append(f"# README.md\n\n{readme_md.read_text()}")

        # Load all source files referenced in test cases
        source_files = set()
        for case in MOLTBOT_TEST_CASES:
            source = case.get("source", {})
            file_path = source.get("file")
            if file_path:
                source_files.add(file_path)

        for file_path in sorted(source_files):
            full_path = self.moltbot_dir / file_path
            if full_path.exists():
                content_parts.append(f"# {file_path}\n\n```typescript\n{full_path.read_text()}\n```")

        self._full_docs = "\n\n---\n\n".join(content_parts)
        return self._full_docs

    def prepare_contexts(self, max_tokens_with: int = 4000) -> dict:
        """Prepare both context versions for all test cases.

        Returns:
            Dict mapping case_id to {'with_snipara': str, 'without_snipara': str}
        """
        full_docs = self.load_full_docs()
        contexts = {}

        for case in self.test_cases:
            case_id = case["id"]
            contexts[case_id] = {
                "with_snipara": self.get_relevant_context(case_id) or "",
                "without_snipara": full_docs,
            }

        return contexts

    @property
    def test_cases(self) -> list[dict]:
        """Get all test cases."""
        return MOLTBOT_TEST_CASES

    def get_test_case(self, case_id: str) -> Optional[dict]:
        """Get a specific test case by ID."""
        for case in MOLTBOT_TEST_CASES:
            if case["id"] == case_id:
                return case
        return None

    def get_by_difficulty(self, difficulty: str) -> list[dict]:
        """Get test cases by difficulty level.

        Args:
            difficulty: 'easy', 'medium', or 'hard'
        """
        return [c for c in MOLTBOT_TEST_CASES if c.get("difficulty") == difficulty]

    def get_by_category(self, category: str) -> list[dict]:
        """Get test cases by category.

        Args:
            category: 'bug_fix', 'validation', 'streaming', 'media', or 'edge_case'
        """
        return [c for c in MOLTBOT_TEST_CASES if c.get("category") == category]

    def get_by_pr(self, pr_number: int) -> list[dict]:
        """Get test cases for a specific PR.

        Args:
            pr_number: The GitHub PR number
        """
        return [
            c for c in MOLTBOT_TEST_CASES
            if c.get("source", {}).get("pr") == pr_number
        ]

    def get_summary(self) -> dict:
        """Get summary statistics of the dataset."""
        difficulties = {}
        categories = {}
        prs = {}

        for case in MOLTBOT_TEST_CASES:
            diff = case.get("difficulty", "unknown")
            cat = case.get("category", "unknown")
            pr = case.get("source", {}).get("pr", "unknown")

            difficulties[diff] = difficulties.get(diff, 0) + 1
            categories[cat] = categories.get(cat, 0) + 1
            prs[pr] = prs.get(pr, 0) + 1

        return {
            "total_cases": len(MOLTBOT_TEST_CASES),
            "by_difficulty": difficulties,
            "by_category": categories,
            "by_pr": prs,
            "source_repo": "MoltBot",
        }

    def load_source_file(self, file_path: str) -> Optional[str]:
        """Load source file content from MoltBot.

        Args:
            file_path: Relative path within MoltBot repo (e.g., 'src/agents/pi-tools.abort.ts')
        """
        full_path = self.moltbot_dir / file_path
        if full_path.exists():
            return full_path.read_text()
        return None

    def get_relevant_context(self, case_id: str) -> Optional[str]:
        """Get relevant source code context for a test case.

        This loads the actual source file referenced in the test case.
        """
        case = self.get_test_case(case_id)
        if not case:
            return None

        source = case.get("source", {})
        file_path = source.get("file")
        if not file_path:
            return None

        return self.load_source_file(file_path)


# Convenience function
def load_dataset(moltbot_dir: Optional[Path] = None) -> MoltbotIssuesDataset:
    """Load the MoltBot issues dataset."""
    return MoltbotIssuesDataset(moltbot_dir)


# Quick test when run directly
if __name__ == "__main__":
    dataset = load_dataset()
    summary = dataset.get_summary()
    print(f"MoltBot Issues Dataset")
    print(f"=" * 40)
    print(f"Total test cases: {summary['total_cases']}")
    print(f"\nBy difficulty:")
    for diff, count in summary['by_difficulty'].items():
        print(f"  {diff}: {count}")
    print(f"\nBy category:")
    for cat, count in summary['by_category'].items():
        print(f"  {cat}: {count}")
    print(f"\nBy PR:")
    for pr, count in summary['by_pr'].items():
        print(f"  #{pr}: {count}")
