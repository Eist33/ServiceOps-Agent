import re
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from serviceops.models import KnowledgeArticle

MIN_RELEVANCE = 0.55

_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "cancel": ("取消", "撤销", "不想要", "拦截"),
    "damage": ("破损", "摔坏", "压坏", "运输破损"),
    "evidence": ("凭证", "照片", "上传"),
    "exchange": ("换货", "换一个", "更换"),
    "excluded_goods": ("定制", "生鲜", "贴身", "内衣", "拆封"),
    "gift": ("赠品", "满赠", "礼品"),
    "human": ("人工", "真人", "客服"),
    "in_transit": ("运输中", "在路上", "路上", "承运商拦截", "拦截"),
    "invoice": ("发票", "票据", "冲红"),
    "knowledge_gap": ("知识库", "查不到", "解决不了", "无法确认", "工具发生异常", "机器人"),
    "logistics": ("物流", "快递", "包裹", "承运商", "运输"),
    "lost": ("丢件", "丢了", "丢失", "找不到"),
    "no_reason": ("无理由", "不喜欢", "不合适", "反悔"),
    "opened": ("拆封", "包装打开"),
    "quality_issue": ("质量问题", "次品", "故障", "有问题", "商品坏"),
    "receipt": ("签收", "收到商品", "收到"),
    "refund": ("退款", "退钱", "钱会退", "钱退", "原路退回"),
    "refund_destination": ("退到哪里", "退回哪里", "原支付", "原路", "支付路径"),
    "refund_eta": ("多久到账", "到账", "工作日", "何时收到"),
    "return": ("退货", "退换货", "退回", "寄回", "能退", "退吗"),
    "shipping_fee": ("运费", "邮费", "快递费", "谁承担"),
    "stale": ("停滞", "没更新", "不更新", "卡住", "没动", "异常", "催一下", "跟进"),
    "time_window": (
        "多久",
        "几天",
        "7 天",
        "7天",
        "七天",
        "一周",
        "15 天",
        "15天",
        "36 小时",
        "36小时",
    ),
    "unshipped": ("未发货", "没发货", "还没发货", "没有发货"),
}


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    chinese_chunks = set(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
    bigrams: set[str] = set()
    for chunk in chinese_chunks:
        bigrams.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return words | bigrams


def _concepts(text: str) -> set[str]:
    lowered = text.lower()
    return {
        concept
        for concept, aliases in _CONCEPT_ALIASES.items()
        if any(alias in lowered for alias in aliases)
    }


def _concept_denominator(query_concepts: set[str]) -> int:
    # A knowledge-gap request is a complete routing intent on its own. Other
    # policy answers require at least two corroborating business concepts.
    if query_concepts and query_concepts <= {"knowledge_gap"}:
        return len(query_concepts)
    return max(2, len(query_concepts))


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
    query_concepts = _concepts(query)
    ranked: list[tuple[float, int, float, KnowledgeArticle]] = []
    for article in articles:
        evidence = " ".join(article.keywords) + " " + article.content
        evidence_tokens = _tokens(evidence)
        evidence_concepts = _concepts(evidence)
        matched_concepts = query_concepts & evidence_concepts
        concept_coverage = len(matched_concepts) / _concept_denominator(query_concepts)
        token_coverage = len(query_tokens & evidence_tokens) / max(1, min(8, len(query_tokens)))
        score = min(0.99, 0.72 * concept_coverage + 0.28 * token_coverage)
        ranked.append((score, len(matched_concepts), token_coverage, article))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    if not ranked or ranked[0][0] < MIN_RELEVANCE:
        return {"confident": False, "score": ranked[0][0] if ranked else 0.0, "results": []}
    score, _, _, article = ranked[0]
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
