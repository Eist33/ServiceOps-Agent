from dataclasses import dataclass

from serviceops.integrations.commerce.contracts import (
    CommerceProvider,
    IdentityProvider,
    IntegrationStatus,
    IntegrationStatusReader,
    OrderReader,
    ShippingReader,
)
from serviceops.integrations.commerce.stubs import UnconfiguredCommercePlatform


@dataclass(frozen=True, slots=True)
class CommerceAdapterBundle:
    provider: CommerceProvider
    status_reader: IntegrationStatusReader
    identity_provider: IdentityProvider
    order_reader: OrderReader
    shipping_reader: ShippingReader

    def __post_init__(self) -> None:
        components = (
            self.status_reader,
            self.identity_provider,
            self.order_reader,
            self.shipping_reader,
        )
        if any(component.provider != self.provider for component in components):
            raise ValueError("Commerce adapter components must use the same provider")


class CommerceAdapterRegistry:
    def __init__(self, bundles: tuple[CommerceAdapterBundle, ...]) -> None:
        self._bundles: dict[CommerceProvider, CommerceAdapterBundle] = {}
        for bundle in bundles:
            if bundle.provider in self._bundles:
                raise ValueError(f"Duplicate commerce adapter: {bundle.provider.value}")
            self._bundles[bundle.provider] = bundle

    def get(self, provider: CommerceProvider) -> CommerceAdapterBundle:
        try:
            return self._bundles[provider]
        except KeyError as exc:
            raise LookupError(f"Commerce adapter is not registered: {provider.value}") from exc

    def statuses(self) -> tuple[IntegrationStatus, ...]:
        return tuple(
            self._status_for(self._bundles[provider])
            for provider in sorted(self._bundles, key=lambda item: item.value)
        )

    @staticmethod
    def _status_for(bundle: CommerceAdapterBundle) -> IntegrationStatus:
        status = bundle.status_reader.integration_status()
        if status.provider != bundle.provider:
            raise ValueError("Commerce adapter status provider does not match registry key")
        return status


def build_default_commerce_registry() -> CommerceAdapterRegistry:
    bundles: list[CommerceAdapterBundle] = []
    for provider in CommerceProvider:
        stub = UnconfiguredCommercePlatform(provider)
        bundles.append(
            CommerceAdapterBundle(
                provider=provider,
                status_reader=stub,
                identity_provider=stub,
                order_reader=stub,
                shipping_reader=stub,
            )
        )
    return CommerceAdapterRegistry(tuple(bundles))
