# celine/dt/core/broker/scanner.py
"""
Package scanner for @on_event plain functions.

Discovers all module-level functions decorated with @on_event by walking
Python packages. Used by SubscriptionManager to auto-register handlers
without explicit module lists.

Default behaviour
-----------------
Given a registered domain with import_path ``celine.dt.domains.participant.domain:domain``,
the scanner derives the base package ``celine.dt.domains.participant`` and walks
every submodule under it. Any function with ``_dt_route`` set is collected.

Extra packages can be added explicitly for cross-domain handlers (e.g. pipeline
reactors that don't belong to a specific domain package).

Usage in main.py
----------------
    from celine.dt.core.broker.scanner import scan_handlers

    specs = scan_handlers(
        domain_registry=domain_registry,
        extra_packages=["celine.dt.reactions"],  # optional
    )
    subscription_manager = SubscriptionManager(
        ...
        handler_specs=specs,
    )
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import pkgutil
from typing import cast

from celine.dt.contracts.subscription import EventHandler, RouteDef, SubscriptionSpec
from celine.dt.core.domain.registry import DomainRegistry

logger = logging.getLogger(__name__)


def _base_package(import_path: str) -> str:
    """Derive the base package from a domain import_path.

    ``celine.dt.domains.participant.domain:domain``
    → ``celine.dt.domains.participant``
    """
    module_path = import_path.split(":")[0]          # strip ':attr'
    parts = module_path.rsplit(".", 1)                # drop last segment (the module file)
    return parts[0] if len(parts) > 1 else module_path


def _walk_package(package_name: str) -> list[object]:
    """Import and return all modules in a package, recursively."""
    modules: list[object] = []

    try:
        package = importlib.import_module(package_name)
    except ImportError:
        logger.debug("Scanner: package '%s' not importable, skipping", package_name)
        return modules

    modules.append(package)

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        # plain module, not a package — nothing to walk
        return modules

    for _finder, name, _ispkg in pkgutil.walk_packages(
        path=package_path,
        prefix=package_name + ".",
        onerror=lambda n: logger.debug("Scanner: error walking '%s'", n),
    ):
        try:
            mod = importlib.import_module(name)
            modules.append(mod)
        except Exception:
            logger.debug("Scanner: could not import '%s', skipping", name)

    return modules


def _collect_from_module(module: object) -> list[RouteDef]:
    """Return all RouteDef-tagged plain functions in a module."""
    routes: list[RouteDef] = []
    for _name, fn in inspect.getmembers(module, predicate=inspect.isfunction):
        route: RouteDef | None = getattr(fn, "_dt_route", None)
        if route is None:
            continue
        handler = cast(EventHandler, fn)
        routes.append(route.with_handler(handler))
        logger.debug(
            "Scanner: found @on_event '%s' in %s",
            route.event_type,
            getattr(module, "__name__", repr(module)),
        )
    return routes


def scan_handlers(
    *,
    domain_registry: DomainRegistry,
    extra_packages: list[str] | None = None,
) -> list[SubscriptionSpec]:
    """Scan for @on_event plain functions and return SubscriptionSpecs.

    Scans:
    - The base package of every registered domain (derived from import_path).
    - Any explicitly listed extra_packages.

    Args:
        domain_registry: The populated DomainRegistry (provides import paths).
        extra_packages:  Additional package names to scan, e.g.
                         ``["celine.dt.reactions"]``.

    Returns:
        List of SubscriptionSpec ready to pass to SubscriptionManager.
    """
    from collections import OrderedDict
    from celine.dt.core.domain.config import DomainSpec

    packages: list[str] = []

    # Derive base packages from registered domains
    for domain in domain_registry:
        import_path: str | None = getattr(domain, "_import_path", None)
        if import_path:
            pkg = _base_package(import_path)
            if pkg not in packages:
                packages.append(pkg)
                logger.debug("Scanner: will scan domain package '%s'", pkg)

    # Add explicit extras
    for pkg in (extra_packages or []):
        if pkg not in packages:
            packages.append(pkg)
            logger.debug("Scanner: will scan extra package '%s'", pkg)

    if not packages:
        logger.debug("Scanner: no packages to scan")
        return []

    # Collect all routes from all modules in all packages
    all_routes: list[RouteDef] = []
    seen_modules: set[str] = set()

    for pkg in packages:
        for module in _walk_package(pkg):
            mod_name = getattr(module, "__name__", "")
            if mod_name in seen_modules:
                continue
            seen_modules.add(mod_name)
            all_routes.extend(_collect_from_module(module))

    if not all_routes:
        logger.debug("Scanner: no @on_event plain functions found")
        return []

    logger.info(
        "Scanner: found %d @on_event route(s) across %d module(s)",
        len(all_routes),
        len(seen_modules),
    )

    return _routes_to_specs(all_routes)


def _routes_to_specs(routes: list[RouteDef]) -> list[SubscriptionSpec]:
    from collections import OrderedDict

    grouped: OrderedDict[tuple[str | None, tuple[str, ...], str], RouteDef] = OrderedDict()
    for r in routes:
        key = (r.broker, tuple(r.topics), r.event_type)
        if key not in grouped:
            grouped[key] = r
        else:
            existing = grouped[key]
            grouped[key] = RouteDef(
                event_type=existing.event_type,
                topics=existing.topics,
                broker=existing.broker,
                enabled=existing.enabled and r.enabled,
                metadata={**existing.metadata, **r.metadata},
                handlers=[*existing.handlers, *r.handlers],
            )
    return [
        SubscriptionSpec(
            topics=r.topics,
            handlers=r.handlers,
            enabled=r.enabled,
            metadata={"event_type": r.event_type, "broker": r.broker, **(r.metadata or {})},
        )
        for r in grouped.values()
    ]