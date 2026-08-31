import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import KnowledgeArticle
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError
from serviceops.shared.schemas import KnowledgePublishRequest


def list_knowledge_articles(db: Session) -> list[KnowledgeArticle]:
    return list(
        db.scalars(
            select(KnowledgeArticle).order_by(
                KnowledgeArticle.created_at.desc(),
                KnowledgeArticle.section.asc(),
            )
        )
    )


def publish_knowledge_article(
    db: Session,
    body: KnowledgePublishRequest,
) -> KnowledgeArticle:
    title = body.title.strip()
    version = body.version.strip()
    section = body.section.strip()
    content = body.content.strip()
    source_uri = body.source_uri.strip()
    keywords = list(dict.fromkeys(keyword.strip() for keyword in body.keywords if keyword.strip()))
    if not keywords:
        raise ValidationError("KNOWLEDGE_KEYWORDS_REQUIRED", "至少填写一个有效关键词")

    duplicate = db.scalar(
        select(KnowledgeArticle).where(
            KnowledgeArticle.title == title,
            KnowledgeArticle.version == version,
            KnowledgeArticle.section == section,
        )
    )
    if duplicate:
        raise ConflictError("KNOWLEDGE_VERSION_EXISTS", "该条款版本已经存在")

    published_at = datetime.now(UTC)
    previous_versions = list(
        db.scalars(
            select(KnowledgeArticle).where(
                KnowledgeArticle.title == title,
                KnowledgeArticle.section == section,
                KnowledgeArticle.active.is_(True),
            )
        )
    )
    for article in previous_versions:
        article.active = False
        article.valid_until = published_at

    article = KnowledgeArticle(
        title=title,
        version=version,
        section=section,
        content=content,
        keywords=keywords,
        embedding=None,
        source_uri=source_uri,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        active=True,
        valid_from=published_at,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def deactivate_knowledge_article(db: Session, article_id: str) -> KnowledgeArticle:
    article = db.get(KnowledgeArticle, article_id)
    if not article:
        raise NotFoundError("知识条款不存在")
    if article.active:
        article.active = False
        article.valid_until = datetime.now(UTC)
        db.commit()
        db.refresh(article)
    return article
