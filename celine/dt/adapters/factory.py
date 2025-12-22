from __future__ import annotations

from celine.dt.adapters.base import DatasetAdapter
from celine.dt.adapters.registry import get_adapter_module
from celine.dt.adapters.sql_api import DATASET_API_ADAPTER, DatasetSqlApiAdapter
from celine.dt.core.dataset_client import get_dataset_api_client


def get_dataset_adapter_for_app(app_key: str) -> DatasetAdapter:
    module = get_adapter_module(app_key)

    if module.engine != DATASET_API_ADAPTER:
        raise ValueError(f"Unsupported adapter engine '{module.engine}'")

    client = get_dataset_api_client()
    return DatasetSqlApiAdapter(client=client)
