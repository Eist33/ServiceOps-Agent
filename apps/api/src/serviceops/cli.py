import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from serviceops.agent.evaluation import evaluate_agent_orchestration
from serviceops.agent.release import governance_snapshot
from serviceops.database import SessionLocal
from serviceops.knowledge.evaluation import (
    EXPLORATORY_CASES,
    EXPLORATORY_DATASET_VERSION,
    evaluate_knowledge_search,
)
from serviceops.knowledge.ingestion import ingest_document, list_document_chunks, list_documents
from serviceops.knowledge.releases import (
    approve_knowledge_release,
    create_knowledge_release,
    evaluate_knowledge_release,
    list_releases,
    publish_knowledge_release,
    rollback_knowledge_release,
)
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


def knowledge_ingest(*, file_path: str, source_uri: str, idempotency_key: str | None) -> int:
    with SessionLocal() as db:
        result = ingest_document(
            db,
            filename=Path(file_path).name,
            source_uri=source_uri,
            data=Path(file_path).read_bytes(),
            idempotency_key=idempotency_key,
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
) -> int:
    with SessionLocal() as db:
        release = create_knowledge_release(
            db,
            release_version=release_version,
            document_ids=document_ids,
            created_by="cli-knowledge-operations",
            git_commit=git_commit,
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
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--release-version", default=None)
    parser.add_argument("--target-release-id", default=None)
    parser.add_argument("--git-commit", default="unbound")
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
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
