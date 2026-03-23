# celine/dt/core/ontology/service.py
"""
OntologyService: fetches raw rows via ValuesService, maps them to JSON-LD
nodes via the CELINE mapper, and wraps the result in a JSON-LD document.

Multiple fetcher bindings within a single OntologySpec are executed in
parallel; their node lists are merged before document assembly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from celine.mapper.graph import CelineGraphBuilder
from celine.mapper.output_mapper import OutputMapper

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.ontology import OntologyFetcherBinding, OntologySpec
from celine.dt.core.values.service import ValuesService

if TYPE_CHECKING:
    from celine.dt.api.context import Ctx


logger = logging.getLogger(__name__)


class OntologyService:
    """Fetch-map-wrap pipeline for ontology concept views."""

    def __init__(self, values_service: ValuesService) -> None:
        self._values_service = values_service

    async def fetch_as_jsonld(
        self,
        spec: OntologySpec,
        entity: EntityInfo,
        payload: dict[str, Any],
        *,
        limit: int | None = None,
        offset: int | None = None,
        ctx: Ctx | None,
    ) -> dict[str, Any]:
        """Return a JSON-LD document for the given ontology spec.

        All bindings are fetched concurrently; their nodes are merged into
        one ``@graph`` and wrapped with the CELINE ``@context``.
        """
        tasks = [
            self._fetch_binding(binding, entity, payload, limit=limit, offset=offset, ctx=ctx)
            for binding in spec.bindings
        ]
        node_lists: list[list[dict[str, Any]]] = await asyncio.gather(*tasks)

        all_nodes = [node for nodes in node_lists for node in nodes]

        builder = CelineGraphBuilder()
        return builder.build_document(all_nodes)

    async def _fetch_binding(
        self,
        binding: OntologyFetcherBinding,
        entity: EntityInfo,
        payload: dict[str, Any],
        *,
        limit: int | None,
        offset: int | None,
        ctx: Ctx | None,
    ) -> list[dict[str, Any]]:
        ns_fetcher_id = f"{entity.domain_name}.{binding.fetcher_id}"

        result = await self._values_service.fetch(
            fetcher_id=ns_fetcher_id,
            entity=entity,
            payload=payload,
            limit=limit,
            offset=offset,
            ctx=ctx,
        )

        context = {
            var_name: entity.metadata[meta_key]
            for meta_key, var_name in binding.context_vars.items()
            if meta_key in entity.metadata and entity.metadata[meta_key] is not None
        }

        mapper = OutputMapper.from_yaml_path(binding.mapper_spec_path, context=context)

        try:
            return mapper.map_many(result.items)
        except Exception:
            logger.exception(
                "Ontology mapping failed for fetcher '%s' (spec binding %s)",
                ns_fetcher_id,
                binding.mapper_spec_path.name,
            )
            raise
