from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import ceil
from time import perf_counter

from sqlalchemy.orm import Session

from serviceops.knowledge.service import RETRIEVAL_STRATEGY_VERSION, search_knowledge_base

KNOWLEDGE_DATASET_VERSION = "knowledge-baseline-30-v1"
EXPLORATORY_DATASET_VERSION = "knowledge-exploratory-edge-v1"
BASELINE_AS_OF = datetime(2026, 9, 6, tzinfo=UTC)
EVALUATION_TOP_K = 5


@dataclass(frozen=True)
class KnowledgeEvaluationCase:
    query: str
    expected_section: str | None
    expected_sections: tuple[str, ...] = ()
    category: str = "baseline"

    @property
    def accepted_sections(self) -> tuple[str, ...]:
        if self.expected_sections:
            return self.expected_sections
        if self.expected_section is not None:
            return (self.expected_section,)
        return ()


DEFAULT_CASES = (
    KnowledgeEvaluationCase("东西不喜欢多久能退", "第 2.1 条"),
    KnowledgeEvaluationCase("签收一周可以反悔吗", "第 2.1 条"),
    KnowledgeEvaluationCase("生鲜能七天无理由吗", "第 2.2 条"),
    KnowledgeEvaluationCase("内衣拆封后还能退吗", "第 2.2 条"),
    KnowledgeEvaluationCase("包裹还在路上可以退款吗", "第 3.1 条"),
    KnowledgeEvaluationCase("运输中不想要怎么处理", "第 3.1 条"),
    KnowledgeEvaluationCase("退款多久到账", "第 3.2 条"),
    KnowledgeEvaluationCase("钱会退到哪里", "第 3.2 条"),
    KnowledgeEvaluationCase("商品坏了想换一个", "第 4.1 条"),
    KnowledgeEvaluationCase("质量问题换货要提供照片吗", "第 4.1 条"),
    KnowledgeEvaluationCase("次品寄回去邮费谁承担", "第 4.2 条"),
    KnowledgeEvaluationCase("质量问题退换货的运费谁出", "第 4.2 条"),
    KnowledgeEvaluationCase("快递多久没更新算异常", "第 5.1 条"),
    KnowledgeEvaluationCase("物流卡住能帮忙催吗", "第 5.1 条"),
    KnowledgeEvaluationCase("快递把东西摔坏了怎么办", "第 5.2 条"),
    KnowledgeEvaluationCase("包裹可能丢了", "第 5.2 条"),
    KnowledgeEvaluationCase("开过发票退货怎么办", "第 6.1 条"),
    KnowledgeEvaluationCase("退货发票要怎么处理", "第 6.1 条"),
    KnowledgeEvaluationCase("整单退货赠品也要寄回吗", "第 6.2 条"),
    KnowledgeEvaluationCase("满赠礼品退货时要不要退", "第 6.2 条"),
    KnowledgeEvaluationCase("订单还没发货怎么取消", "第 7.1 条"),
    KnowledgeEvaluationCase("未发货订单不想要了", "第 7.1 条"),
    KnowledgeEvaluationCase("机器人解决不了怎么找人工", "第 7.2 条"),
    KnowledgeEvaluationCase("知识库查不到怎么办", "第 7.2 条"),
    KnowledgeEvaluationCase("积分可以换会员吗", None),
    KnowledgeEvaluationCase("怎么修改收货地址", None),
    KnowledgeEvaluationCase("有没有优惠券", None),
    KnowledgeEvaluationCase("商品保修几年", None),
    KnowledgeEvaluationCase("如何开发票", None),
    KnowledgeEvaluationCase("怎么评价商品", None),
)


# These de-identified exploratory utterances make the edge-case gap visible
# without changing the fixed 30-case release gate. They are deliberately
# reported separately until a future phase decides whether they belong in a
# revised baseline.
EXPLORATORY_CASES = (
    KnowledgeEvaluationCase("签收一周可以返悔吗", "第 2.1 条", category="typo"),
    KnowledgeEvaluationCase("内衣拆开了还可以无理由退吗", "第 2.2 条", category="synonym"),
    KnowledgeEvaluationCase(
        "包裹在路上不想要了，能不能退",
        "第 3.1 条",
        category="multi_intent",
    ),
    KnowledgeEvaluationCase(
        "商品破损而且想换一个，需要什么凭证",
        "第 4.1 条",
        category="multi_intent",
    ),
    KnowledgeEvaluationCase(
        "物流没动又怀疑丢件，怎么跟进",
        None,
        expected_sections=("第 5.1 条", "第 5.2 条"),
        category="conflict",
    ),
    KnowledgeEvaluationCase(
        "发票已开但我要退货，赠品也要寄回吗",
        None,
        expected_sections=("第 6.1 条", "第 6.2 条"),
        category="multi_intent",
    ),
    KnowledgeEvaluationCase("会员积分和优惠券都怎么用", None, category="out_of_domain"),
    KnowledgeEvaluationCase("怎么改收货地址并申请保价", None, category="out_of_domain"),
)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, ceil(len(ordered) * percentile) - 1))
    return round(ordered[index], 3)


def evaluate_knowledge_search(
    db: Session,
    cases: Iterable[KnowledgeEvaluationCase] = DEFAULT_CASES,
    *,
    now: datetime = BASELINE_AS_OF,
    dataset_version: str = KNOWLEDGE_DATASET_VERSION,
) -> dict:
    """Evaluate one immutable lexical baseline dataset at a fixed clock.

    The function only reads the supplied database and returns JSON-safe
    primitives. It never changes knowledge articles, calls a provider, or
    performs network I/O. Timing is observational; ranking and refusal
    judgments are deterministic for a fixed database and ``now``.
    """

    case_list = list(cases)
    answerable = sum(bool(case.accepted_sections) for case in case_list)
    unanswerable = len(case_list) - answerable
    correct_at_1 = 0
    correct_refusals = 0
    reciprocal_ranks: list[float] = []
    hits_at_3 = 0
    hits_at_5 = 0
    failures: list[dict] = []
    latencies_ms: list[float] = []

    for case in case_list:
        started = perf_counter()
        result = search_knowledge_base(db, case.query, now=now, limit=EVALUATION_TOP_K)
        latencies_ms.append((perf_counter() - started) * 1000)
        actual_sections = [item["section"] for item in result["results"]]
        accepted = set(case.accepted_sections)
        rank = next(
            (index + 1 for index, section in enumerate(actual_sections) if section in accepted),
            None,
        )

        if not accepted:
            if not result["results"]:
                correct_refusals += 1
            else:
                failures.append(
                    {
                        **asdict(case),
                        "actual_sections": actual_sections,
                        "score": round(result["score"], 3),
                        "failure": "unexpected_answer",
                    }
                )
            continue

        if rank == 1:
            correct_at_1 += 1
        if rank is not None and rank <= 3:
            hits_at_3 += 1
        if rank is not None and rank <= 5:
            hits_at_5 += 1
        reciprocal_ranks.append(1 / rank if rank is not None else 0.0)
        if rank != 1:
            failures.append(
                {
                    **asdict(case),
                    "actual_sections": actual_sections,
                    "score": round(result["score"], 3),
                    "failure": "top_1_miss",
                    "rank": rank,
                }
            )

    hit_at_1 = correct_at_1 / answerable if answerable else 1.0
    hit_at_3 = hits_at_3 / answerable if answerable else 1.0
    hit_at_5 = hits_at_5 / answerable if answerable else 1.0
    mrr = sum(reciprocal_ranks) / answerable if answerable else 1.0
    refusal_accuracy = correct_refusals / unanswerable if unanswerable else 1.0
    false_accept_rate = 1 - refusal_accuracy if unanswerable else 0.0
    metrics = {
        "hit_at_1": round(hit_at_1, 4),
        "hit_at_3": round(hit_at_3, 4),
        "hit_at_5": round(hit_at_5, 4),
        "mrr": round(mrr, 4),
        "refusal_accuracy": round(refusal_accuracy, 4),
        "p95_latency_ms": _percentile(latencies_ms, 0.95),
    }
    return {
        "strategy_version": RETRIEVAL_STRATEGY_VERSION,
        "dataset_version": dataset_version,
        "as_of": now.isoformat(),
        "total": len(case_list),
        "answerable": answerable,
        "unanswerable": unanswerable,
        "correct_answerable": correct_at_1,
        "correct_refusals": correct_refusals,
        "answerable_accuracy": metrics["hit_at_1"],
        "false_accept_rate": round(false_accept_rate, 4),
        "overall_accuracy": round(
            (correct_at_1 + correct_refusals) / len(case_list), 4
        )
        if case_list
        else 1.0,
        "metrics": metrics,
        "passed": hit_at_1 >= 0.95 and false_accept_rate == 0,
        "failures": failures,
    }
