from __future__ import annotations

import functools
from celine.dt.core.config import settings
from celine.dt.adapters.sql_api import DatasetSqlApiClient


@functools.lru_cache(maxsize=1)
def get_dataset_api_client() -> DatasetSqlApiClient:
    return DatasetSqlApiClient(
        base_url=str(settings.dataset_api_base_url),
        token=settings.dataset_api_token,
    )
