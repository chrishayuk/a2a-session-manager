"""
sample_tools/search_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

DuckDuckGo HTML search tool (chuk_tool_processor ≥ 0.8).

• Queries the *html.duckduckgo.com* endpoint directly.
• Strips DDG redirect wrappers so callers get plain target URLs.
• Returns a structured `Result` model.
"""
from __future__ import annotations

import asyncio
import re
import time
from html import unescape
from typing import Dict, List
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool

# ─────────────────────────── helpers ────────────────────────────────
_DDG_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": "a2a_demo_search_tool/1.2 (+https://example.com)"
}


def _clean_ddg_link(raw: str) -> str:
    """If `raw` is a DDG redirect URL, return the direct target; else raw."""
    if not raw.startswith("//duckduckgo.com/l/"):
        return raw
    qs = parse_qs(urlparse(raw).query)
    target = qs.get("uddg", [""])[0]
    return unquote(target) or raw


def _search_ddg_html(query: str, max_results: int) -> List[Dict]:
    """Scrape DuckDuckGo HTML results and return ≤ `max_results` hits."""
    params = {"q": query}
    with httpx.Client(
        timeout=8, headers=_HEADERS, follow_redirects=True
    ) as client:
        rsp = client.get(_DDG_URL, params=params)
        rsp.raise_for_status()

    pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>'
        r'(?P<title>.*?)</a>',
        re.S,
    )

    results = []
    for m in pattern.finditer(rsp.text):
        title = unescape(re.sub(r"<[^>]+>", "", m.group("title")))
        url = _clean_ddg_link(unescape(m.group("url")))
        results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return results


# ─────────────────────────── tool class ─────────────────────────────
@register_tool(name="search")
class SearchTool(ValidatedTool):
    """DuckDuckGo search tool using the new ValidatedTool contract."""

    # schemas ----------------------------------------------------------
    class Arguments(ValidatedTool.Arguments):
        query: str
        max_results: int = 5

    class Result(ValidatedTool.Result):
        results: List[Dict]

    # sync entry-point -------------------------------------------------
    def _execute(self, *, query: str, max_results: int) -> Result:
        # tiny pause so demos don’t hammer DDG
        time.sleep(0.4)
        hits = _search_ddg_html(query, max_results)
        return self.Result(results=hits)

    # optional async variant ------------------------------------------
    async def _execute_async(self, *, query: str, max_results: int) -> Result:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._execute(query=query, max_results=max_results)
        )
