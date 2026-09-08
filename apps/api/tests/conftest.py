import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

database_path = Path(tempfile.gettempdir()) / "serviceops-agent-tests.db"
os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
os.environ["AGENT_MODE"] = "deterministic"
os.environ["DEMO_LOGIN_PASSWORD"] = "test-password"

from serviceops.database import Base, engine  # noqa: E402
from serviceops.main import create_app  # noqa: E402
from serviceops.seed import DEMO_SESSION_TOKEN, SECONDARY_SESSION_TOKEN, seed_database  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        seed_database(db)
    yield


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        test_client.headers.update({"X-Demo-Session": DEMO_SESSION_TOKEN})
        yield test_client


@pytest.fixture
def other_client():
    app = create_app()
    with TestClient(app) as test_client:
        test_client.headers.update({"X-Demo-Session": SECONDARY_SESSION_TOKEN})
        yield test_client


@pytest.fixture
def db():
    with Session(engine) as session:
        yield session
