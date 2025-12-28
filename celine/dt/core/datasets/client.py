# celine/dt/core/datasets/client.py
from typing import Any, AsyncIterator, Optional
from abc import ABC, abstractmethod


from typing import Any, AsyncIterator
from abc import ABC, abstractmethod


class DatasetClient(ABC):
    """
    Core DT interface to the Dataset SQL API.
    """

    @abstractmethod
    async def query(
        self,
        *,
        sql: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def stream(
        self,
        *,
        sql: str,
        page_size: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]: ...
