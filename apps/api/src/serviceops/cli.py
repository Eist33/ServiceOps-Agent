from serviceops.database import SessionLocal
from serviceops.seed import seed_database


def seed() -> None:
    with SessionLocal() as db:
        seed_database(db)


if __name__ == "__main__":
    seed()
