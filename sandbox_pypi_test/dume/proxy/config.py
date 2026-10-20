import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProxyConfig:
    upstream_base_url: str = "http://localhost:11434/v1"
    upstream_api_key: str = ""
    default_entity_id: str = "DemoUser-01"
    enabled: bool = True

    @classmethod
    def load_from_env(cls) -> "ProxyConfig":
        base_url = os.environ.get("UPSTREAM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        api_key = os.environ.get("UPSTREAM_API_KEY", "")
        entity_id = os.environ.get("DEFAULT_ENTITY_ID", "DemoUser-01")
        return cls(
            upstream_base_url=base_url,
            upstream_api_key=api_key,
            default_entity_id=entity_id
        )

    def to_dict(self) -> dict:
        # Mask API key for security in status endpoints
        masked_key = f"{self.upstream_api_key[:4]}..." if len(self.upstream_api_key) > 6 else ("***" if self.upstream_api_key else "")
        return {
            "upstream_base_url": self.upstream_base_url,
            "upstream_api_key_masked": masked_key,
            "default_entity_id": self.default_entity_id,
            "enabled": self.enabled
        }


# Global Proxy Config Instance
_proxy_config = ProxyConfig.load_from_env()


def get_proxy_config() -> ProxyConfig:
    return _proxy_config


def set_proxy_config(
    upstream_base_url: Optional[str] = None,
    upstream_api_key: Optional[str] = None,
    default_entity_id: Optional[str] = None
) -> ProxyConfig:
    global _proxy_config
    if upstream_base_url is not None:
        _proxy_config.upstream_base_url = upstream_base_url.rstrip("/")
    if upstream_api_key is not None:
        _proxy_config.upstream_api_key = upstream_api_key
    if default_entity_id is not None:
        _proxy_config.default_entity_id = default_entity_id
    return _proxy_config
