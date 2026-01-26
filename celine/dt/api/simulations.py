# celine/dt/api/simulations.py
"""FastAPI router for simulation endpoints.

This router is designed around explicit separation of:
- Scenario (expensive, cacheable)
- Parameters (cheap, per-run)
- Run (immutable execution, addressed by run_id)

Primary objective:
- Results and artifacts must be reachable via API over a simulation run ID.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from celine.dt.core.dt import DT

logger = logging.getLogger(__name__)
router = APIRouter()


class BuildScenarioRequest(BaseModel):
    config: dict[str, Any]
    ttl_hours: int = 24
    reuse_existing: bool = True


class BuildScenarioResponse(BaseModel):
    scenario_id: str
    simulation_key: str
    created_at: str
    expires_at: str
    config_hash: str
    baseline_metrics: dict[str, Any] = {}


class RunSimulationRequest(BaseModel):
    scenario_id: str
    parameters: dict[str, Any] = {}
    include_result: bool = False


class RunInlineRequest(BaseModel):
    scenario: dict[str, Any]
    parameters: dict[str, Any] = {}
    include_result: bool = False
    ttl_hours: int = 1


class SweepRequest(BaseModel):
    scenario_id: str
    parameter_sets: list[dict[str, Any]]
    include_baseline: bool = True


def _get_dt(request: Request) -> DT:
    dt = getattr(request.app.state, "dt", None)
    if dt is None:
        raise HTTPException(status_code=500, detail="DT runtime not initialized")
    return cast(DT, dt)


@router.get("")
async def list_simulations(request: Request) -> list[dict[str, Any]]:
    dt = _get_dt(request)
    sims = getattr(dt, "simulations", None)
    if sims is None:
        # fallback: registry-based
        if hasattr(dt, "registry") and hasattr(dt.registry, "simulations"):
            sims = dt.registry.simulations
        else:
            return []
    return sims.list()


@router.get("/{simulation_key}/describe")
async def describe_simulation(simulation_key: str, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    sims = getattr(dt, "simulations", None) or getattr(dt.registry, "simulations", None)
    if sims is None:
        raise HTTPException(status_code=404, detail="Simulations not enabled")
    try:
        return sims.get_descriptor(simulation_key).describe()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{simulation_key}/scenarios")
async def build_scenario(simulation_key: str, body: BuildScenarioRequest, request: Request) -> BuildScenarioResponse:
    dt = _get_dt(request)
    runner = getattr(dt, "simulation_runner", None)
    scenario_service = getattr(dt, "scenario_service", None)
    if runner is None or scenario_service is None:
        raise HTTPException(status_code=500, detail="Simulation subsystem not configured")

    context = dt.create_context(request=request, request_scope={})
    try:
        ref = await runner.build_scenario(
            simulation_key=simulation_key,
            config=body.config,
            context=context,
            ttl_hours=body.ttl_hours,
            reuse_existing=body.reuse_existing,
        )
        metadata = await scenario_service.get_metadata(ref.scenario_id)
        return BuildScenarioResponse(
            scenario_id=ref.scenario_id,
            simulation_key=simulation_key,
            created_at=ref.created_at.isoformat(),
            expires_at=ref.expires_at.isoformat(),
            config_hash=ref.config_hash,
            baseline_metrics=metadata.baseline_metrics if metadata else {},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to build scenario")
        raise HTTPException(status_code=500, detail="Scenario build failed")


@router.get("/{simulation_key}/scenarios")
async def list_scenarios(simulation_key: str, request: Request, include_expired: bool = Query(default=False)) -> list[dict[str, Any]]:
    dt = _get_dt(request)
    scenario_service = getattr(dt, "scenario_service", None)
    if scenario_service is None:
        return []
    refs = await scenario_service.list_scenarios(simulation_key=simulation_key, include_expired=include_expired)
    return [
        {
            "scenario_id": ref.scenario_id,
            "simulation_key": ref.simulation_key,
            "created_at": ref.created_at.isoformat(),
            "expires_at": ref.expires_at.isoformat(),
            "config_hash": ref.config_hash,
            "is_expired": ref.is_expired(),
        }
        for ref in refs
    ]


@router.get("/{simulation_key}/scenarios/{scenario_id}")
async def get_scenario(simulation_key: str, scenario_id: str, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    scenario_service = getattr(dt, "scenario_service", None)
    if scenario_service is None:
        raise HTTPException(status_code=500, detail="Scenario service not configured")

    metadata = await scenario_service.get_metadata(scenario_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    if metadata.simulation_key != simulation_key:
        raise HTTPException(status_code=400, detail=f"Scenario belongs to simulation '{metadata.simulation_key}'")

    return {
        "scenario_id": metadata.scenario_id,
        "simulation_key": metadata.simulation_key,
        "config": metadata.config,
        "config_hash": metadata.config_hash,
        "created_at": metadata.created_at.isoformat(),
        "expires_at": metadata.expires_at.isoformat(),
        "baseline_metrics": metadata.baseline_metrics,
        "artifacts": metadata.artifacts,
        "workspace_path": metadata.workspace_path,
    }


@router.delete("/{simulation_key}/scenarios/{scenario_id}")
async def delete_scenario(simulation_key: str, scenario_id: str, request: Request) -> dict[str, bool]:
    dt = _get_dt(request)
    scenario_service = getattr(dt, "scenario_service", None)
    if scenario_service is None:
        raise HTTPException(status_code=500, detail="Scenario service not configured")
    metadata = await scenario_service.get_metadata(scenario_id)
    if metadata and metadata.simulation_key != simulation_key:
        raise HTTPException(status_code=400, detail=f"Scenario belongs to simulation '{metadata.simulation_key}'")
    deleted = await scenario_service.delete_scenario(scenario_id)
    return {"deleted": deleted}


@router.post("/{simulation_key}/runs")
async def run_simulation(simulation_key: str, body: RunSimulationRequest, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    runner = getattr(dt, "simulation_runner", None)
    if runner is None:
        raise HTTPException(status_code=500, detail="Simulation runner not configured")

    context = dt.create_context(request=request, request_scope={})
    try:
        return await runner.run(
            simulation_key=simulation_key,
            scenario_id=body.scenario_id,
            parameters=body.parameters,
            context=context,
            include_result=body.include_result,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to run simulation")
        raise HTTPException(status_code=500, detail="Simulation failed")


@router.post("/{simulation_key}/run-inline")
async def run_simulation_inline(simulation_key: str, body: RunInlineRequest, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    runner = getattr(dt, "simulation_runner", None)
    if runner is None:
        raise HTTPException(status_code=500, detail="Simulation runner not configured")

    context = dt.create_context(request=request, request_scope={})
    try:
        return await runner.run_with_inline_scenario(
            simulation_key=simulation_key,
            scenario_config=body.scenario,
            parameters=body.parameters,
            context=context,
            ttl_hours=body.ttl_hours,
            include_result=body.include_result,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to run inline simulation")
        raise HTTPException(status_code=500, detail="Simulation failed")


@router.post("/{simulation_key}/sweep")
async def run_sweep(simulation_key: str, body: SweepRequest, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    runner = getattr(dt, "simulation_runner", None)
    if runner is None:
        raise HTTPException(status_code=500, detail="Simulation runner not configured")
    context = dt.create_context(request=request, request_scope={})
    try:
        return await runner.sweep(
            simulation_key=simulation_key,
            scenario_id=body.scenario_id,
            parameter_sets=body.parameter_sets,
            context=context,
            include_baseline=body.include_baseline,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to run sweep")
        raise HTTPException(status_code=500, detail="Sweep failed")


# ─────────────────────────────────────────────────────────────────────────────
# Run retrieval (run_id addressing)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    request: Request,
    simulation_key: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    dt = _get_dt(request)
    run_service = getattr(dt, "run_service", None)
    if run_service is None:
        return []
    refs = await run_service.list_runs(simulation_key=simulation_key, limit=limit, offset=offset)
    return [
        {
            "simulation_key": r.simulation_key,
            "run_id": r.run_id,
            "scenario_id": r.scenario_id,
            "created_at": r.created_at.isoformat(),
            "status": r.status.value,
        }
        for r in refs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    dt = _get_dt(request)
    run_service = getattr(dt, "run_service", None)
    if run_service is None:
        raise HTTPException(status_code=500, detail="Run service not configured")
    md = await run_service.get_metadata(run_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "simulation_key": md.simulation_key,
        "run_id": md.run_id,
        "scenario_id": md.scenario_id,
        "parameters": md.parameters,
        "parameters_hash": md.parameters_hash,
        "created_at": md.created_at.isoformat(),
        "started_at": md.started_at.isoformat() if md.started_at else None,
        "finished_at": md.finished_at.isoformat() if md.finished_at else None,
        "status": md.status.value,
        "error": md.error,
        "artifacts": md.artifacts,
        "workspace_path": md.workspace_path,
    }


@router.get("/runs/{run_id}/artifacts")
async def list_run_artifacts(run_id: str, request: Request) -> list[str]:
    dt = _get_dt(request)
    run_service = getattr(dt, "run_service", None)
    if run_service is None:
        raise HTTPException(status_code=500, detail="Run service not configured")
    md = await run_service.get_metadata(run_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return md.artifacts


@router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
async def download_run_artifact(run_id: str, artifact_path: str, request: Request):
    dt = _get_dt(request)
    run_service = getattr(dt, "run_service", None)
    if run_service is None:
        raise HTTPException(status_code=500, detail="Run service not configured")
    md = await run_service.get_metadata(run_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    abs_path = (Path(md.workspace_path) / artifact_path).resolve()
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    # minimal content-type handling is delegated to FileResponse
    return FileResponse(str(abs_path))
