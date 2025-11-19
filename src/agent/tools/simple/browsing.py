from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool


search = DuckDuckGoSearchRun()


@tool
def search_engine(query: str) -> str:
    """Search for text, news, images and videos using the DuckDuckGo.com search engine."""
    return search.invoke(query)
