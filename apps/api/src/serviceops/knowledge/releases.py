"""Immutable knowledge snapshot lifecycle for stage 2.

Releases contain only parsed document and chunk references.  Publishing never
rewrites the stage-0 ``KnowledgeArticle`` rows, so ``lexical_v1`` keeps its
existing behaviour until a later, separately approved retrieval stage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.knowledge.evaluation import (
    KNOWLEDGE_DATASET_VERSION,
    evaluate_knowledge_search,
)
from serviceops.knowledge.ingestion import CHUNKING_VERSION, PARSER_VERSION
from serviceops.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRelease,
    KnowledgeReleaseItem,
    new_id,
)
from serviceops.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

RETRIEVAL_STRATEGY_VERSION = "lexical_v1"
RELEASE_EVALUATION_DATASET_VERSION = KNOWLEDGE_DATASET_VERSION
RELEASE_STATUSES = frozenset(
    {"DRAFT", "EVALUATED", "REJECTED", "APPROVED", "PUBLISHED", "RETIRED", "ROLLED_BACK"}
)


class KnowledgeReleaseError(DomainError):
    """A safe lifecycle failure that does not expose document contents."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code, message, status_code)


def _now() -> datetime:
    return datetime.now(UTC)


def get_release(db: Session, release_id: str) -> KnowledgeRelease:
    release = db.get(KnowledgeRelease, release_id)
    if release is None:
        raise NotFoundError("知识快照不存在")
    return release


def list_releases(db: Session) -> list[KnowledgeRelease]:
    return list(
        db.scalars(
            select(KnowledgeRelease).order_by(KnowledgeRelease.created_at.desc())
        )
    )


def list_release_items(db: Session, release_id: str) -> list[KnowledgeReleaseItem]:
    get_release(db, release_id)
    return list(
        db.scalars(
            select(KnowledgeReleaseItem)
            .where(KnowledgeReleaseItem.release_id == release_id)
            .order_by(KnowledgeReleaseItem.ordinal.asc())
        )
    )


def _snapshot_documents(
    db: Session,
    document_ids: list[str],
) -> tuple[list[KnowledgeDocument], list[KnowledgeChunk]]:
    if not document_ids or len(set(document_ids)) != len(document_ids):
        raise ValidationError("KNOWLEDGE_DOCUMENTS_REQUIRED", "快照必须包含不重复的已解析文档")
    documents = []
    chunks: list[KnowledgeChunk] = []
    for document_id in document_ids:
        document = db.get(KnowledgeDocument, document_id)
        if document is None:
            raise NotFoundError("知识文档不存在")
        if document.status != "PARSED":
            raise KnowledgeReleaseError(
                "KNOWLEDGE_DOCUMENT_NOT_READY",
                "只有解析成功的文档才能加入知识快照",
            )
        document_chunks = list(
            db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document.id)
                .order_by(KnowledgeChunk.chunk_index.asc())
            )
        )
        if not document_chunks:
            raise KnowledgeReleaseError("KNOWLEDGE_DOCUMENT_EMPTY", "文档没有可发布切块")
        documents.append(document)
        chunks.extend(document_chunks)
    return documents, chunks


def create_knowledge_release(
    db: Session,
    *,
    release_version: str,
    document_ids: list[str],
    created_by: str,
    git_commit: str = "unbound",
    evaluation_dataset_version: str = RELEASE_EVALUATION_DATASET_VERSION,
) -> KnowledgeRelease:
    version = release_version.strip()
    actor = created_by.strip()
    commit = git_commit.strip() or "unbound"
    if len(version) < 2 or len(version) > 80:
        raise ValidationError("KNOWLEDGE_RELEASE_VERSION_INVALID", "知识快照版本格式无效")
    if not actor:
        raise ValidationError("KNOWLEDGE_RELEASE_ACTOR_REQUIRED", "知识快照必须记录创建人")
    if len(commit) > 64:
        raise ValidationError("KNOWLEDGE_RELEASE_COMMIT_INVALID", "关联提交标识过长")
    if evaluation_dataset_version.strip() != RELEASE_EVALUATION_DATASET_VERSION:
        raise KnowledgeReleaseError(
            "KNOWLEDGE_EVALUATION_DATASET_UNSUPPORTED",
            "阶段 2 只允许使用冻结的知识评测集版本",
        )
    duplicate = db.scalar(
        select(KnowledgeRelease).where(KnowledgeRelease.release_version == version)
    )
    if duplicate:
        raise ConflictError("KNOWLEDGE_RELEASE_EXISTS", "知识快照版本已经存在")
    documents, chunks = _snapshot_documents(db, document_ids)
    parser_versions = {document.parser_version for document in documents}
    chunking_versions = {document.chunking_version for document in documents}
    if parser_versions != {PARSER_VERSION} or chunking_versions != {CHUNKING_VERSION}:
        raise KnowledgeReleaseError(
            "KNOWLEDGE_PIPELINE_VERSION_MISMATCH",
            "文档解析器或切块策略版本不一致",
        )
    release = KnowledgeRelease(
        release_version=version,
        status="DRAFT",
        parser_version=PARSER_VERSION,
        chunking_version=CHUNKING_VERSION,
        retrieval_strategy_version=RETRIEVAL_STRATEGY_VERSION,
        evaluation_dataset_version=RELEASE_EVALUATION_DATASET_VERSION,
        source_manifest=[
            {
                "document_id": document.id,
                "filename": document.filename,
                "source_uri": document.source_uri,
                "content_hash": document.content_hash,
                "byte_size": document.byte_size,
                "chunk_count": document.chunk_count,
            }
            for document in documents
        ],
        git_commit=commit,
        created_by=actor,
    )
    db.add(release)
    db.flush()
    db.add_all(
        [
            KnowledgeReleaseItem(
                id=new_id(),
                release_id=release.id,
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                ordinal=ordinal,
                content_hash=chunk.content_hash,
                source_uri=chunk.source_uri,
                title_path=chunk.title_path,
                page_number=chunk.page_number,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
            )
            for ordinal, chunk in enumerate(chunks)
        ]
    )
    db.commit()
    db.refresh(release)
    return release


def _release_evaluation(release: KnowledgeRelease, db: Session) -> dict[str, Any]:
    items = list_release_items(db, release.id)
    document_ids = {item.document_id for item in items}
    content_hashes = [item.content_hash for item in items]
    traceable = all(
        item.source_uri.strip()
        and item.start_offset >= 0
        and item.end_offset > item.start_offset
        and isinstance(item.title_path, list)
        for item in items
    )
    baseline = evaluate_knowledge_search(db)
    failures: list[str] = []
    if not items:
        failures.append("no_chunks")
    if len(content_hashes) != len(set(content_hashes)):
        failures.append("duplicate_chunk_hash")
    if not traceable:
        failures.append("untraceable_chunk")
    if not baseline["passed"]:
        failures.append("lexical_baseline_failed")
    return {
        "release_id": release.id,
        "release_version": release.release_version,
        "parser_version": release.parser_version,
        "chunking_version": release.chunking_version,
        "retrieval_strategy_version": release.retrieval_strategy_version,
        "evaluation_dataset_version": release.evaluation_dataset_version,
        "snapshot": {
            "document_count": len(document_ids),
            "chunk_count": len(items),
            "unique_chunk_hashes": len(set(content_hashes)),
            "traceable": traceable,
        },
        "baseline": {
            "dataset_version": baseline["dataset_version"],
            "passed": baseline["passed"],
            "metrics": baseline["metrics"],
        },
        "passed": not failures,
        "failures": failures,
    }


def evaluate_knowledge_release(db: Session, release_id: str) -> KnowledgeRelease:
    release = get_release(db, release_id)
    if release.status in {"APPROVED", "PUBLISHED", "RETIRED", "ROLLED_BACK"}:
        raise KnowledgeReleaseError("KNOWLEDGE_RELEASE_IMMUTABLE", "已审核快照不能重新评测")
    report = _release_evaluation(release, db)
    release.evaluation_report = report
    release.evaluated_at = _now()
    release.status = "EVALUATED" if report["passed"] else "REJECTED"
    db.commit()
    db.refresh(release)
    return release


def approve_knowledge_release(db: Session, release_id: str, *, approved_by: str) -> KnowledgeRelease:
    release = get_release(db, release_id)
    if release.status == "APPROVED":
        return release
    if release.status == "REJECTED":
        raise KnowledgeReleaseError(
            "KNOWLEDGE_RELEASE_EVALUATION_FAILED",
            "评测未通过，不能审核发布",
        )
    if release.status != "EVALUATED" or not release.evaluation_report:
        raise KnowledgeReleaseError("KNOWLEDGE_RELEASE_NOT_EVALUATED", "快照必须先完成评测")
    if not release.evaluation_report.get("passed"):
        raise KnowledgeReleaseError("KNOWLEDGE_RELEASE_EVALUATION_FAILED", "评测未通过，不能审核发布")
    actor = approved_by.strip()
    if not actor:
        raise ValidationError("KNOWLEDGE_RELEASE_ACTOR_REQUIRED", "审核人不能为空")
    release.status = "APPROVED"
    release.approved_by = actor
    release.approved_at = _now()
    db.commit()
    db.refresh(release)
    return release


def publish_knowledge_release(db: Session, release_id: str) -> KnowledgeRelease:
    release = get_release(db, release_id)
    if release.status == "PUBLISHED":
        return release
    if release.status != "APPROVED":
        raise KnowledgeReleaseError("KNOWLEDGE_RELEASE_NOT_APPROVED", "只有已审核快照才能发布")
    now = _now()
    previous = list(
        db.scalars(
            select(KnowledgeRelease).where(
                KnowledgeRelease.status == "PUBLISHED",
                KnowledgeRelease.id != release.id,
            )
        )
    )
    for item in previous:
        item.status = "RETIRED"
    release.status = "PUBLISHED"
    release.published_at = now
    db.commit()
    db.refresh(release)
    return release


def rollback_knowledge_release(
    db: Session,
    release_id: str,
    *,
    target_release_id: str,
) -> KnowledgeRelease:
    release = get_release(db, release_id)
    target = get_release(db, target_release_id)
    if release.id == target.id:
        raise KnowledgeReleaseError("KNOWLEDGE_ROLLBACK_TARGET_INVALID", "回滚目标不能是当前快照")
    if release.status != "PUBLISHED":
        raise KnowledgeReleaseError("KNOWLEDGE_RELEASE_NOT_PUBLISHED", "只有当前发布快照才能回滚")
    if target.status not in {"RETIRED", "APPROVED", "PUBLISHED"}:
        raise KnowledgeReleaseError("KNOWLEDGE_ROLLBACK_TARGET_INVALID", "回滚目标不是可用快照")
    now = _now()
    release.status = "ROLLED_BACK"
    release.rollback_release_id = target.id
    release.rolled_back_at = now
    target.status = "PUBLISHED"
    target.published_at = now
    db.commit()
    db.refresh(target)
    return target
