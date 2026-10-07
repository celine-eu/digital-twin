# celine/dt/domains/energy_community/base.py
"""
Energy Community domain – base class for community-level Digital Twins.

This provides the shared structure for energy community DTs across
regulatory regimes. Locale variants (IT, DE, etc.) inherit from this
and override incentive models, data sources, and regulatory logic.

Route surface::

    /communities/{community_id}/values/...
    /communities/{community_id}/simulations   (501 until a subclass lists some)
    /communities/{community_id}/energy-balance
    /communities/{community_id}/summary       (501 until a subclass implements it)
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from fastapi import APIRouter, HTTPException, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.simulation import DTSimulation
from celine.dt.contracts.subscription import SubscriptionSpec
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.context import RunContext
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.values.executor import FetchRefused
from celine.dt.domains.energy_community.boundary_fetchers import boundary_value_specs
from celine.dt.domains.energy_community.manager_fetchers import (
    MANAGER_FETCHER_IDS,
    MANAGER_SCOPE,
)

logger = logging.getLogger(__name__)

#: The groups inside a community's organisation that run it (celine-policies
#: provisioning): its members are filed in ``viewers``.
MANAGING_GROUPS = frozenset({"admins", "managers"})
COMMUNITY_NOT_MANAGED = "community_not_managed"
MANAGER_SCOPE_MISSING = "manager_scope_missing"


class EnergyCommunityDomain(DTDomain):
    """Base energy community domain.

    Subclass and override for locale-specific behaviour. At minimum,
    override ``get_value_specs`` to provide the right data queries,
    extending ``super().get_value_specs()`` to keep the boundary fetchers.
    ``get_simulations`` may add simulations; none exists yet.
    """

    domain_type: ClassVar[str] = "energy-community"
    route_prefix: ClassVar[str] = "/communities"
    entity_id_param: ClassVar[str] = "community_id"

    # -- values (override in locale subclass) ----------------------------

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        """Community value fetchers every locale shares.

        The reference-boundary fetchers (``boundary_at_point``,
        ``boundary_shape``; ADR-0003) live here so each locale variant inherits
        them. A subclass extends this list with ``super().get_value_specs()``
        rather than replacing it.
        """
        return boundary_value_specs()

    # -- who may read the manager fetchers ------------------------------

    async def check_fetch(
        self, spec: ValueFetcherSpec, payload: dict[str, Any], ctx: Any
    ) -> None:
        """REQ-1510: a manager fetcher is read only by those who run the community.

        A service holding ``MANAGER_SCOPE``, the ``platform-admin`` realm role, or a
        person in ``admins`` or ``managers`` of the organisation the URL names. Every
        other fetcher of the domain is open to any authenticated caller (REQ-1513):
        flexibility-api and onboarding read them with their own service tokens.
        Organisation presence decides whether the caller is a person, as in the grid
        domain: a client-credentials token carries none.
        """
        if spec.id.split(".", 1)[-1] not in MANAGER_FETCHER_IDS:
            return
        caller = getattr(ctx, "user", None)
        if caller is not None and caller.is_platform_admin:
            return
        if caller is None or caller.organizations or not caller.is_service_account:
            community = ctx.entity.id if ctx.entity else None
            if caller is None or not community or not (
                MANAGING_GROUPS & caller.grants.in_org(community)
            ):
                raise FetchRefused(
                    COMMUNITY_NOT_MANAGED,
                    "Only the community's admins or managers read its manager values",
                )
            return
        if not caller.has_scope(MANAGER_SCOPE):
            raise FetchRefused(
                MANAGER_SCOPE_MISSING,
                f"A service needs {MANAGER_SCOPE} to read a community's manager values",
            )

    # -- lifecycle -------------------------------------------------------

    async def on_startup(self) -> None:
        logger.info(
            "EnergyCommunityDomain '%s' starting (type=%s, version=%s)",
            self.name,
            self.domain_type,
            self.version,
        )

    async def on_shutdown(self) -> None:
        logger.info("EnergyCommunityDomain '%s' shutting down", self.name)
