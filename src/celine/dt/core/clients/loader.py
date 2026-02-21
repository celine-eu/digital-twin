# celine/dt/core/clients/loader.py
"""
Client loader – reads config/clients.yaml and registers live client instances.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Iterable

from celine.dt.core.config import settings
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.loader import import_attr, load_yaml_files, substitute_env_vars
from celine.sdk.auth.provider import TokenProvider
from celine.sdk.auth import OidcClientCredentialsProvider

logger = logging.getLogger(__name__)



def load_and_register_clients(
    *,
    patterns: Iterable[str],
    registry: ClientsRegistry,
    token_provider: TokenProvider | None = None,
) -> None:
    """Load client definitions from YAML and register live instances.

    Expected YAML::

        clients:
          dataset_api:
            class: celine.dt.core.clients.dataset_api:DatasetSqlApiClient
            config:
              base_url: "${DATASET_API_URL:-http://localhost:8001}"
              timeout: 30.0

    If a client constructor accepts ``token_provider``, the given
    provider is injected automatically.
    """
    yamls = load_yaml_files(patterns)
    if not yamls:
        logger.debug("No client config files matched: %s", list(patterns))
        return

    for data in yamls:
        for name, spec in (data.get("clients") or {}).items():
            class_path = spec.get("class")
            scope = spec.get("scope")
            raw_config = substitute_env_vars(spec.get("config", {}))

            cls = import_attr(class_path)
            kwargs = dict(raw_config)

            sig = inspect.signature(cls.__init__)
            if "token_provider" in sig.parameters:
                kwargs["token_provider"] = token_provider
                if scope and isinstance(token_provider, OidcClientCredentialsProvider):
                    if settings.oidc.client_id and settings.oidc.client_secret:
                        kwargs["token_provider"] = OidcClientCredentialsProvider(
                            base_url=settings.oidc.base_url,
                            client_id=settings.oidc.client_id,
                            client_secret=settings.oidc.client_secret,
                            scope=scope,
                            timeout=settings.oidc.timeout,
                        )
                    else:
                        logger.warning(f"Cannot initialize OIDC token provider for aud={scope}: missing client_id / client_secret")

            registry.register(name, cls(**kwargs))
    logger.info("Registered %d client(s): %s", len(registry.list()), registry.list())
