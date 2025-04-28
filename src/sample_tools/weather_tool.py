"""
sample_tools/weather_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Demo “Weather” tool that works with both synchronous and asynchronous
callers:

  • synchronous processors call  →   ``run()``  
  • async processors   call      →   ``await arun()``

Nothing else in your code has to change.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict

from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool


@register_tool(name="weather")
class WeatherTool(ValidatedTool):
    """Return fake weather data for a location (demo only)."""

    # ── validated arguments & result ────────────────────────────
    class Arguments(ValidatedTool.Arguments):
        location: str
        units: str = "metric"

    class Result(ValidatedTool.Result):
        temperature: float
        conditions: str
        humidity: float
        location: str

    # ── synchronous implementation (required) ───────────────────
    def _execute(self, location: str, units: str) -> Dict:
        """Pretend we called a weather API."""
        time.sleep(0.5)  # simulate I/O delay
        return {
            "temperature": 22.5,
            "conditions": "Partly Cloudy",
            "humidity": 65.0,
            "location": location,
        }

    # ── public sync entry-point expected by ValidatedTool ────────
    def run(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        result = self._execute(**args.model_dump())
        return self.Result(**result).model_dump()  # plain dict

    # ── optional async wrapper so callers can ``await`` it ───────
    async def arun(self, **kwargs) -> Dict:
        loop = asyncio.get_running_loop()
        # run the blocking `_execute` in a thread to avoid blocking the loop
        return await loop.run_in_executor(None, lambda: self.run(**kwargs))
