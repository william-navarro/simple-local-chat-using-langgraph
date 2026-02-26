import json

from langchain_core.tools import tool
from duckduckgo_search import DDGS


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for current information. Use this when the user asks about
    recent events, real-time data, current prices, weather, news, or anything
    that may require up-to-date information beyond your training. Consider data
    ONLY from english and brazilian portuguese websites."""
    try:
        num_results = max(1, min(10, num_results))
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

        if not results:
            return json.dumps(
                {"status": "no_results", "message": f"No results found for: {query}"}
            )

        formatted = [
            {
                "position": i,
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for i, r in enumerate(results, 1)
        ]

        return json.dumps({"status": "success", "query": query, "results": formatted})

    except Exception as e:
        return json.dumps({"status": "error", "message": f"Search failed: {str(e)}"})


ALL_TOOLS = [web_search]
