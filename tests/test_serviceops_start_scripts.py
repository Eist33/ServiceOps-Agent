from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "scripts" / "start-serviceops.cmd").read_text(encoding="utf-8")
STOP = (ROOT / "scripts" / "stop-serviceops.cmd").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
START_BYTES = (ROOT / "scripts" / "start-serviceops.cmd").read_bytes()
STOP_BYTES = (ROOT / "scripts" / "stop-serviceops.cmd").read_bytes()


def test_start_script_is_docker_only_and_path_safe() -> None:
    for fragment in (
        'for %%I in ("%~dp0..")',
        'cd /d "%PROJECT_DIR%"',
        'docker info --format',
        "docker compose config --quiet",
        "docker compose up -d --build --wait",
        "docker compose ps",
        "docker compose ps --status running --services",
        'docker compose ps --format "{{.Service}} {{.Health}}"',
        'start "" "http://localhost:13000/staff/channel"',
        "docker compose logs --tail=100 postgres api web",
    ):
        assert fragment in START
    assert "powershell" not in START.lower()
    assert "docker compose down -v" not in START.lower()
    assert "curl.exe" not in START.lower()


def test_stop_script_preserves_volumes_and_is_idempotent() -> None:
    assert 'for %%I in ("%~dp0..")' in STOP
    assert 'cd /d "%PROJECT_DIR%"' in STOP
    assert "docker info --format" in STOP
    assert "docker compose stop" in STOP
    assert "docker compose down" not in STOP
    assert "-v" not in STOP.lower()
    assert "serviceops-postgres volume was preserved" in STOP
    assert "docker compose logs --tail=100 postgres api web" in STOP
    assert "powershell" not in STOP.lower()
    assert "curl.exe" not in STOP.lower()


def test_cmd_scripts_use_crlf_for_cmd_unicode_output() -> None:
    for script in (START_BYTES, STOP_BYTES):
        assert b"\r\n" in script
        assert script.count(b"\r\n") == script.count(b"\n")


def test_main_compose_has_healthchecks_for_all_startup_services() -> None:
    assert 'test: ["CMD-SHELL", "pg_isready -U serviceops -d serviceops"]' in COMPOSE
    assert "urlopen('http://localhost:8000/health')" in COMPOSE
    assert "fetch('http://localhost:3000')" in COMPOSE
