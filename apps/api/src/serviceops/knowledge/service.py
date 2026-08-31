import re
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from serviceops.models import KnowledgeArticle

MIN_RELEVANCE = 0.55


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    chinese_chunks = set(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
    bigrams: set[str] = set()
    for chunk in chinese_chunks:
        bigrams.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return words | bigrams


def search_knowledge_base(db: Session, query: str, *, now: datetime | None = None) -> dict:
    current_time = now or datetime.now(UTC)
    articles = list(
        db.scalars(
            select(KnowledgeArticle).where(
                KnowledgeArticle.active.is_(True),
                KnowledgeArticle.valid_from <= current_time,
                or_(
                    KnowledgeArticle.valid_until.is_(None),
                    KnowledgeArticle.valid_until > current_time,
                ),
            )
        )
    )
    query_tokens = _tokens(query)
    ranked: list[tuple[float, KnowledgeArticle]] = []
    for article in articles:
        evidence_tokens = _tokens(" ".join(article.keywords) + " " + article.content)
        overlap = len(query_tokens & evidence_tokens)
        score = min(0.99, overlap / max(1, min(4, len(query_tokens))))
        ranked.append((score, article))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < MIN_RELEVANCE:
        return {"confident": False, "score": ranked[0][0] if ranked else 0.0, "results": []}
    score, article = ranked[0]
    return {
        "confident": True,
        "score": round(score, 2),
        "results": [
            {
                "article_id": article.id,
                "title": article.title,
                "version": article.version,
                "section": article.section,
                "content": article.content,
                "source_uri": article.source_uri,
                "relevance": round(score, 2),
            }
        ],
    }
