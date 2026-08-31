from serviceops.knowledge.service import search_knowledge_base
from serviceops.seed import OPS_SESSION_TOKEN

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}


def test_knowledge_operations_require_operator_identity(client):
    response = client.get("/api/ops/knowledge")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_operator_can_list_seeded_knowledge(client):
    response = client.get("/api/ops/knowledge", headers=OPS_HEADERS)

    assert response.status_code == 200
    articles = response.json()
    assert len(articles) == 12
    assert all(article["title"] == "平台退换货规则" for article in articles)
    assert all(article["active"] is True for article in articles)


def test_publish_new_version_retires_previous_article_and_changes_search(client, db):
    response = client.post(
        "/api/ops/knowledge",
        headers=OPS_HEADERS,
        json={
            "title": "平台退换货规则",
            "version": "2026-09",
            "section": "第 2.1 条",
            "content": "大多数商品支持签收后 10 天内无理由退货，商品与赠品需保持完整。",
            "keywords": ["退货", "无理由", "10天", "签收"],
            "source_uri": "kb://after-sales/2026-09/第-2.1-条",
        },
    )

    assert response.status_code == 200
    assert response.json()["active"] is True
    articles = client.get("/api/ops/knowledge", headers=OPS_HEADERS).json()
    matching = [article for article in articles if article["section"] == "第 2.1 条"]
    assert len(matching) == 2
    assert {article["version"] for article in matching if article["active"]} == {"2026-09"}
    result = search_knowledge_base(db, "10天内可以无理由退货吗")
    assert result["results"][0]["version"] == "2026-09"
    assert "10 天" in result["results"][0]["content"]


def test_duplicate_version_is_rejected(client):
    payload = {
        "title": "平台退换货规则",
        "version": "2026-07",
        "section": "第 2.1 条",
        "content": "重复内容不应发布。",
        "keywords": ["退货"],
        "source_uri": "kb://duplicate",
    }

    response = client.post("/api/ops/knowledge", headers=OPS_HEADERS, json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "KNOWLEDGE_VERSION_EXISTS"


def test_operator_can_deactivate_article(client, db):
    articles = client.get("/api/ops/knowledge", headers=OPS_HEADERS).json()
    article = next(item for item in articles if item["section"] == "第 2.1 条")

    response = client.post(
        f"/api/ops/knowledge/{article['id']}/deactivate",
        headers=OPS_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    result = search_knowledge_base(db, "7天无理由退货")
    assert not result["results"] or result["results"][0]["section"] != "第 2.1 条"


def test_demo_reset_restores_fixed_knowledge_version(client):
    client.post(
        "/api/ops/knowledge",
        headers=OPS_HEADERS,
        json={
            "title": "平台退换货规则",
            "version": "2026-09",
            "section": "第 2.1 条",
            "content": "大多数商品支持签收后 10 天内无理由退货。",
            "keywords": ["退货", "10天"],
            "source_uri": "kb://after-sales/2026-09/第-2.1-条",
        },
    )

    response = client.post("/api/demo/reset")

    assert response.status_code == 200
    articles = client.get("/api/ops/knowledge", headers=OPS_HEADERS).json()
    assert len(articles) == 12
    assert {article["version"] for article in articles} == {"2026-07"}
    assert all(article["active"] is True for article in articles)
