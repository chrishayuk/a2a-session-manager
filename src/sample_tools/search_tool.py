"""
sample_tools/search_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Quick-and-dirty “search” tool.

• Synchronous processors call  →  run()
• Async processors call        →  await arun()
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool


@register_tool(name="search")
class SearchTool(ValidatedTool):
    """Return dummy search results (demo only)."""

    # ── validated arguments & result ─────────────────────────────
    class Arguments(ValidatedTool.Arguments):
        query: str
        num_results: int = 3

    class Result(ValidatedTool.Result):
        results: List[Dict[str, str]]

    # ── core (blocking) implementation ───────────────────────────
    def _execute(self, query: str, num_results: int) -> Dict:
        """Pretend we queried a search engine."""
        time.sleep(0.8)  # simulate network latency
        return {
            "results": [
                {
                    "title": f"Result {i+1} for {query}",
                    "url": f"https://example.com/result{i+1}",
                    "snippet": f"This is a search result about {query}.",
                }
                for i in range(num_results)
            ]
        }

    # ── sync entry-point required by ValidatedTool ───────────────
    def run(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        result = self._execute(**args.model_dump())
        return self.Result(**result).model_dump()

    # ── async façade so callers can “await” the tool ─────────────
    async def arun(self, **kwargs) -> Dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.run(**kwargs))
