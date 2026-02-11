# celine/dt/core/router_discovery.py
"""
Autodiscover routers from domain routes/ packages.

Each module exports:
- router: APIRouter instance
- __prefix__: optional URL prefix (default "")
- __tags__: optional OpenAPI tags
"""
from __future__ import annotations

from enum import Enum
import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from celine.dt.core.domain.base import DTDomain

log = logging.getLogger(__name__)


@dataclass
class FoundRouter:
    name: str
    router: APIRouter
    prefix: str = ""
    tags: list[str | Enum] | None = None


def discover(domain: "DTDomain") -> list[FoundRouter]:
    """Find routers in domain's routes/ package."""

    # Get routes package path from domain's module
    # domain is at: celine.dt.domains.{pkg}.domain
    # routes at:    celine.dt.domains.{pkg}.routes
    mod = type(domain).__module__
    pkg = ".".join(mod.split(".")[:-1])
    routes_pkg = f"{pkg}.routes"

    try:
        routes_mod = importlib.import_module(routes_pkg)
    except ImportError:
        log.debug("No routes/ for %s", domain.name)
        return []

    if not hasattr(routes_mod, "__path__"):
        return []

    found = []
    for _, name, is_pkg in pkgutil.iter_modules(routes_mod.__path__):
        if name.startswith("_") or is_pkg:
            continue

        try:
            m = importlib.import_module(f"{routes_pkg}.{name}")
        except ImportError:
            log.warning("Failed to import %s.%s", routes_pkg, name)
            log.exception("Import error")
            continue

        router = getattr(m, "router", None)
        if not isinstance(router, APIRouter):
            continue

        found.append(
            FoundRouter(
                name=name,
                router=router,
                prefix=getattr(m, "__prefix__", ""),
                tags=getattr(m, "__tags__", None),
            )
        )
        log.info("Found router: %s.%s", routes_pkg, name)

    return found
