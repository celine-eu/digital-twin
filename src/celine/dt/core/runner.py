from __future__ import annotations
from typing import Any, Mapping
from celine.dt.core.context import RunContext
from celine.dt.core.registry import DTRegistry


def resolve_config(app, defaults, payload):
    merged = {}
    merged.update(defaults)
    if payload:
        merged.update(payload)

    if getattr(app, "input_mapper", None):
        return app.input_mapper.map(merged)

    return app.config_type(**merged)


class DTAppRunner:
    async def run(
        self,
        *,
        registry: DTRegistry,
        app_key: str,
        payload: Mapping[str, Any] | None,
        context: RunContext,
    ) -> Any:
        desc = registry.apps.get(app_key)
        if not desc:
            raise KeyError(app_key)

        config = resolve_config(
            app=desc.app,
            defaults=desc.defaults,
            payload=payload,
        )

        result = await desc.app.run(config, context)

        if getattr(desc.app, "output_mapper", None):
            return desc.app.output_mapper.map(result)

        return result
