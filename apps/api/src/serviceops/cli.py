import argparse
import json
from datetime import UTC, datetime

from serviceops.agent.evaluation import evaluate_agent_orchestration
from serviceops.agent.release import governance_snapshot
from serviceops.database import SessionLocal
from serviceops.knowledge.evaluation import (
    EXPLORATORY_CASES,
    EXPLORATORY_DATASET_VERSION,
    evaluate_knowledge_search,
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
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
