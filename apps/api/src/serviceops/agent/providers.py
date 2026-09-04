from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from agents.models.openai_provider import OpenAIProvider
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from serviceops.config import Settings


class ModelConfigurationError(ValueError):
    pass


class LocalModelRateLimitError(RuntimeError):
    pass


class ModelCircuitOpenError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelProviderConfiguration:
    provider: str
    api_style: str
    base_url: str
    model_name: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 30.0
    max_retries: int = 1
    requests_per_minute: int = 30
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 60.0
    fallback_enabled: bool = True
    max_turns: int = 8

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelProviderConfiguration:
        if settings.agent_mode.strip().lower() == "openai":
            return cls(
                provider="openai",
                api_style="responses",
                base_url="https://api.openai.com/v1",
                model_name=settings.openai_model,
                api_key=settings.openai_api_key,
                timeout_seconds=settings.model_timeout_seconds,
                max_retries=settings.model_max_retries,
                requests_per_minute=settings.model_requests_per_minute,
                circuit_failure_threshold=settings.model_circuit_failure_threshold,
                circuit_cooldown_seconds=settings.model_circuit_cooldown_seconds,
                fallback_enabled=settings.model_fallback_enabled,
                max_turns=settings.model_max_turns,
            ).validated()
        return cls(
            provider=settings.model_provider,
            api_style=settings.model_api_style,
            base_url=settings.model_base_url,
            model_name=settings.model_name,
            api_key=settings.model_api_key or settings.deepseek_api_key,
            timeout_seconds=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
            requests_per_minute=settings.model_requests_per_minute,
            circuit_failure_threshold=settings.model_circuit_failure_threshold,
            circuit_cooldown_seconds=settings.model_circuit_cooldown_seconds,
            fallback_enabled=settings.model_fallback_enabled,
            max_turns=settings.model_max_turns,
        ).validated()

    def validated(self) -> ModelProviderConfiguration:
        provider = self.provider.strip().lower()
        api_style = self.api_style.strip().lower()
        base_url = self.base_url.strip().rstrip("/")
        model_name = self.model_name.strip()
        if provider not in {"deepseek", "openai", "openai_compatible"}:
            raise ModelConfigurationError("不支持的模型提供方")
        if api_style not in {"responses", "chat_completions"}:
            raise ModelConfigurationError("不支持的模型 API 风格")
        parsed = urlparse(base_url)
        localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or (parsed.scheme != "https" and not localhost):
            raise ModelConfigurationError("模型地址必须使用 HTTPS")
        if provider == "deepseek" and parsed.hostname != "api.deepseek.com":
            raise ModelConfigurationError("DeepSeek 必须使用官方 API 地址")
        if not model_name:
            raise ModelConfigurationError("模型名称不能为空")
        numeric_values = {
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requests_per_minute": self.requests_per_minute,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_cooldown_seconds": self.circuit_cooldown_seconds,
            "max_turns": self.max_turns,
        }
        if any(value <= 0 for key, value in numeric_values.items() if key != "max_retries"):
            raise ModelConfigurationError("模型可靠性参数必须大于零")
        if self.max_retries < 0 or self.max_retries > 3:
            raise ModelConfigurationError("模型重试次数必须在 0 到 3 之间")
        return ModelProviderConfiguration(
            provider=provider,
            api_style=api_style,
            base_url=base_url,
            model_name=model_name,
            api_key=self.api_key,
            timeout_seconds=float(self.timeout_seconds),
            max_retries=int(self.max_retries),
            requests_per_minute=int(self.requests_per_minute),
            circuit_failure_threshold=int(self.circuit_failure_threshold),
            circuit_cooldown_seconds=float(self.circuit_cooldown_seconds),
            fallback_enabled=bool(self.fallback_enabled),
            max_turns=int(self.max_turns),
        )

    @property
    def identity(self) -> tuple[Any, ...]:
        return (
            self.provider,
            self.base_url,
            self.model_name,
            self.requests_per_minute,
            self.circuit_failure_threshold,
            self.circuit_cooldown_seconds,
        )


def build_sdk_model_provider(configuration: ModelProviderConfiguration) -> OpenAIProvider:
    if not configuration.api_key:
        raise ModelConfigurationError("模型 API Key 尚未配置")
    client = AsyncOpenAI(
        api_key=configuration.api_key,
        base_url=configuration.base_url,
        timeout=configuration.timeout_seconds,
        max_retries=configuration.max_retries,
    )
    return OpenAIProvider(
        openai_client=client,
        use_responses=configuration.api_style == "responses",
        strict_feature_validation=True,
    )


_provider_registry: dict[tuple[Any, ...], OpenAIProvider] = {}
_provider_registry_lock = Lock()


def sdk_model_provider_for(
    configuration: ModelProviderConfiguration,
) -> OpenAIProvider:
    if not configuration.api_key:
        raise ModelConfigurationError("模型 API Key 尚未配置")
    key_fingerprint = hashlib.sha256(configuration.api_key.encode()).hexdigest()[:16]
    registry_key = (*configuration.identity, configuration.api_style, key_fingerprint)
    with _provider_registry_lock:
        provider = _provider_registry.get(registry_key)
        if provider is None:
            provider = build_sdk_model_provider(configuration)
            _provider_registry[registry_key] = provider
        return provider


class ModelReliabilityGuard:
    def __init__(
        self,
        *,
        requests_per_minute: int,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self._requests: deque[float] = deque()
        self._consecutive_failures = 0
        self._opened_until = 0.0
        self._lock = Lock()

    def before_request(self) -> None:
        now = self.clock()
        with self._lock:
            if self._opened_until > now:
                raise ModelCircuitOpenError("模型熔断器处于冷却期")
            if self._opened_until:
                self._opened_until = 0.0
                self._consecutive_failures = 0
            cutoff = now - 60.0
            while self._requests and self._requests[0] <= cutoff:
                self._requests.popleft()
            if len(self._requests) >= self.requests_per_minute:
                raise LocalModelRateLimitError("本地模型请求速率已达到上限")
            self._requests.append(now)

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_until = 0.0

    def record_failure(self, error: BaseException) -> None:
        if not is_retryable_provider_error(error):
            return
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._opened_until = self.clock() + self.cooldown_seconds


_guard_registry: dict[tuple[Any, ...], ModelReliabilityGuard] = {}
_guard_registry_lock = Lock()


def reliability_guard_for(
    configuration: ModelProviderConfiguration,
) -> ModelReliabilityGuard:
    with _guard_registry_lock:
        guard = _guard_registry.get(configuration.identity)
        if guard is None:
            guard = ModelReliabilityGuard(
                requests_per_minute=configuration.requests_per_minute,
                failure_threshold=configuration.circuit_failure_threshold,
                cooldown_seconds=configuration.circuit_cooldown_seconds,
            )
            _guard_registry[configuration.identity] = guard
        return guard


def classify_model_error(error: BaseException) -> str:
    if isinstance(error, ModelConfigurationError):
        return "MODEL_CONFIGURATION_ERROR"
    if isinstance(error, LocalModelRateLimitError):
        return "MODEL_LOCAL_RATE_LIMIT"
    if isinstance(error, ModelCircuitOpenError):
        return "MODEL_CIRCUIT_OPEN"
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, APITimeoutError)):
        return "MODEL_TIMEOUT"
    if isinstance(error, RateLimitError):
        return "MODEL_PROVIDER_RATE_LIMIT"
    if isinstance(error, APIConnectionError):
        return "MODEL_CONNECTION_ERROR"
    if isinstance(error, APIStatusError):
        return f"MODEL_HTTP_{error.status_code}"
    return "MODEL_RUNTIME_ERROR"


def is_retryable_provider_error(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(error, RateLimitError):
        return True
    return isinstance(error, APIStatusError) and error.status_code >= 500
