from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package-portainer.ps1"
COMPOSE = ROOT / "docker-compose.portainer.yml"


def test_portainer_packaging_script_uses_incrementing_release_tags():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "yyyyMMdd" in script
    assert "-r$nextNumber" in script
    assert "serviceops-api:$ReleaseTag" in script
    assert "serviceops-web:$ReleaseTag" in script
    assert '"save",' in script


def test_portainer_packaging_script_bakes_server_api_url_and_checks_compose():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_API_URL=$publicApiUrl" in script
    assert "Generated Compose does not reference both images" in script
    assert '@("compose", "-f"' in script
    assert "bundle_sha256" in script
    assert "apiPortMapping" in script


def test_portainer_compose_keeps_api_and_web_image_tags_aligned():
    compose = COMPOSE.read_text(encoding="utf-8")

    api_line = next(line for line in compose.splitlines() if "image: serviceops-api:" in line)
    web_line = next(line for line in compose.splitlines() if "image: serviceops-web:" in line)
    api_tag = api_line.rsplit(":", 1)[1].strip()
    web_tag = web_line.rsplit(":", 1)[1].strip()
    assert api_tag == web_tag
    assert "POSTGRES_PASSWORD: serviceops" in compose
    assert "postgresql+psycopg://serviceops:serviceops@postgres:5432/serviceops" in compose
