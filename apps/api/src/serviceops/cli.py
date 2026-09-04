import argparse
import json

from serviceops.agent.evaluation import evaluate_agent_orchestration
from serviceops.database import SessionLocal
from serviceops.knowledge.evaluation import evaluate_knowledge_search
from serviceops.seed import seed_database


def seed() -> None:
    with SessionLocal() as db:
        seed_database(db)


def evaluate_knowledge() -> int:
    with SessionLocal() as db:
        seed_database(db)
        report = evaluate_knowledge_search(db)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ServiceOps Agent maintenance commands")
    parser.add_argument(
        "command",
        choices=("seed", "evaluate-knowledge", "evaluate-agent"),
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
    args = parser.parse_args(argv)
    if args.command == "evaluate-knowledge":
        return evaluate_knowledge()
    if args.command == "evaluate-agent":
        return evaluate_agent(
            runtime=args.runtime,
            max_cases=args.max_cases,
            delay_seconds=args.delay_seconds,
        )
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
