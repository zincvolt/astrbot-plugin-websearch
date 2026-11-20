"""Web search for the QQ bot, backed by the local SearXNG instance.

Two entry points:

1. ``web_search`` LLM tool - the model can call it explicitly.
2. ``on_llm_request`` hook - the framework searches on its own whenever the
   latest user message looks like a factual question. Small local models
   rarely call tools on their own, so the hook is the reliable path and the
   tool stays as a manual fallback.
"""

from __future__ import annotations

import re

import httpx

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest

# 指令自声明（插件开发规范要求，见 docs/PLUGIN-DEV.md）：本插件无斜线指令
DECLARED_COMMANDS: dict[str, tuple[str, str]] = {}
DECLARED_BEHAVIOR = "无斜线指令：LLM 工具调用联网搜索，提问类消息自动触发（SearXNG 9000）"

SEARX_URL = "http://127.0.0.1:9000/search"
TOOL_MAX_RESULTS = 5
AUTO_MAX_RESULTS = 4
SNIPPET_CHARS = 180
AUTO_SNIPPET_CHARS = 140

QUESTION_HINTS = re.compile(
    r"[？?]|什么|怎么|咋|多少|几个|哪[个里儿天年]|谁|何时|几点|多久|为何|为什么|"
    r"是不是|能不能|有没有|可不可以|求推荐|最新|新闻|今天|现在|最近|目前|"
    r"价格|多少钱|版本|更新|结束|开始|上映|发布"
)

CQ_AT = re.compile(r"\[CQ:at,qq=\d+\]")


def _looks_like_question(text: str) -> bool:
    """Decide whether a chat message is worth an automatic web search.

    Args:
        text: Normalized message text.

    Returns:
        True when the message reads like a question or a request for facts.
    """
    stripped = text.strip()
    if len(stripped) < 5 or len(stripped) > 120:
        return False
    return bool(QUESTION_HINTS.search(stripped))


async def _searx(query: str, limit: int) -> list[dict]:
    """Query the local SearXNG instance.

    Args:
        query: Search query.
        limit: Maximum number of results to keep.

    Returns:
        A list of raw result dicts, empty on failure.
    """
    async with httpx.AsyncClient(timeout=12) as client:
        resp = await client.get(
            SEARX_URL,
            params={"q": query, "format": "json", "language": "zh-CN"},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])[:limit]


def _format(results: list[dict], snippet_chars: int) -> str:
    """Render search results as a compact plain-text block."""
    lines = []
    for item in results:
        title = (item.get("title") or "").strip()
        snippet = (item.get("content") or "").strip().replace("\n", " ")
        url = (item.get("url") or "").strip()
        if not title and not snippet:
            continue
        lines.append(f"- {title}：{snippet[:snippet_chars]}（{url}）")
    return "\n".join(lines)


class Main(star.Star):
    """Web search tool plus automatic retrieval."""

    def __init__(self, context: star.Context) -> None:
        self.context = context

    @filter.llm_tool(name="web_search")
    async def web_search(self, event: AstrMessageEvent, query: str) -> str:
        """联网搜索实时信息。需要最新消息或具体数据时调用。

        Args:
            query(string): 搜索关键词，尽量简短准确
        """
        try:
            results = await _searx(query, TOOL_MAX_RESULTS)
        except Exception as exc:  # noqa: BLE001 - the model gets a text error
            logger.warning(f"[websearch] tool searx failed: {exc}")
            return "搜索服务当前不可用，直接凭已有知识回答，并说明不确定。"
        if not results:
            return "没有搜到结果。直接说明不确定，不要编造。"
        return _format(results, SNIPPET_CHARS)

    @filter.on_llm_request()
    async def auto_search(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """Search automatically for question-like messages and inject snippets.

        Args:
            event: The message event being answered.
            req: The outgoing provider request to augment.
        """
        text = CQ_AT.sub(" ", event.message_str or "").strip()
        if not _looks_like_question(text):
            return
        try:
            results = await _searx(text[:60], AUTO_MAX_RESULTS)
        except Exception as exc:  # noqa: BLE001 - never block the reply
            logger.warning(f"[websearch] auto searx failed: {exc}")
            return
        if not results:
            return

        block = _format(results, AUTO_SNIPPET_CHARS)
        logger.info(f"[websearch] auto search | {text[:30]} | {len(results)} results")
        req.system_prompt = (req.system_prompt or "") + (
            "\n\n[实时搜索结果，可能不全或过时，只取和问题相关的部分；"
            "资料里没有的就直接说不知道，不要编]\n" + block
        )
