import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from serviceops.agent.evaluation import evaluate_agent_orchestration
from serviceops.agent.release import governance_snapshot
from serviceops.database import SessionLocal
from serviceops.knowledge.embedding_pipeline import embed_knowledge_release
from serviceops.knowledge.embeddings import EmbeddingProviderError, build_embedding_provider
from serviceops.knowledge.evaluation import (
    EXPLORATORY_CASES,
    EXPLORATORY_DATASET_VERSION,
    evaluate_knowledge_search,
)
from serviceops.knowledge.fusion import search_hybrid_knowledge
from serviceops.knowledge.ingestion import ingest_document, list_document_chunks, list_documents
from serviceops.knowledge.releases import (
    approve_knowledge_release,
    create_knowledge_release,
    evaluate_knowledge_release,
    list_releases,
    publish_knowledge_release,
    rollback_knowledge_release,
)
from serviceops.knowledge.vector import search_vector_candidates
from serviceops.retention.service import purge_expired_data
from serviceops.seed import seed_database


def seed() -> None:
    with SessionLocal() as db:
        seed_database(db)


def evaluate_knowledge(*, include_exploratory: bool = False) -> int:
    with SessionLocal() as db:
        seed_database(db)
        report = evaluate_knowledge_search(db)
        if include_exploratory:
            report["exploratory"] = evaluate_knowledge_search(
                db,
                EXPLORATORY_CASES,
                dataset_version=EXPLORATORY_DATASET_VERSION,
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def evaluate_agent(
    *,
    runtime: str = "deterministic",
    max_cases: int | None = None,
    delay_seconds: float | None = None,
) -> int:
    report = evaluate_agent_orchestration(
        runtime=runtime,
        max_cases=max_cases,
        delay_seconds=delay_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def purge_retention(*, as_of: datetime | None = None) -> int:
    with SessionLocal() as db:
        report = purge_expired_data(db, as_of=as_of)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


def agent_governance() -> int:
    print(json.dumps(governance_snapshot(), ensure_ascii=False, indent=2))
    return 0


def _json_model(value) -> dict:
    return {
        key: (item.isoformat() if isinstance(item, datetime) else item)
        for key, item in vars(value).items()
        if not key.startswith("_")
    }


def knowledge_ingest(
    *,
    file_path: str,
    source_uri: str,
    idempotency_key: str | None,
    tenant_scope: str,
    channel_scope: str,
    product_scope: str,
) -> int:
    with SessionLocal() as db:
        result = ingest_document(
            db,
            filename=Path(file_path).name,
            source_uri=source_uri,
            data=Path(file_path).read_bytes(),
            idempotency_key=idempotency_key,
            tenant_scope=tenant_scope,
            channel_scope=channel_scope,
            product_scope=product_scope,
        )
    print(
        json.dumps(
            {
                "document": _json_model(result.document),
                "duplicate": result.duplicate,
                "retried": result.retried,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def knowledge_documents() -> int:
    with SessionLocal() as db:
        payload = [_json_model(document) for document in list_documents(db)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def knowledge_preview(*, document_id: str) -> int:
    with SessionLocal() as db:
        payload = [_json_model(chunk) for chunk in list_document_chunks(db, document_id)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def knowledge_release_create(
    *,
    release_version: str,
    document_ids: list[str],
    git_commit: str,
    retrieval_strategy_version: str,
) -> int:
    with SessionLocal() as db:
        release = create_knowledge_release(
            db,
            release_version=release_version,
            document_ids=document_ids,
            created_by="cli-knowledge-operations",
            git_commit=git_commit,
            retrieval_strategy_version=retrieval_strategy_version,
        )
    print(json.dumps(_json_model(release), ensure_ascii=False, indent=2))
    return 0


def knowledge_release_action(*, command: str, release_id: str, target_release_id: str | None) -> int:
    with SessionLocal() as db:
        if command == "knowledge-release-evaluate":
            release = evaluate_knowledge_release(db, release_id)
        elif command == "knowledge-release-approve":
            release = approve_knowledge_release(
                db,
                release_id,
                approved_by="cli-knowledge-operations",
            )
        elif command == "knowledge-release-publish":
            release = publish_knowledge_release(db, release_id)
        elif command == "knowledge-release-rollback":
            if not target_release_id:
                raise argparse.ArgumentError(None, "knowledge-release-rollback 需要 --target-release-id")
            release = rollback_knowledge_release(
                db,
                release_id,
                target_release_id=target_release_id,
            )
        else:
            raise argparse.ArgumentError(None, "未知知识快照命令")
    print(json.dumps(_json_model(release), ensure_ascii=False, indent=2))
    return 0


def knowledge_releases() -> int:
    with SessionLocal() as db:
        payload = [_json_model(release) for release in list_releases(db)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def knowledge_embed(*, release_id: str, provider_name: str | None, batch_size: int | None) -> int:
    provider = build_embedding_provider(provider_name)
    with SessionLocal() as db:
        batch = embed_knowledge_release(
            db,
            release_id,
            provider=provider,
            batch_size=batch_size,
        )
    print(json.dumps(_json_model(batch), ensure_ascii=False, indent=2))
    return 0


def knowledge_search(
    *,
    query: str,
    tenant_scope: str,
    channel_scope: str,
    product_scope: str,
    strategy: str,
    provider_name: str | None,
    limit: int,
    now: datetime | None,
) -> int:
    provider = None
    provider_error: EmbeddingProviderError | None = None
    try:
        provider = build_embedding_provider(provider_name)
    except EmbeddingProviderError as error:
        provider_error = error
        if strategy == "vector_v1":
            raise
    with SessionLocal() as db:
        if strategy == "vector_v1":
            results = search_vector_candidates(
                db,
                query,
                provider=provider,
                strategy=strategy,
                tenant_scope=tenant_scope,
                channel_scope=channel_scope,
                product_scope=product_scope,
                now=now,
                limit=limit,
            )
            report = {
                "strategy": strategy,
                "confident": bool(results),
                "score": results[0]["relevance"] if results else 0.0,
                "results": results,
                "fallback": False,
                "fallback_reason": None,
                "release_version": results[0]["release_version"] if results else None,
                "provider": provider.provider if provider else None,
            }
        else:
            report = search_hybrid_knowledge(
                db,
                query,
                provider=provider,
                provider_error=provider_error,
                tenant_scope=tenant_scope,
                channel_scope=channel_scope,
                product_scope=product_scope,
                now=now,
                limit=limit,
                strategy=strategy,
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def parse_as_of(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--as-of 必须是 ISO-8601 时间") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--as-of 必须包含时区")
    return parsed.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ServiceOps Agent maintenance commands")
    parser.add_argument(
        "command",
        choices=(
            "seed",
            "evaluate-knowledge",
            "evaluate-agent",
            "purge-retention",
            "agent-governance",
            "knowledge-ingest",
            "knowledge-documents",
            "knowledge-preview",
            "knowledge-release-create",
            "knowledge-release-evaluate",
            "knowledge-release-approve",
            "knowledge-release-publish",
            "knowledge-release-rollback",
            "knowledge-releases",
            "knowledge-embed",
            "knowledge-search",
        ),
        default="seed",
        nargs="?",
    )
    parser.add_argument(
        "--runtime",
        choices=("deterministic", "model"),
        default="deterministic",
        help="Agent evaluation runtime; model makes real provider calls",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional leading case limit for controlled provider checks",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Delay between real model cases; defaults to configured RPM spacing",
    )
    parser.add_argument(
        "--include-exploratory",
        action="store_true",
        help="Also report de-identified typo, multi-intent, conflict, and OOD cases",
    )
    parser.add_argument(
        "--as-of",
        type=parse_as_of,
        default=None,
        help="Retention evaluation time as ISO-8601 with timezone; defaults to now",
    )
    parser.add_argument("--file", default=None, help="Local document path for knowledge-ingest")
    parser.add_argument("--source-uri", default=None, help="Controlled provenance URI")
    parser.add_argument("--query", default=None, help="Knowledge retrieval query")
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--release-version", default=None)
    parser.add_argument("--target-release-id", default=None)
    parser.add_argument("--git-commit", default="unbound")
    parser.add_argument("--tenant-scope", default="local-demo")
    parser.add_argument("--channel-scope", default="*")
    parser.add_argument("--product-scope", default="*")
    parser.add_argument(
        "--retrieval-strategy",
        choices=("lexical_v1", "vector_v1", "hybrid_rrf_v1"),
        default="lexical_v1",
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--now", type=parse_as_of, default=None)
    args = parser.parse_args(argv)
    if args.command == "evaluate-knowledge":
        return evaluate_knowledge(include_exploratory=args.include_exploratory)
    if args.command == "evaluate-agent":
        return evaluate_agent(
            runtime=args.runtime,
            max_cases=args.max_cases,
            delay_seconds=args.delay_seconds,
        )
    if args.command == "purge-retention":
        return purge_retention(as_of=args.as_of)
    if args.command == "agent-governance":
        return agent_governance()
    if args.command == "knowledge-ingest":
        if not args.file or not args.source_uri:
            parser.error("knowledge-ingest 需要 --file 和 --source-uri")
        return knowledge_ingest(
            file_path=args.file,
            source_uri=args.source_uri,
            idempotency_key=args.idempotency_key,
            tenant_scope=args.tenant_scope,
            channel_scope=args.channel_scope,
            product_scope=args.product_scope,
        )
    if args.command == "knowledge-documents":
        return knowledge_documents()
    if args.command == "knowledge-preview":
        if not args.document_id:
            parser.error("knowledge-preview 需要 --document-id")
        return knowledge_preview(document_id=args.document_id[-1])
    if args.command == "knowledge-release-create":
        if not args.release_version or not args.document_id:
            parser.error("knowledge-release-create 需要 --release-version 和至少一个 --document-id")
        return knowledge_release_create(
            release_version=args.release_version,
            document_ids=args.document_id,
            git_commit=args.git_commit,
            retrieval_strategy_version=args.retrieval_strategy,
        )
    if args.command in {
        "knowledge-release-evaluate",
        "knowledge-release-approve",
        "knowledge-release-publish",
        "knowledge-release-rollback",
    }:
        if not args.release_id:
            parser.error(f"{args.command} 需要 --release-id")
        if args.command == "knowledge-release-rollback" and not args.target_release_id:
            parser.error("knowledge-release-rollback 需要 --target-release-id")
        return knowledge_release_action(
            command=args.command,
            release_id=args.release_id,
            target_release_id=args.target_release_id,
        )
    if args.command == "knowledge-releases":
        return knowledge_releases()
    if args.command == "knowledge-embed":
        if not args.release_id:
            parser.error("knowledge-embed 需要 --release-id")
        return knowledge_embed(
            release_id=args.release_id,
            provider_name=args.provider,
            batch_size=args.batch_size,
        )
    if args.command == "knowledge-search":
        if not args.query:
            parser.error("knowledge-search 需要 --query")
        return knowledge_search(
            query=args.query,
            tenant_scope=args.tenant_scope,
            channel_scope=args.channel_scope,
            product_scope=args.product_scope,
            strategy=args.retrieval_strategy,
            provider_name=args.provider,
            limit=args.limit,
            now=args.now,
        )
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
