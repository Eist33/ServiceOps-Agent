import argparse
import json

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ServiceOps Agent maintenance commands")
    parser.add_argument(
        "command",
        choices=("seed", "evaluate-knowledge"),
        default="seed",
        nargs="?",
    )
    args = parser.parse_args(argv)
    if args.command == "evaluate-knowledge":
        return evaluate_knowledge()
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
