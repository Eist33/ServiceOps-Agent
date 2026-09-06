"""Optional stage-4 reranker boundary with an offline deterministic provider."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from serviceops.config import Settings, get_settings
from serviceops.shared.errors import DomainError


class RerankerProviderError(DomainError):
    """Safe reranker failure; callers must keep the RRF result or refuse."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(code, message, status_code)


@dataclass(frozen=True)
class RerankBatch:
    provider: str
    model: str
    version: str
    scores: tuple[tuple[str, float], ...]
    input_tokens: int
    cost_micros: int


class RerankerProvider(Protocol):
    provider: str
    model: str
    version: str
    timeout_ms: int

    def rerank(self, query: str, candidates: Sequence[dict]) -> RerankBatch:
        """Score only already authorized retrieval candidates."""


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.lower()))


class FixtureReranker:
    """Offline lexical cross-encoder stand-in; never makes a network call."""

    provider = "fixture"
    model = "fixture-cross-encoder-v1"
    version = "reranker_v1"

    def __init__(self, timeout_ms: int = 250) -> None:
        self.timeout_ms = timeout_ms

    def rerank(self, query: str, candidates: Sequence[dict]) -> RerankBatch:
        if not query.strip():
            raise RerankerProviderError("RERANKER_QUERY_INVALID", "重排查询不能为空")
        if not candidates:
            return RerankBatch(
                provider=self.provider,
                model=self.model,
                version=self.version,
                scores=(),
                input_tokens=max(1, len(query) // 4),
                cost_micros=0,
            )
        query_terms = _terms(query)
        scores: list[tuple[str, float]] = []
        for candidate in candidates:
            chunk_id = str(candidate.get("chunk_id", ""))
            content = str(candidate.get("content", ""))
            if not chunk_id or not content:
                raise RerankerProviderError(
                    "RERANKER_CANDIDATE_INVALID",
                    "重排候选缺少受控标识或内容",
                )
            terms = _terms(content)
            overlap = len(query_terms & terms) / max(1, len(query_terms))
            scores.append((chunk_id, round(min(1.0, overlap), 6)))
        return RerankBatch(
            provider=self.provider,
            model=self.model,
            version=self.version,
            scores=tuple(scores),
            input_tokens=max(1, (len(query) + sum(len(str(item.get("content", ""))) for item in candidates)) // 4),
            cost_micros=0,
        )


def build_reranker(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> RerankerProvider:
    current = settings or get_settings()
    provider_name = (name or current.reranker_provider).strip().lower()
    if provider_name in {"", "not_configured", "none"}:
        raise RerankerProviderError(
            "RERANKER_PROVIDER_NOT_CONFIGURED",
            "重排 provider 未配置，保持 RRF 结果",
        )
    if provider_name == "fixture":
        if current.app_env.strip().lower() == "production":
            raise RerankerProviderError(
                "RERANKER_FIXTURE_FORBIDDEN",
                "生产环境不允许使用 fixture 重排 provider",
            )
        return FixtureReranker(timeout_ms=max(1, current.reranker_timeout_ms))
    raise RerankerProviderError(
        "RERANKER_PROVIDER_UNSUPPORTED",
        "未识别的重排 provider，保持 RRF 结果",
    )


def apply_optional_reranker(
    report: dict,
    query: str,
    *,
    provider: RerankerProvider | None,
    timeout_ms: int | None = None,
) -> dict:
    """Apply reranking without weakening refusal or losing the RRF citations."""

    results = list(report.get("results") or [])
    report.setdefault("reranker_status", "NOT_CONFIGURED")
    report.setdefault("reranker_fallback", False)
    report.setdefault("reranker_fallback_reason", None)
    report.setdefault("reranker_input_tokens", 0)
    report.setdefault("reranker_cost_micros", 0)
    if provider is None or not results:
        return report

    try:
        started = monotonic()
        batch = provider.rerank(query, results)
        elapsed_ms = int((monotonic() - started) * 1000)
        effective_timeout = timeout_ms or getattr(provider, "timeout_ms", 250)
        if elapsed_ms > effective_timeout:
            raise RerankerProviderError(
                "RERANKER_TIMEOUT",
                "重排超过延迟预算，回退到 RRF 结果",
            )
        score_by_id = dict(batch.scores)
        if set(score_by_id) != {str(item.get("chunk_id", "")) for item in results}:
            raise RerankerProviderError(
                "RERANKER_RESPONSE_MISMATCH",
                "重排返回候选与授权候选不一致",
            )
        for item in results:
            rerank_score = float(score_by_id[str(item["chunk_id"])])
            rrf_score = float(item.get("hybrid_score") or item.get("relevance") or 0.0)
            normalized_rrf = min(1.0, max(0.0, rrf_score * 60.0))
            item["rerank_score"] = round(rerank_score, 6)
            item["final_score"] = round(0.8 * rerank_score + 0.2 * normalized_rrf, 6)
            item["decision"] = "RERANKED_CANDIDATE"
        results.sort(key=lambda item: item["final_score"], reverse=True)
        for index, item in enumerate(results):
            item["selected"] = index == 0 and item["final_score"] >= 0.5
        report["results"] = results
        report["score"] = results[0]["final_score"] if results else 0.0
        report["confident"] = bool(report.get("confident") and results and results[0]["selected"])
        report["reranker_status"] = "READY"
        report["reranker_provider"] = batch.provider
        report["reranker_model"] = batch.model
        report["reranker_version"] = batch.version
        report["reranker_input_tokens"] = batch.input_tokens
        report["reranker_cost_micros"] = batch.cost_micros
        return report
    except RerankerProviderError as error:
        for item in results:
            item["rerank_score"] = None
            item["final_score"] = item.get("hybrid_score") or item.get("relevance") or 0.0
            item["decision"] = "RRF_FALLBACK"
        report["results"] = results
        report["reranker_status"] = "FALLBACK"
        report["reranker_fallback"] = True
        report["reranker_fallback_reason"] = error.code
        report["reranker_provider"] = getattr(provider, "provider", None)
        report["reranker_model"] = getattr(provider, "model", None)
        report["reranker_version"] = getattr(provider, "version", None)
        return report
