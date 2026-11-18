import pytest

from memory.database import Database
from memory.embeddings import CpuHashEmbeddingModel
from memory.knowledge_store import KnowledgeStore
from memory.semantic_cache import SemanticCache
from memory.state_store import EncryptedStateCodec, StateStoreError


def test_semantic_cache_persists_vectors_and_answers(tmp_path):
    path = str(tmp_path / "engine.db")
    cache = SemanticCache(
        database=Database(path),
        embedder=CpuHashEmbeddingModel(dimension=128),
        similarity_threshold=0.25,
    )
    cache.put("reset my account password", "Open account settings and choose reset password.")

    restored = SemanticCache(
        database=Database(path),
        embedder=CpuHashEmbeddingModel(dimension=128),
        similarity_threshold=0.25,
    )
    assert restored.lookup("how do I reset my password?") == (
        "Open account settings and choose reset password."
    )


def test_semantic_cache_keeps_namespaces_isolated(tmp_path):
    database = Database(str(tmp_path / "engine.db"))
    first = SemanticCache(database, namespace="tenant-a", embedder=CpuHashEmbeddingModel(64))
    second = SemanticCache(database, namespace="tenant-b", embedder=CpuHashEmbeddingModel(64))
    first.put("same question", "private answer")

    assert second.lookup("same question") is None


def test_knowledge_store_upserts_and_searches_documents(tmp_path):
    store = KnowledgeStore(
        Database(str(tmp_path / "knowledge.db")),
        embedder=CpuHashEmbeddingModel(128),
    )
    item_id = store.upsert(
        source="docs/architecture.md",
        title="SQLite persistence",
        content="Workflow checkpoints are saved in SQLite so interrupted runs can resume.",
        metadata={"kind": "architecture"},
    )
    results = store.search("saved SQLite workflow checkpoints", limit=3)

    assert results
    assert results[0].id == item_id
    assert results[0].metadata["kind"] == "architecture"
    assert store.get(item_id).source == "docs/architecture.md"


def test_state_codec_round_trips_and_rejects_tampering():
    codec = EncryptedStateCodec(key=b"k" * 32)
    encrypted = codec.encrypt(b"sqlite snapshot bytes")
    assert codec.decrypt(encrypted) == b"sqlite snapshot bytes"

    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(StateStoreError, match="authentication"):
        codec.decrypt(tampered)


def test_state_codec_requires_a_32_byte_key():
    with pytest.raises(StateStoreError, match="32-byte"):
        EncryptedStateCodec(key=b"short")
