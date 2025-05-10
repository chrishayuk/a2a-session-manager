"""
sample_tools/search_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
DuckDuckGo HTML search – *sync `_execute` + async facade*.

Compatible with chuk-tool-processor 0.1.x `ValidatedTool`.
"""

from __future__ import annotations

import asyncio, re
from html import unescape
from typing import Dict, List
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry.decorators import register_tool


_DDG_URL   = "https://html.duckduckgo.com/html/"
_HEADERS   = {"User-Agent": "a2a_demo_search_tool/2.0 (+https://example.com)"}
_RESULT_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>'
    r'(?P<title>.*?)</a>',
    re.S,
)


def _clean_ddg_link(raw: str) -> str:
    """Return direct target for DDG redirect URLs."""
    if not raw.startswith("//duckduckgo.com/l/"):
        return raw
    return unquote(parse_qs(urlparse(raw).query).get("uddg", [""])[0])


def _scrape(query: str, max_results: int) -> List[Dict]:
    """Blocking HTML scrape – called by synchronous `_execute`."""
    with httpx.Client(timeout=8, headers=_HEADERS, follow_redirects=True) as http:
        rsp = http.get(_DDG_URL, params={"q": query})
        rsp.raise_for_status()

    hits: List[Dict] = []
    for m in _RESULT_RE.finditer(rsp.text):
        hits.append(
            {
                "title": unescape(re.sub(r"<[^>]+>", "", m.group("title"))),
                "url": _clean_ddg_link(unescape(m.group("url"))),
            }
        )
        if len(hits) >= max_results:
            break
    return hits


# ─────────────────────────── tool definition ────────────────────────────
@register_tool(name="search")
class SearchTool(ValidatedTool):
    """DuckDuckGo search (sync core, async-friendly)."""

    class Arguments(ValidatedTool.Arguments):
        query: str
        max_results: int = 5

    class Result(ValidatedTool.Result):
        results: List[Dict]

    # -------- REQUIRED sync implementation for ValidatedTool ----------
    def _execute(self, *, query: str, max_results: int) -> Result:  # noqa: D401
        hits = _scrape(query, max_results)
        return self.Result(results=hits)

    # `run()` is what the executor calls in a worker thread
    def run(self, **kwargs) -> Dict:
        args  = self.Arguments(**kwargs)
        model = self._execute(**args.model_dump())      # synchronous call
        return model.model_dump()

    # -------- Optional async facade for direct async usage ------------
    async def arun(self, **kwargs) -> Dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.run(**kwargs))
