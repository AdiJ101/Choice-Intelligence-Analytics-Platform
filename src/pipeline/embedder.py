"""
embedder.py — Embedding client for the Customer Intelligence & Analytics Platform.

Wraps the ``BAAI/bge-m3`` SentenceTransformer model and projects its native output
dimension to the target 1536-dimensional space required by the Qdrant
``content_embeddings`` collection.

If the model's native output dimension is already 1536, no projection is applied.
Otherwise a trainable (or randomly initialised) ``torch.nn.Linear`` layer maps
native_dim → target_dim without bias, and the result is L2-normalised before
being returned.

Text is passed to the model as-is — no transliteration or encoding conversion is
performed.

Requirements: 7.6, 9.4, 10.4
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sentence_transformers import SentenceTransformer


class EmbedderClient:
    """Encapsulates a SentenceTransformer model with optional linear projection.

    Parameters
    ----------
    model_name:
        Hugging Face model identifier or local path passed to
        :class:`sentence_transformers.SentenceTransformer`.  Defaults to
        ``"BAAI/bge-m3"``.
    target_dim:
        The required output vector dimension.  Defaults to ``1536`` to match
        the Qdrant collection schema.

    Attributes
    ----------
    native_dim : int
        The raw output dimension of the underlying SentenceTransformer model
        before any projection is applied.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", target_dim: int = 1536) -> None:
        self._model: SentenceTransformer = SentenceTransformer(model_name)
        self._target_dim: int = target_dim

        # Determine the native output dimension by inspecting the last pooling
        # layer, or by running a single dummy encode.
        native: int = self._model.get_sentence_embedding_dimension()  # type: ignore[assignment]
        if native is None:
            # Fallback: run a dummy forward pass to discover the dimension.
            dummy = self._model.encode("probe", normalize_embeddings=False)
            native = int(np.asarray(dummy).shape[-1])
        self._native_dim: int = int(native)

        # Set up linear projection if the model's native dim differs from target.
        if self._native_dim != self._target_dim:
            self._projection: nn.Linear | None = nn.Linear(
                self._native_dim, self._target_dim, bias=False
            )
        else:
            self._projection = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def native_dim(self) -> int:
        """The model's actual output dimension before any projection."""
        return self._native_dim

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Encode *text* and return a 1536-dimensional L2-normalised vector.

        The method:

        1. Encodes *text* with the SentenceTransformer using
           ``normalize_embeddings=True`` (unit-norm in the model's native space).
        2. If a projection layer exists, applies it via ``torch.no_grad()`` to
           map the vector from ``native_dim`` → ``target_dim``.
        3. L2-normalises the (possibly projected) vector so the final output is
           always a unit vector in ``target_dim``-dimensional space.
        4. Returns the result as a plain Python ``list[float]``.

        Parameters
        ----------
        text:
            The input string to embed.  Passed to the model without any
            modification (no transliteration, no encoding conversion).

        Returns
        -------
        list[float]
            A Python list of ``target_dim`` (default 1536) floats representing
            the L2-normalised embedding.
        """
        # Step 1: encode with the model; already unit-normalised in native space.
        raw: np.ndarray = np.asarray(
            self._model.encode(text, normalize_embeddings=True), dtype=np.float32
        )

        # Step 2: apply linear projection if needed.
        if self._projection is not None:
            tensor = torch.from_numpy(raw)  # shape: (native_dim,)
            with torch.no_grad():
                projected: np.ndarray = self._projection(tensor).numpy()
        else:
            projected = raw

        # Step 3: L2-normalise the (possibly projected) vector.
        norm = float(np.linalg.norm(projected))
        if norm > 0.0:
            projected = projected / norm

        # Step 4: return as a Python list.
        return projected.tolist()
