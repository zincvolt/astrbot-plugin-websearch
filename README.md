# astrbot-plugin-websearch

联网搜索插件，用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot)。后端接本机自建的 [SearXNG](https://github.com/searxng/searxng) 实例（默认 9000 端口）。

## 功能

提供两个入口，互补：

1. **`web_search` LLM 工具**：模型可以显式调用它查资料。
2. **`on_llm_request` 自动搜索钩子**：每当最新一条用户消息看起来像事实性问题（问句、包含"什么/怎么/多少/最新/今天"等提示词），就自动搜索并把结果注入提示词。

之所以两个都要，是因为**小型本地模型很少主动调用工具**——自动钩子是可靠的路径，工具留给手动兜底。

搜索结果会截断摘要、限制条数（自动 4 条 / 工具 5 条），避免撑爆上下文。

## 依赖

- AstrBot 4.28+
- 本机 SearXNG 服务（默认 `http://127.0.0.1:9000/search`），需开启 JSON 输出
- `httpx`

## 许可证

AGPL-3.0-or-later，见 [LICENSE](LICENSE)。
