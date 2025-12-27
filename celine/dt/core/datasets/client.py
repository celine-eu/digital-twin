# celine/dt/core/datasets/client.py
from typing import Any, AsyncIterator, Optional
from abc import ABC, abstractmethod


class DatasetClient(ABC):
    """
    Core DT interface to the Dataset API.
    """

    @abstractmethod
    async def query(
        self,
        dataset_id: str,
        *,
        sql: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def stream(
        self,
        dataset_id: str,
        *,
        sql: Optional[str] = None,
        page_size: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]: ...

    @abstractmethod
    async def metadata(self, dataset_id: str) -> dict[str, Any]: ...
