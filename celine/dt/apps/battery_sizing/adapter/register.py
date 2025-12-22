from pathlib import Path
from celine.dt.adapters.registry import register_adapter_module, AdapterModule
from celine.dt.adapters.sql_api import DATASET_API_ADAPTER


def register():
    register_adapter_module(
        AdapterModule(
            app_key="battery-sizing",
            engine=DATASET_API_ADAPTER,
            mapping_path=Path(__file__).parent / "inputs.yaml",
            provides=["load", "pv", "tariff"],
        )
    )
