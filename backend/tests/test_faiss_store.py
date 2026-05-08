"""
Unit tests for backend/utils/faiss_store.py

Covers:
- initialize: creates index file on disk; is idempotent
- exists: returns True/False correctly
- upsert: adds new vectors; updates existing vectors (no duplicates)
- search: returns correct IDs; handles empty index; handles top_k > index size
- Dimension validation for upsert and search
- Corrupted index recovery
- Thread safety (basic concurrent upsert)

Requirements: 5.1, 5.2, 5.3, 5.4, 13.3
"""

import json
import os
import threading
import tempfile
from pathlib import Path

import numpy as np
import pytest

from utils.faiss_store import FAISSStore, EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_embedding(seed: int | None = None) -> list[float]:
    """Return a random unit-normalised 1536-dim embedding."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _zero_embedding() -> list[float]:
    return [0.0] * EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_store(tmp_path):
    """Return a FAISSStore backed by a temporary directory."""
    return FAISSStore(index_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------

class TestExists:
    def test_returns_false_before_initialize(self, tmp_store):
        assert tmp_store.exists("user-1") is False

    def test_returns_true_after_initialize(self, tmp_store):
        tmp_store.initialize("user-1")
        assert tmp_store.exists("user-1") is True

    def test_different_users_are_independent(self, tmp_store):
        tmp_store.initialize("user-a")
        assert tmp_store.exists("user-a") is True
        assert tmp_store.exists("user-b") is False


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_creates_index_file(self, tmp_store, tmp_path):
        tmp_store.initialize("user-1")
        assert (tmp_path / "user-1.index").exists()

    def test_creates_ids_file(self, tmp_store, tmp_path):
        tmp_store.initialize("user-1")
        assert (tmp_path / "user-1.ids").exists()

    def test_ids_file_is_empty_list(self, tmp_store, tmp_path):
        tmp_store.initialize("user-1")
        with open(tmp_path / "user-1.ids") as fh:
            assert json.load(fh) == []

    def test_idempotent_does_not_overwrite_existing_data(self, tmp_store):
        """Calling initialize twice must not wipe an existing index."""
        tmp_store.initialize("user-1")
        emb = _random_embedding(seed=0)
        tmp_store.upsert("user-1", "vec-1", emb)

        # Second initialize should be a no-op
        tmp_store.initialize("user-1")
        ids = tmp_store.search("user-1", emb, top_k=1)
        assert ids == ["vec-1"]

    def test_creates_index_dir_if_missing(self, tmp_path):
        nested = str(tmp_path / "deep" / "nested" / "dir")
        store = FAISSStore(index_dir=nested)
        store.initialize("user-1")
        assert store.exists("user-1")


# ---------------------------------------------------------------------------
# upsert()
# ---------------------------------------------------------------------------

class TestUpsert:
    def test_upsert_new_vector_increases_count(self, tmp_store):
        tmp_store.initialize("user-1")
        tmp_store.upsert("user-1", "vec-1", _random_embedding(seed=1))
        ids = tmp_store.search("user-1", _random_embedding(seed=1), top_k=10)
        assert "vec-1" in ids

    def test_upsert_multiple_vectors(self, tmp_store):
        tmp_store.initialize("user-1")
        for i in range(5):
            tmp_store.upsert("user-1", f"vec-{i}", _random_embedding(seed=i))
        ids = tmp_store.search("user-1", _random_embedding(seed=0), top_k=10)
        assert len(ids) == 5

    def test_upsert_existing_id_does_not_duplicate(self, tmp_store):
        """Re-upserting the same vector_id must not create a duplicate entry."""
        tmp_store.initialize("user-1")
        emb = _random_embedding(seed=42)
        tmp_store.upsert("user-1", "vec-dup", emb)
        tmp_store.upsert("user-1", "vec-dup", emb)  # same ID, same embedding

        ids = tmp_store.search("user-1", emb, top_k=10)
        assert ids.count("vec-dup") == 1

    def test_upsert_replaces_old_embedding(self, tmp_store):
        """After upsert with a new embedding, the new embedding is returned."""
        tmp_store.initialize("user-1")
        old_emb = _random_embedding(seed=10)
        new_emb = _random_embedding(seed=20)

        tmp_store.upsert("user-1", "vec-replace", old_emb)
        tmp_store.upsert("user-1", "vec-replace", new_emb)

        # Searching with new_emb should return vec-replace as the top hit
        ids = tmp_store.search("user-1", new_emb, top_k=1)
        assert ids == ["vec-replace"]

    def test_upsert_auto_initializes_if_index_missing(self, tmp_store):
        """upsert must work even if initialize was never called."""
        tmp_store.upsert("user-new", "vec-1", _random_embedding(seed=5))
        assert tmp_store.exists("user-new")

    def test_upsert_wrong_dimension_raises(self, tmp_store):
        tmp_store.initialize("user-1")
        with pytest.raises(ValueError, match="1536"):
            tmp_store.upsert("user-1", "bad-vec", [0.0] * 128)

    def test_upsert_persists_to_disk(self, tmp_store, tmp_path):
        """After upsert, a new FAISSStore instance can read the data."""
        tmp_store.upsert("user-1", "vec-persist", _random_embedding(seed=7))

        # Create a fresh store pointing at the same directory
        store2 = FAISSStore(index_dir=str(tmp_path))
        ids = store2.search("user-1", _random_embedding(seed=7), top_k=1)
        assert "vec-persist" in ids


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_empty_index_returns_empty_list(self, tmp_store):
        tmp_store.initialize("user-1")
        result = tmp_store.search("user-1", _random_embedding(seed=0), top_k=5)
        assert result == []

    def test_search_missing_index_initializes_and_returns_empty(self, tmp_store):
        """search on a non-existent user must initialise the index and return []."""
        result = tmp_store.search("ghost-user", _random_embedding(seed=0), top_k=5)
        assert result == []
        assert tmp_store.exists("ghost-user")

    def test_search_returns_correct_top_k(self, tmp_store):
        tmp_store.initialize("user-1")
        embeddings = [_random_embedding(seed=i) for i in range(10)]
        for i, emb in enumerate(embeddings):
            tmp_store.upsert("user-1", f"vec-{i}", emb)

        results = tmp_store.search("user-1", embeddings[0], top_k=3)
        assert len(results) == 3

    def test_search_top_k_larger_than_index_returns_all(self, tmp_store):
        """When top_k > index size, all available IDs are returned."""
        tmp_store.initialize("user-1")
        for i in range(3):
            tmp_store.upsert("user-1", f"vec-{i}", _random_embedding(seed=i))

        results = tmp_store.search("user-1", _random_embedding(seed=0), top_k=100)
        assert len(results) == 3

    def test_search_nearest_neighbour_is_correct(self, tmp_store):
        """The most similar vector should be returned first."""
        tmp_store.initialize("user-1")
        target_emb = _random_embedding(seed=99)

        # Add the target embedding and several unrelated ones
        tmp_store.upsert("user-1", "target", target_emb)
        for i in range(5):
            tmp_store.upsert("user-1", f"noise-{i}", _random_embedding(seed=i))

        results = tmp_store.search("user-1", target_emb, top_k=1)
        assert results == ["target"]

    def test_search_wrong_dimension_raises(self, tmp_store):
        tmp_store.initialize("user-1")
        with pytest.raises(ValueError, match="1536"):
            tmp_store.search("user-1", [0.0] * 512, top_k=5)

    def test_search_top_k_one(self, tmp_store):
        tmp_store.initialize("user-1")
        emb = _random_embedding(seed=3)
        tmp_store.upsert("user-1", "only-vec", emb)
        results = tmp_store.search("user-1", emb, top_k=1)
        assert results == ["only-vec"]


# ---------------------------------------------------------------------------
# Multi-user isolation
# ---------------------------------------------------------------------------

class TestMultiUserIsolation:
    def test_users_have_separate_indexes(self, tmp_store):
        emb_a = _random_embedding(seed=1)
        emb_b = _random_embedding(seed=2)

        tmp_store.upsert("user-a", "vec-a", emb_a)
        tmp_store.upsert("user-b", "vec-b", emb_b)

        results_a = tmp_store.search("user-a", emb_a, top_k=10)
        results_b = tmp_store.search("user-b", emb_b, top_k=10)

        assert "vec-a" in results_a
        assert "vec-b" not in results_a
        assert "vec-b" in results_b
        assert "vec-a" not in results_b


# ---------------------------------------------------------------------------
# Corrupted index recovery
# ---------------------------------------------------------------------------

class TestCorruptedIndex:
    def test_corrupted_index_file_is_reinitialised(self, tmp_store, tmp_path):
        """A corrupted .index file must be silently reinitialised."""
        tmp_store.initialize("user-corrupt")
        # Overwrite the index file with garbage
        (tmp_path / "user-corrupt.index").write_bytes(b"not a valid faiss index")

        # search should trigger load → detect corruption → reinitialise → return []
        result = tmp_store.search("user-corrupt", _random_embedding(seed=0), top_k=5)
        assert result == []


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_upserts_do_not_corrupt_index(self, tmp_store):
        """Multiple threads upserting to the same user must not corrupt the index."""
        tmp_store.initialize("user-concurrent")
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                tmp_store.upsert(
                    "user-concurrent", f"vec-{i}", _random_embedding(seed=i)
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

        # All 20 vectors should be present
        results = tmp_store.search(
            "user-concurrent", _random_embedding(seed=0), top_k=20
        )
        assert len(results) == 20
