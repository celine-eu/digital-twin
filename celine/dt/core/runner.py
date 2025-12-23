from __future__ import annotations
from ast import TypeVar
from typing import Any, Mapping, cast
from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext
from celine.dt.core.registry import DTRegistry
from typing import get_type_hints, Type
import inspect


def get_config_type(app: DTApp) -> Type[Any]:
    """
    Extract the type of the `config` parameter from app.run().
    """
    sig = inspect.signature(app.run)
    params = list(sig.parameters.values())

    if len(params) < 2:
        raise TypeError(f"{app.__class__.__name__}.run must accept (config, context)")

    config_param = params[1]

    hints = get_type_hints(app.run)
    config_type = hints.get(config_param.name)

    if config_type is None:
        raise TypeError(f"{app.__class__.__name__}.run must type-annotate `config`")

    return config_type


def resolve_config(
    *,
    app: DTApp,
    defaults: Mapping[str, Any],
    run_params: Mapping[str, Any] | None,
) -> Any:
    merged: dict[str, Any] = {}

    merged.update(defaults)
    if run_params:
        merged.update(run_params)

    config_type = get_config_type(app)

    # instantiate
    return config_type(**merged)


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
            run_params=payload,
        )

        return await desc.app.run(config, context)
