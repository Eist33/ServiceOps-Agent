"""Embedding provider contracts for stage 3.

The provider boundary is deliberately explicit: production uses the official
OpenAI SDK only when an operator configures a provider and API key, while the
deterministic fixture provider is available only outside production.  No
provider is contacted while importing this module.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from serviceops.config import Settings, get_settings
from serviceops.shared.errors import DomainError

EMBEDDING_DIMENSIONS = 1536
NORMALIZATION_VERSION = "l2-v1"


class EmbeddingProviderError(DomainError):
    """Safe provider failure that never includes request text or credentials."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(code, message, status_code)


@dataclass(frozen=True)
class EmbeddingBatch:
    provider: str
    model: str
    dimensions: int
    normalization_version: str
    vectors: tuple[tuple[float, ...], ...]
    input_tokens: int
    cost_micros: int


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimensions: int
    normalization_version: str

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Return one normalized vector per input text."""


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values or any(not math.isfinite(value) for value in values):
        raise EmbeddingProviderError(
            "EMBEDDING_VECTOR_INVALID",
            "embedding 返回了空向量或非有限数值",
        )
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        raise EmbeddingProviderError("EMBEDDING_VECTOR_INVALID", "embedding 向量不能是零向量")
    return tuple(value / norm for value in values)


def _validate_batch(
    *,
    provider: str,
    model: str,
    dimensions: int,
    normalization_version: str,
    texts: Sequence[str],
    vectors: Sequence[Sequence[float]],
    input_tokens: int,
    cost_micros: int,
) -> EmbeddingBatch:
    if not texts or len(texts) != len(vectors):
        raise EmbeddingProviderError(
            "EMBEDDING_RESPONSE_COUNT_MISMATCH",
            "embedding 返回数量与请求数量不一致",
        )
    if dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            "EMBEDDING_DIMENSION_UNSUPPORTED",
            f"当前知识向量索引只支持 {EMBEDDING_DIMENSIONS} 维",
        )
    normalized = tuple(_normalize(vector) for vector in vectors)
    if any(len(vector) != dimensions for vector in normalized):
        raise EmbeddingProviderError(
            "EMBEDDING_DIMENSION_MISMATCH",
            "embedding 返回维度与配置不一致",
        )
    return EmbeddingBatch(
        provider=provider,
        model=model,
        dimensions=dimensions,
        normalization_version=normalization_version,
        vectors=normalized,
        input_tokens=max(0, int(input_tokens)),
        cost_micros=max(0, int(cost_micros)),
    )


class FixtureEmbeddingProvider:
    """Offline hash vectors for deterministic tests and local Docker fixtures."""

    provider = "fixture"
    model = "fixture-hash-v1"
    dimensions = EMBEDDING_DIMENSIONS
    normalization_version = NORMALIZATION_VERSION

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingProviderError("EMBEDDING_INPUT_INVALID", "embedding 输入不能为空")
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            values = [
                ((seed[index % len(seed)] / 255.0) * 2.0) - 1.0
                for index in range(self.dimensions)
            ]
            vectors.append(_normalize(values))
        return _validate_batch(
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            normalization_version=self.normalization_version,
            texts=texts,
            vectors=vectors,
            input_tokens=sum(max(1, math.ceil(len(text) / 4)) for text in texts),
            cost_micros=0,
        )


class OpenAIEmbeddingProvider:
    """Official OpenAI embeddings adapter, instantiated only when configured."""

    provider = "openai"
    normalization_version = NORMALIZATION_VERSION

    def __init__(self, settings: Settings) -> None:
        if not settings.embedding_api_key:
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER_NOT_CONFIGURED",
                "embedding provider 未配置 API key，保持失败关闭",
            )
        if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
            raise EmbeddingProviderError(
                "EMBEDDING_DIMENSION_UNSUPPORTED",
                f"当前索引只支持 {EMBEDDING_DIMENSIONS} 维 embedding",
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER_UNAVAILABLE",
                "embedding provider SDK 不可用",
            ) from exc
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self._cost_per_1k_tokens = max(0.0, settings.embedding_cost_per_1k_tokens)
        self._client = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            timeout=settings.model_timeout_seconds,
            max_retries=0,
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingProviderError("EMBEDDING_INPUT_INVALID", "embedding 输入不能为空")
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=list(texts),
                dimensions=self.dimensions,
            )
            data = sorted(response.data, key=lambda item: item.index)
            vectors = [item.embedding for item in data]
            input_tokens = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER_REQUEST_FAILED",
                "embedding provider 请求失败，未将结果用于检索",
            ) from exc
        cost_micros = round(input_tokens / 1000 * self._cost_per_1k_tokens * 1_000_000)
        return _validate_batch(
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            normalization_version=self.normalization_version,
            texts=texts,
            vectors=vectors,
            input_tokens=input_tokens,
            cost_micros=cost_micros,
        )


def build_embedding_provider(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> EmbeddingProvider:
    current = settings or get_settings()
    provider_name = (name or current.embedding_provider).strip().lower()
    if provider_name in {"", "not_configured", "none"}:
        raise EmbeddingProviderError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "embedding provider 未配置，保持 lexical_v1 回退",
        )
    if provider_name == "fixture":
        if current.app_env.strip().lower() == "production":
            raise EmbeddingProviderError(
                "EMBEDDING_FIXTURE_FORBIDDEN",
                "生产环境不允许使用 fixture embedding",
            )
        return FixtureEmbeddingProvider()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider(current)
    raise EmbeddingProviderError(
        "EMBEDDING_PROVIDER_UNSUPPORTED",
        "未识别的 embedding provider，保持失败关闭",
    )
