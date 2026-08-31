from collections.abc import Iterable
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from serviceops.knowledge.service import search_knowledge_base


@dataclass(frozen=True)
class KnowledgeEvaluationCase:
    query: str
    expected_section: str | None


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


def evaluate_knowledge_search(
    db: Session,
    cases: Iterable[KnowledgeEvaluationCase] = DEFAULT_CASES,
) -> dict:
    case_list = list(cases)
    answerable = sum(case.expected_section is not None for case in case_list)
    unanswerable = len(case_list) - answerable
    correct_answerable = 0
    correct_refusals = 0
    failures: list[dict] = []

    for case in case_list:
        result = search_knowledge_base(db, case.query)
        actual_section = result["results"][0]["section"] if result["results"] else None
        if actual_section == case.expected_section:
            if case.expected_section is None:
                correct_refusals += 1
            else:
                correct_answerable += 1
            continue
        failures.append(
            {
                **asdict(case),
                "actual_section": actual_section,
                "score": round(result["score"], 3),
            }
        )

    answerable_accuracy = correct_answerable / answerable if answerable else 1.0
    false_accept_rate = (unanswerable - correct_refusals) / unanswerable if unanswerable else 0.0
    overall_accuracy = (correct_answerable + correct_refusals) / len(case_list) if case_list else 1.0
    return {
        "total": len(case_list),
        "answerable": answerable,
        "unanswerable": unanswerable,
        "correct_answerable": correct_answerable,
        "correct_refusals": correct_refusals,
        "answerable_accuracy": round(answerable_accuracy, 4),
        "false_accept_rate": round(false_accept_rate, 4),
        "overall_accuracy": round(overall_accuracy, 4),
        "passed": answerable_accuracy >= 0.95 and false_accept_rate == 0,
        "failures": failures,
    }
