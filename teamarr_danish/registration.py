"""Native Teamarr registry integration; no changes to other providers."""

from .http import MAX_BYTES, USER_AGENT, CachedHTTP, SourceError
from .provider import ALigaProvider, BetiniaProvider


def register():
    from teamarr.providers.base_client import BaseHTTPClient
    from teamarr.providers.registry import ProviderRegistry

    def factory(provider_class):
        class Transport(BaseHTTPClient):
            PROVIDER = provider_class.provider_name
            LOG_TAG = provider_class.provider_name.upper()

            def text(self, url):
                # Uses Teamarr's configured per-provider proxy/UA policy. Do not
                # propagate HTTPX exception strings (they contain full query URLs).
                try:
                    with self._get_client().stream("GET", url, follow_redirects=True) as response:
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > MAX_BYTES:
                                raise SourceError("Fixture response exceeds size limit")
                        return data.decode("utf-8-sig")
                except Exception:
                    raise SourceError("Official fixture request failed") from None

        transport = Transport(timeout=20, max_connections=4, headers={"User-Agent": USER_AGENT})
        return provider_class(
            client=provider_class.client_type(http=CachedHTTP(fetch=transport.text)),
            league_mapping_source=ProviderRegistry.get_league_mapping_source(),
        )

    for cls in (BetiniaProvider, ALigaProvider):
        ProviderRegistry.register(name=cls.provider_name, provider_class=cls,
                                  factory=lambda cls=cls: factory(cls), priority=60, enabled=True)
