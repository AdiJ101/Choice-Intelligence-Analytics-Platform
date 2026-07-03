"""
Unit tests for src.pipeline.chunker.

Tests run without a live tokenizer by patching the lazy singleton so
we can exercise all branching logic without the `transformers` dependency.

Requirements: 7.5, 7.8
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: build a minimal fake tokenizer that maps each character to one token
# ---------------------------------------------------------------------------

def _make_fake_tokenizer(char_to_id: dict[str, int] | None = None) -> MagicMock:
    """Return a mock tokenizer where each character is a single token.

    encode(text)  -> list of ints, one per character
    decode(ids)   -> " ".join(chr(i) for i in ids)  (deterministic round-trip)
    """
    tok = MagicMock()

    def _encode(text: str, add_special_tokens: bool = False) -> list[int]:
        return [ord(c) for c in text]

    def _decode(ids: list[int], skip_special_tokens: bool = True) -> str:
        return "".join(chr(i) for i in ids)

    tok.encode.side_effect = _encode
    tok.decode.side_effect = _decode
    return tok


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOversizedChunkError(unittest.TestCase):
    """OversizedChunkError carries chunk_index and token_count."""

    def test_attributes_are_set(self):
        from src.pipeline.chunker import OversizedChunkError

        err = OversizedChunkError(chunk_index=3, token_count=600)
        self.assertEqual(err.chunk_index, 3)
        self.assertEqual(err.token_count, 600)

    def test_is_exception(self):
        from src.pipeline.chunker import OversizedChunkError

        self.assertTrue(issubclass(OversizedChunkError, Exception))

    def test_str_contains_useful_info(self):
        from src.pipeline.chunker import OversizedChunkError

        err = OversizedChunkError(chunk_index=7, token_count=999)
        msg = str(err)
        self.assertIn("7", msg)
        self.assertIn("999", msg)


class TestChunkTextEdgeCases(unittest.TestCase):
    """chunk_text edge cases that don't require actual tokenization."""

    def setUp(self):
        # Patch the lazy tokenizer singleton for every test in this class
        self._tok = _make_fake_tokenizer()
        self._patcher = patch(
            "src.pipeline.chunker._get_tokenizer", return_value=self._tok
        )
        self._patcher.start()
        # Clear the lru_cache so our patch takes effect
        import src.pipeline.chunker as _mod
        _mod._get_tokenizer.cache_clear()

    def tearDown(self):
        self._patcher.stop()

    def test_none_returns_single_empty_chunk(self):
        from src.pipeline.chunker import chunk_text

        result = chunk_text(None)
        self.assertEqual(result, [(0, "")])

    def test_empty_string_returns_single_empty_chunk(self):
        from src.pipeline.chunker import chunk_text

        result = chunk_text("")
        self.assertEqual(result, [(0, "")])

    def test_short_text_returns_original_string_unchanged(self):
        """Text shorter than max_tokens must be returned verbatim (not re-decoded)."""
        from src.pipeline.chunker import chunk_text

        text = "hello"  # 5 chars → 5 tokens, well under default 512
        result = chunk_text(text, max_tokens=512)
        self.assertEqual(len(result), 1)
        # chunk_index must be 0
        self.assertEqual(result[0][0], 0)
        # text must be the *original* string, not a re-decoded version
        self.assertIs(result[0][1], text)

    def test_text_exactly_at_max_tokens_returns_single_chunk(self):
        from src.pipeline.chunker import chunk_text

        text = "a" * 10   # exactly 10 tokens
        result = chunk_text(text, max_tokens=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 0)
        self.assertIs(result[0][1], text)


class TestChunkTextSlidingWindow(unittest.TestCase):
    """Sliding window correctness with fake per-character tokenizer."""

    def setUp(self):
        self._tok = _make_fake_tokenizer()
        self._patcher = patch(
            "src.pipeline.chunker._get_tokenizer", return_value=self._tok
        )
        self._patcher.start()
        import src.pipeline.chunker as _mod
        _mod._get_tokenizer.cache_clear()

    def tearDown(self):
        self._patcher.stop()

    def test_chunk_indices_are_sequential_and_zero_based(self):
        from src.pipeline.chunker import chunk_text

        # 25 chars, max_tokens=10, overlap=2 → step=8
        # windows: [0,10), [8,18), [16,25) → 3 chunks
        text = "a" * 25
        result = chunk_text(text, max_tokens=10, overlap=2)
        indices = [idx for idx, _ in result]
        self.assertEqual(indices, list(range(len(result))))
        self.assertEqual(indices[0], 0)

    def test_chunk_count_respects_max_chunks_cap(self):
        from src.pipeline.chunker import chunk_text

        # 1000 chars, max_tokens=10, overlap=0 → 100 natural windows → cap at 5
        text = "x" * 1000
        result = chunk_text(text, max_tokens=10, overlap=0, max_chunks=5)
        self.assertEqual(len(result), 5)

    def test_each_chunk_length_does_not_exceed_max_tokens(self):
        from src.pipeline.chunker import chunk_text

        text = "z" * 100
        max_tokens = 20
        result = chunk_text(text, max_tokens=max_tokens, overlap=5)
        for idx, chunk_str in result:
            token_count = len(self._tok.encode(chunk_str))
            self.assertLessEqual(
                token_count,
                max_tokens,
                msg=f"Chunk {idx} has {token_count} tokens, expected ≤ {max_tokens}",
            )

    def test_overlap_creates_shared_tokens_between_consecutive_chunks(self):
        """Last `overlap` tokens of chunk N should equal first `overlap` tokens of chunk N+1."""
        from src.pipeline.chunker import chunk_text

        text = "abcdefghijklmnopqrstuvwxyz"  # 26 unique chars
        max_tokens = 10
        overlap = 3
        result = chunk_text(text, max_tokens=max_tokens, overlap=overlap)
        self.assertGreater(len(result), 1, "Need at least 2 chunks to test overlap")
        for i in range(len(result) - 1):
            chunk_a = result[i][1]
            chunk_b = result[i + 1][1]
            # Last `overlap` chars of chunk_a should match first `overlap` chars of chunk_b
            self.assertEqual(
                chunk_a[-overlap:],
                chunk_b[:overlap],
                msg=f"Overlap mismatch between chunk {i} and {i+1}",
            )

    def test_single_character_text_longer_than_max_tokens_is_handled(self):
        """Degenerate: text = 'a'*11 with max_tokens=10 should produce 2 chunks."""
        from src.pipeline.chunker import chunk_text

        text = "a" * 11
        result = chunk_text(text, max_tokens=10, overlap=0)
        self.assertEqual(len(result), 2)


class TestChunkTextOversizedGuard(unittest.TestCase):
    """OversizedChunkError is raised when the safety guard fires."""

    def setUp(self):
        import src.pipeline.chunker as _mod
        _mod._get_tokenizer.cache_clear()

    def tearDown(self):
        import src.pipeline.chunker as _mod
        _mod._get_tokenizer.cache_clear()

    def test_raises_oversized_chunk_error_when_guard_triggers(self):
        """If a decoded chunk re-tokenizes to more than max_tokens, raise OversizedChunkError."""
        from src.pipeline.chunker import OversizedChunkError, chunk_text

        # Create a tokenizer where encode always reports 1 token per char on
        # the *initial* call (so we pass the total-tokens gate), but the
        # second call (inside the guard) reports max_tokens+1 tokens.
        call_count = {"n": 0}
        tok = MagicMock()

        def _encode(text: str, add_special_tokens: bool = False) -> list[int]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: tokenize the original text → 11 tokens (> max 10)
                return list(range(len(text)))
            # Subsequent calls (guard check): report inflated count
            return list(range(600))  # 600 > max_tokens=10

        tok.encode.side_effect = _encode
        tok.decode.return_value = "x" * 20  # decoded chunk text

        with patch("src.pipeline.chunker._get_tokenizer", return_value=tok):
            with self.assertRaises(OversizedChunkError) as ctx:
                chunk_text("a" * 11, max_tokens=10, overlap=0)

        self.assertEqual(ctx.exception.token_count, 600)


class TestImportErrorHandling(unittest.TestCase):
    """ImportError is raised with a helpful message when transformers is absent."""

    def test_import_error_when_transformers_missing(self):
        # Temporarily hide transformers from the import machinery
        import src.pipeline.chunker as _mod

        _mod._get_tokenizer.cache_clear()

        original = sys.modules.get("transformers")
        sys.modules["transformers"] = None  # type: ignore[assignment]

        try:
            with self.assertRaises(ImportError) as ctx:
                _mod._get_tokenizer()
            self.assertIn("transformers", str(ctx.exception).lower())
        finally:
            if original is None:
                del sys.modules["transformers"]
            else:
                sys.modules["transformers"] = original
            _mod._get_tokenizer.cache_clear()


if __name__ == "__main__":
    unittest.main()
