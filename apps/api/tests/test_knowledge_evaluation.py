import json
from collections import Counter

import pytest

from serviceops.cli import main
from serviceops.knowledge.evaluation import (
    BASELINE_AS_OF,
    DEFAULT_CASES,
    EXPLORATORY_CASES,
    EXPLORATORY_DATASET_VERSION,
    KNOWLEDGE_DATASET_VERSION,
    evaluate_knowledge_search,
)
from serviceops.knowledge.service import search_knowledge_base
from serviceops.seed import POLICIES


def test_evaluation_dataset_covers_every_policy_section_twice():
    counts = Counter(case.expected_section for case in DEFAULT_CASES if case.expected_section)
    assert set(counts) == {section for section, _, _ in POLICIES}
    assert all(count >= 2 for count in counts.values())
    assert sum(case.expected_section is None for case in DEFAULT_CASES) >= 6


def test_knowledge_retrieval_meets_quality_gate(db):
    report = evaluate_knowledge_search(db)
    assert report["answerable_accuracy"] >= 0.95, report["failures"]
    assert report["false_accept_rate"] == 0, report["failures"]
    assert report["passed"] is True


def test_baseline_report_is_versioned_and_contains_immutable_metrics(db):
    report = evaluate_knowledge_search(db)

    assert report["strategy_version"] == "lexical_v1"
    assert report["dataset_version"] == KNOWLEDGE_DATASET_VERSION
    assert report["as_of"] == BASELINE_AS_OF.isoformat()
    assert set(report["metrics"]) == {
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "mrr",
        "refusal_accuracy",
        "p95_latency_ms",
    }
    assert report["metrics"]["hit_at_1"] == report["answerable_accuracy"]
    assert report["metrics"]["hit_at_3"] >= report["metrics"]["hit_at_1"]
    assert report["metrics"]["hit_at_5"] >= report["metrics"]["hit_at_3"]
    assert report["metrics"]["p95_latency_ms"] >= 0


def test_repeated_fixed_clock_evaluation_has_identical_decisions(db):
    first = evaluate_knowledge_search(db)
    second = evaluate_knowledge_search(db)

    first["metrics"].pop("p95_latency_ms")
    second["metrics"].pop("p95_latency_ms")
    assert first == second


def test_exploratory_cases_are_separately_versioned_without_changing_gate(db):
    report = evaluate_knowledge_search(
        db,
        EXPLORATORY_CASES,
        dataset_version=EXPLORATORY_DATASET_VERSION,
    )

    assert report["dataset_version"] == EXPLORATORY_DATASET_VERSION
    assert report["total"] == len(EXPLORATORY_CASES)
    assert report["strategy_version"] == "lexical_v1"


@pytest.mark.parametrize(
    ("query", "expected_section"),
    [
        ("签收一周可以反悔吗", "第 2.1 条"),
        ("运输中不想要怎么处理", "第 3.1 条"),
        ("次品寄回去邮费谁承担", "第 4.2 条"),
        ("机器人解决不了怎么找人工", "第 7.2 条"),
    ],
)
def test_natural_paraphrases_match_expected_sections(db, query, expected_section):
    result = search_knowledge_base(db, query)
    assert result["confident"] is True
    assert result["results"][0]["section"] == expected_section


def test_cli_defaults_to_seed():
    assert main([]) == 0


def test_cli_evaluation_prints_machine_readable_report(capsys):
    assert main(["evaluate-knowledge"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is True
    assert report["total"] == len(DEFAULT_CASES)


def test_cli_can_report_exploratory_cases_separately(capsys):
    assert main(["evaluate-knowledge", "--include-exploratory"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is True
    assert report["exploratory"]["dataset_version"] == EXPLORATORY_DATASET_VERSION
    assert report["exploratory"]["total"] == len(EXPLORATORY_CASES)
