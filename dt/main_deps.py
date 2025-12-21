from __future__ import annotations

import functools
from dt.core.config import settings
from dt.adapters.sql_api import DatasetSqlApiClient, DatasetSqlApiAdapter


@functools.lru_cache(maxsize=1)
def get_dataset_adapter() -> DatasetSqlApiAdapter:
    client = DatasetSqlApiClient(
        str(settings.dataset_api_base_url), settings.dataset_api_token
    )
    # PoC: one mapping file. Extend to multi-instance via config.
    return DatasetSqlApiAdapter(
        client=client, mapping_path="app/adapters/mappings/maps-gl.yaml"
    )
