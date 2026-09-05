"""Non-PowerShell smoke check for the configured real model provider."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib import request


DEMO_HEADERS = {"X-Demo-Session": "demo-linmu-session"}


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    headers = dict(DEMO_HEADERS)
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    with request.urlopen(
        request.Request(url, data=data, headers=headers, method=method),
        timeout=120,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def _send_message(api_base_url: str, conversation_id: str, content: str) -> list[dict]:
    url = f"{api_base_url}/api/conversations/{conversation_id}/messages"
    headers = {**DEMO_HEADERS, "Content-Type": "application/json; charset=utf-8"}
    data = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
    with request.urlopen(
        request.Request(url, data=data, headers=headers, method="POST"),
        timeout=120,
    ) as response:
        return [
            json.loads(line)
            for line in response.read().decode("utf-8").splitlines()
            if line.strip()
        ]


def verify_provider(api_base_url: str, *, reset_after: bool) -> dict[str, Any]:
    conversation = _request_json(
        f"{api_base_url}/api/conversations",
        method="POST",
    )
    conversation_id = conversation["id"]
    events = _send_message(api_base_url, conversation_id, "收到商品后几天可以退货？")
    events += _send_message(
        api_base_url,
        conversation_id,
        "订单 ORD-20260828-1042 的物流到哪里了？",
    )
    event_types = {event["type"] for event in events}
    tool_names = {
        event.get("payload", {}).get("tool_name")
        for event in events
        if event["type"] == "tool_completed"
    }

    required_events = {"message_delta", "response_completed"}
    required_tools = {"search_knowledge_base", "get_order", "get_shipping_status"}
    if "model_fallback" in event_types:
        raise RuntimeError("real model provider unexpectedly used fallback")
    if "error" in event_types:
        raise RuntimeError("real model provider returned an error event")
    if not required_events <= event_types:
        raise RuntimeError("real model provider did not complete streaming output")
    if not required_tools <= tool_names:
        raise RuntimeError("real model provider did not complete required tool calls")

    if reset_after:
        _request_json(f"{api_base_url}/api/demo/reset", method="POST")

    return {
        "passed": True,
        "conversation_id": conversation_id,
        "tool_names": sorted(name for name in tool_names if name),
        "reset_after": reset_after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--reset-after", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_provider(args.api_base_url.rstrip("/"), reset_after=args.reset_after)
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
