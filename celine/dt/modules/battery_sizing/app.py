from __future__ import annotations
from typing import Any

class BatterySizingApp:
    key = "battery-sizing"
    version = "1.0.0"

    async def run(self, inputs: Any, **context: Any) -> dict:
        return {
            "@id": "urn:celine:battery-sizing:demo",
            "@type": "EnergyKPI",
            "value": 42.0,
        }
