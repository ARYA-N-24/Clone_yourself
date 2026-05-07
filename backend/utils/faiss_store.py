"""
Per-user FAISS vector store for email embedding storage and retrieval.

Each user gets their own flat L2 index stored on disk:
  - ``{index_dir}/{user_id}.index``  — the FAISS binary index file
  - ``{index_dir}/{user_id}.ids``    — a JSON file mapping position → vector_id string

Embedding dimension is fixed at 1536 (OpenAI text-embedding-3-small).

Thread safety: a per-user ``threading.Lock`` is acquired for every mutating
operation (initialize, upsert) so concurrent requests for the same user do not
corrupt the index.  Read-only operations (search, exists) are also lock-guarded
to avoid reading a partially-written index.

Usage::

    store = FAISSStore()                          # default dir: ./faiss_indexes/
    store.initialize("user-123")
    store.upsert("user-123", "email-abc", embedding_list)
    ids = store.search("user-123", query_embedding, top_k=5)
    print(store.exists("user-123"))               # True
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# Embedding dimension for OpenAI text-embedding-3-small
EMBEDDING_DIM = 1536


class FAISSStore:
    """
    Manages per-user FAISS flat L2 indexes stored on disk.

    Args:
        index_dir: Directory where index files are stored.
                   Defaults to ``./faiss_indexes/``.
    """

    def __init__(self, index_dir: str = "./faiss_indexes/") -> None:
        self._index_dir = Path(index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        # Per-user locks to prevent concurrent index corruption
        self._locks: dict[str, threading.Lock] = {}
        self._locks_meta = threading.Lock()  # guards _locks dict itself

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lock(self, user_id: str) -> threading.Lock:
        """Return (creating if necessary) the per-user lock."""
        with self._locks_meta:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def _index_path(self, user_id: str) -> Path:
        return self._index_dir / f"{user_id}.index"

    def _ids_path(self, user_id: str) -> Path:
        return self._index_dir / f"{user_id}.ids"

    def _load_index(self, user_id: str) -> Optional[faiss.IndexFlatL2]:
        """
        Load the FAISS index from disk.

        Returns ``None`` if the file does not exist.
        Reinitialises (and overwrites) the file if it is corrupted.
        """
        path = self._index_path(user_id)
        if not path.exists():
            return None
        try:
            index = faiss.read_index(str(path))
            return index
        except Exception:
            logger.warning(
                "FAISS index for user %s is corrupted; reinitialising.", user_id
            )
            self._create_empty_index(user_id)
            return faiss.read_index(str(path))

    def _load_ids(self, user_id: str) -> list[str]:
        """Load the vector-ID list from disk, returning [] if absent."""
        path = self._ids_path(user_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logger.warning(
                "IDs file for user %s is corrupted; returning empty list.", user_id
            )
            return []

    def _save_index(self, user_id: str, index: faiss.IndexFlatL2) -> None:
        """Persist the FAISS index to disk."""
        faiss.write_index(index, str(self._index_path(user_id)))

    def _save_ids(self, user_id: str, ids: list[str]) -> None:
        """Persist the vector-ID list to disk."""
        with open(self._ids_path(user_id), "w", encoding="utf-8") as fh:
            json.dump(ids, fh)

    def _create_empty_index(self, user_id: str) -> None:
        """Create and save an empty IndexFlatL2 for the user."""
        index = faiss.IndexFlatL2(EMBEDDING_DIM)
        self._save_index(user_id, index)
        self._save_ids(user_id, [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self, user_id: str) -> None:
        """
        Create an empty FAISS index for *user_id* if one does not already exist.

        If the index already exists on disk this is a no-op.

        Args:
            user_id: Unique identifier for the user.
        """
        lock = self._get_lock(user_id)
        with lock:
            if not self._index_path(user_id).exists():
                self._create_empty_index(user_id)
                logger.debug("Initialised empty FAISS index for user %s.", user_id)

    def upsert(self, user_id: str, vector_id: str, embedding: list[float]) -> None:
        """
        Add or replace a vector in the user's FAISS index.

        Because ``IndexFlatL2`` does not support in-place deletion, an upsert
        of an existing *vector_id* rebuilds the index from scratch without the
        old vector, then adds the new one.  The updated index is saved to disk.

        Args:
            user_id:   Unique identifier for the user.
            vector_id: Application-level ID for this vector (e.g. email UUID).
            embedding: A list of 1536 floats representing the embedding.

        Raises:
            ValueError: If ``len(embedding) != 1536``.
        """
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding must have exactly {EMBEDDING_DIM} dimensions, "
                f"got {len(embedding)}."
            )

        vec = np.array(embedding, dtype=np.float32).reshape(1, EMBEDDING_DIM)

        lock = self._get_lock(user_id)
        with lock:
            # Ensure index exists
            if not self._index_path(user_id).exists():
                self._create_empty_index(user_id)

            index = self._load_index(user_id)
            ids = self._load_ids(user_id)

            if vector_id in ids:
                # Rebuild index without the old vector
                old_pos = ids.index(vector_id)
                n = index.ntotal

                if n > 1:
                    # Reconstruct all existing vectors
                    all_vectors = np.zeros((n, EMBEDDING_DIM), dtype=np.float32)
                    for i in range(n):
                        all_vectors[i] = index.reconstruct(i)

                    # Remove the old vector and its ID
                    keep_mask = [i for i in range(n) if i != old_pos]
                    kept_vectors = all_vectors[keep_mask]
                    kept_ids = [ids[i] for i in keep_mask]

                    # Build a fresh index with the remaining vectors
                    new_index = faiss.IndexFlatL2(EMBEDDING_DIM)
                    new_index.add(kept_vectors)
                    index = new_index
                    ids = kept_ids
                else:
                    # Only one vector and it's the one being replaced
                    index = faiss.IndexFlatL2(EMBEDDING_DIM)
                    ids = []

            # Append the new vector
            index.add(vec)
            ids.append(vector_id)

            self._save_index(user_id, index)
            self._save_ids(user_id, ids)
            logger.debug(
                "Upserted vector %s for user %s (index size: %d).",
                vector_id,
                user_id,
                index.ntotal,
            )

    def search(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[str]:
        """
        Return the *top_k* most similar vector IDs for *query_embedding*.

        If the user's index does not exist it is initialised (empty) and an
        empty list is returned.  If the index contains fewer than *top_k*
        vectors, all available IDs are returned.

        Args:
            user_id:         Unique identifier for the user.
            query_embedding: A list of 1536 floats representing the query.
            top_k:           Maximum number of results to return (default 5).

        Returns:
            A list of vector ID strings ordered by ascending L2 distance
            (most similar first).

        Raises:
            ValueError: If ``len(query_embedding) != 1536``.
        """
        if len(query_embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Query embedding must have exactly {EMBEDDING_DIM} dimensions, "
                f"got {len(query_embedding)}."
            )

        lock = self._get_lock(user_id)
        with lock:
            if not self._index_path(user_id).exists():
                self._create_empty_index(user_id)
                logger.debug(
                    "Index for user %s did not exist; initialised empty index.",
                    user_id,
                )
                return []

            index = self._load_index(user_id)
            ids = self._load_ids(user_id)

            n = index.ntotal
            if n == 0:
                return []

            k = min(top_k, n)
            query_vec = np.array(query_embedding, dtype=np.float32).reshape(
                1, EMBEDDING_DIM
            )
            _distances, indices = index.search(query_vec, k)

            result: list[str] = []
            for idx in indices[0]:
                if idx == -1:
                    # FAISS returns -1 when fewer results than k are available
                    continue
                if 0 <= idx < len(ids):
                    result.append(ids[idx])

            return result

    def exists(self, user_id: str) -> bool:
        """
        Return ``True`` if the user's FAISS index file exists on disk.

        Args:
            user_id: Unique identifier for the user.
        """
        return self._index_path(user_id).exists()
