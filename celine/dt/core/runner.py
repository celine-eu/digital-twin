
from __future__ import annotations
from typing import Any
from celine.dt.core.context import RunContext
from celine.dt.core.registry import DTRegistry

class DTAppRunner:
    async def run(
        self,
        *,
        registry: DTRegistry,
        app_key: str,
        payload: Any,
        context: RunContext,
    ) -> Any:
        desc = registry.apps.get(app_key)
        if desc is None:
            raise KeyError(f"Unknown app '{app_key}'")

        inputs = (
            desc.input_mapper.map(payload)
            if desc.input_mapper
            else payload
        )

        result = await desc.app.run(inputs, context)

        return (
            desc.output_mapper.map(result)
            if desc.output_mapper
            else result
        )
