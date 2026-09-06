import base64
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from serviceops.config import Settings
from serviceops.knowledge.embedding_pipeline import embed_knowledge_release
from serviceops.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProviderError,
    FixtureEmbeddingProvider,
    build_embedding_provider,
)
from serviceops.knowledge.fusion import search_hybrid_knowledge
from serviceops.knowledge.ingestion import ingest_document
from serviceops.knowledge.releases import (
    KnowledgeReleaseError,
    approve_knowledge_release,
    create_knowledge_release,
    evaluate_knowledge_release,
    publish_knowledge_release,
)
from serviceops.knowledge.vector import search_vector_candidates
from serviceops.models import KnowledgeChunk, KnowledgeChunkEmbedding, KnowledgeEmbeddingBatch
from serviceops.seed import OPS_SESSION_TOKEN
from serviceops.shared.errors import ValidationError

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}


def _hybrid_release(db, *, version: str, documents: list[str]):
    release = create_knowledge_release(
        db,
        release_version=version,
        document_ids=documents,
        created_by="stage3-test",
        retrieval_strategy_version="hybrid_rrf_v1",
    )
    release = evaluate_knowledge_release(db, release.id)
    assert release.status == "EVALUATED"
    return approve_knowledge_release(db, release.id, approved_by="stage3-reviewer")


class FlakyFixtureProvider(FixtureEmbeddingProvider):
    def __init__(self, failures: int = 1):
        self.failures = failures
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.calls <= self.failures:
            raise EmbeddingProviderError("EMBEDDING_PROVIDER_REQUEST_FAILED", "fixture transient failure")
        return super().embed(texts)


class WrongDimensionProvider(FixtureEmbeddingProvider):
    dimensions = 3


class AlwaysFailProvider(FixtureEmbeddingProvider):
    def embed(self, texts):
        raise EmbeddingProviderError("EMBEDDING_PROVIDER_REQUEST_FAILED", "fixture provider unavailable")


def test_provider_configuration_fails_closed_and_fixture_is_not_production():
    with pytest.raises(EmbeddingProviderError) as not_configured:
        build_embedding_provider(settings=Settings(embedding_provider="not_configured"))
    assert not_configured.value.code == "EMBEDDING_PROVIDER_NOT_CONFIGURED"

    with pytest.raises(EmbeddingProviderError) as production_fixture:
        build_embedding_provider(
            settings=Settings(
                app_env="production",
                embedding_provider="fixture",
                demo_mode_enabled=False,
                api_docs_enabled=False,
                database_url="postgresql+psycopg://serviceops:secret@db/serviceops",
                web_origin="https://serviceops.example",
            )
        )
    assert production_fixture.value.code == "EMBEDDING_FIXTURE_FORBIDDEN"

    fixture = build_embedding_provider(settings=Settings(embedding_provider="fixture"))
    result = fixture.embed(["退货规则"])
    assert result.provider == "fixture"
    assert len(result.vectors[0]) == EMBEDDING_DIMENSIONS
    assert result.cost_micros == 0


def test_embedding_request_budget_fails_closed_when_invalid(db, monkeypatch):
    document = ingest_document(
        db,
        filename="rate-limit.md",
        source_uri="fixture://stage3/rate-limit.md",
        data=b"# Rate limit\n\nA policy.",
    ).document
    release = _hybrid_release(db, version="stage3-rate-limit", documents=[document.id])
    monkeypatch.setattr(
        "serviceops.knowledge.embedding_pipeline.get_settings",
        lambda: Settings(embedding_requests_per_minute=0),
    )

    with pytest.raises(ValidationError) as error:
        embed_knowledge_release(db, release.id, provider=FixtureEmbeddingProvider())
    assert error.value.code == "EMBEDDING_RATE_LIMIT_INVALID"


def test_embedding_batch_is_retryable_cached_and_required_before_hybrid_publish(db):
    document = ingest_document(
        db,
        filename="hybrid.md",
        source_uri="fixture://stage3/hybrid.md",
        data=b"# Return\n\n7 days return policy.",
    ).document
    release = _hybrid_release(db, version="stage3-cache", documents=[document.id])

    with pytest.raises(KnowledgeReleaseError) as not_ready:
        publish_knowledge_release(db, release.id)
    assert not_ready.value.code == "KNOWLEDGE_RELEASE_EMBEDDING_NOT_READY"

    provider = FlakyFixtureProvider()
    batch = embed_knowledge_release(db, release.id, provider=provider, batch_size=1)
    assert batch.status == "READY"
    assert batch.attempts == 2
    assert batch.embedded_count == 1
    assert batch.cost_micros == 0
    row_count = len(list(db.scalars(select(KnowledgeChunkEmbedding))))

    repeated = embed_knowledge_release(db, release.id, provider=provider, batch_size=1)
    assert repeated.id == batch.id
    assert provider.calls == 2
    assert len(list(db.scalars(select(KnowledgeChunkEmbedding)))) == row_count

    published = publish_knowledge_release(db, release.id)
    assert published.status == "PUBLISHED"
    assert published.embedding_status == "READY"


def test_embedding_dimension_and_content_hash_mismatch_fail_closed(db):
    document = ingest_document(
        db,
        filename="mismatch.md",
        source_uri="fixture://stage3/mismatch.md",
        data=b"# Scope\n\nA policy.",
    ).document
    release = _hybrid_release(db, version="stage3-mismatch", documents=[document.id])
    with pytest.raises(EmbeddingProviderError) as dimension:
        embed_knowledge_release(db, release.id, provider=WrongDimensionProvider())
    assert dimension.value.code == "EMBEDDING_DIMENSION_UNSUPPORTED"

    release_item = release.source_manifest[0]
    assert release_item["content_hash"] == document.content_hash
    chunk = db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    assert chunk is not None

    chunk.content_hash = "0" * 64
    db.commit()
    with pytest.raises(Exception) as mismatch:
        embed_knowledge_release(db, release.id, provider=FixtureEmbeddingProvider())
    assert getattr(mismatch.value, "code", None) == "EMBEDDING_CONTENT_HASH_MISMATCH"


def test_provider_failure_persists_failed_batch_and_blocks_publish(db):
    document = ingest_document(
        db,
        filename="failure.md",
        source_uri="fixture://stage3/failure.md",
        data=b"# Failure\n\nA policy.",
    ).document
    release = _hybrid_release(db, version="stage3-failure", documents=[document.id])
    with pytest.raises(EmbeddingProviderError) as failure:
        embed_knowledge_release(db, release.id, provider=AlwaysFailProvider())
    assert failure.value.code == "EMBEDDING_PROVIDER_REQUEST_FAILED"
    batch = db.scalar(
        select(KnowledgeEmbeddingBatch).where(KnowledgeEmbeddingBatch.release_id == release.id)
    )
    assert batch is not None
    assert batch.status == "FAILED"
    assert db.get(release.__class__, release.id).embedding_status == "FAILED"
    with pytest.raises(KnowledgeReleaseError) as blocked:
        publish_knowledge_release(db, release.id)
    assert blocked.value.code == "KNOWLEDGE_RELEASE_EMBEDDING_NOT_READY"


def test_vector_and_hybrid_search_apply_tenant_channel_product_and_validity_filters(db):
    local = ingest_document(
        db,
        filename="local.md",
        source_uri="fixture://stage3/local.md",
        data="# Return\n\n退货规则 7 days.".encode(),
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
    ).document
    other = ingest_document(
        db,
        filename="other.md",
        source_uri="fixture://stage3/other.md",
        data="# Other\n\n退货规则 other tenant.".encode(),
        tenant_scope="other-tenant",
        channel_scope="xianyu",
        product_scope="phone",
    ).document
    expired = ingest_document(
        db,
        filename="expired.md",
        source_uri="fixture://stage3/expired.md",
        data="# Expired\n\n退货规则 expired.".encode(),
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    ).document
    release = _hybrid_release(
        db,
        version="stage3-scope",
        documents=[local.id, other.id, expired.id],
    )
    provider = FixtureEmbeddingProvider()
    embed_knowledge_release(db, release.id, provider=provider)
    publish_knowledge_release(db, release.id)

    local_results = search_vector_candidates(
        db,
        "Return\n退货规则 7 days.",
        provider=provider,
        strategy="hybrid_rrf_v1",
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
    )
    assert local_results
    assert {item["document_id"] for item in local_results} == {local.id}

    wrong_channel = search_vector_candidates(
        db,
        "Return\n退货规则 7 days.",
        provider=provider,
        strategy="hybrid_rrf_v1",
        tenant_scope="local-demo",
        channel_scope="taobao",
        product_scope="phone",
    )
    assert wrong_channel == []

    hybrid = search_hybrid_knowledge(
        db,
        "Return\n退货规则 7 days.",
        provider=provider,
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
    )
    assert hybrid["strategy"] == "hybrid_rrf_v1"
    assert hybrid["fallback"] is False
    assert hybrid["results"][0]["hybrid_score"] is not None


def test_hybrid_provider_outage_falls_back_to_legacy_lexical_without_cross_scope_leak(db):
    report = search_hybrid_knowledge(
        db,
        "退货需要几天",
        provider=None,
        provider_error=EmbeddingProviderError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "not configured",
        ),
        tenant_scope="local-demo",
    )
    assert report["strategy"] == "lexical_v1"
    assert report["fallback"] is True
    assert report["fallback_reason"] == "EMBEDDING_PROVIDER_NOT_CONFIGURED"
    assert report["results"]

    isolated = search_hybrid_knowledge(
        db,
        "退货需要几天",
        provider=None,
        provider_error=EmbeddingProviderError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "not configured",
        ),
        tenant_scope="other-tenant",
    )
    assert isolated["results"] == []


def test_stage3_api_exposes_embedding_and_search_contract(client, db, monkeypatch):
    document_response = client.post(
        "/api/ops/knowledge/documents",
        headers=OPS_HEADERS,
        json={
            "filename": "api-hybrid.md",
            "source_uri": "fixture://stage3/api-hybrid.md",
            "content_base64": base64.b64encode(b"# Return\n\n6 days return policy.").decode(),
            "tenant_scope": "local-demo",
            "channel_scope": "xianyu",
            "product_scope": "phone",
        },
    )
    assert document_response.status_code == 200
    document_id = document_response.json()["id"]
    release_response = client.post(
        "/api/ops/knowledge/releases",
        headers=OPS_HEADERS,
        json={
            "release_version": "api-stage3-v1",
            "document_ids": [document_id],
            "retrieval_strategy_version": "hybrid_rrf_v1",
        },
    )
    assert release_response.status_code == 200
    release_id = release_response.json()["id"]
    assert client.post(
        f"/api/ops/knowledge/releases/{release_id}/evaluate", headers=OPS_HEADERS
    ).json()["status"] == "EVALUATED"
    assert client.post(
        f"/api/ops/knowledge/releases/{release_id}/approve", headers=OPS_HEADERS
    ).json()["status"] == "APPROVED"
    monkeypatch.setattr(
        "serviceops.main.build_embedding_provider",
        lambda _name=None: FixtureEmbeddingProvider(),
    )
    embedding_response = client.post(
        f"/api/ops/knowledge/releases/{release_id}/embeddings",
        headers=OPS_HEADERS,
        json={"provider": "fixture"},
    )
    assert embedding_response.status_code == 200
    assert embedding_response.json()["status"] == "READY"
    assert client.post(
        f"/api/ops/knowledge/releases/{release_id}/publish", headers=OPS_HEADERS
    ).json()["status"] == "PUBLISHED"
    search_response = client.post(
        "/api/ops/knowledge/search",
        headers=OPS_HEADERS,
        json={
            "query": "return policy",
            "tenant_scope": "local-demo",
            "channel_scope": "xianyu",
            "product_scope": "phone",
            "provider": "fixture",
        },
    )
    assert search_response.status_code == 200
    assert search_response.json()["strategy"] in {"hybrid_rrf_v1", "lexical_v1"}
