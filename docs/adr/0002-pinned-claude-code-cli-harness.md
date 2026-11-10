# Harness 使用固定版本的 Claude Code CLI，不使用 Agent SDK 或 LangGraph

我們需要一個版本固定、能在容器裡無人值守執行的 harness。決定以無頭模式執行固定版本的 Claude Code CLI，外面包一個自寫的 Python 執行器。理由有三個：

1. 這是官方唯一允許在 CI 中使用訂閱額度的方式，所以試跑和正式執行只需要換認證，不需要換 harness。
2. pstack 官方提供 Claude Code 版本，C2a 測得到未經修改的 pstack。
3. C1 基準因此對應到一般使用者實際在用的工具。

## Considered Options

- **Claude Agent SDK**：底層是同一個 CLI，程式介面比較好寫。但官方要求使用 API key，試跑階段就得付費。
- **LangGraph 搭配 deepagents**：可以混用多家模型，也完全開源。但只能使用 API key，而且 pstack 技能裡的工具名稱需要改寫，改寫後 C2a 測的就不再是原版 pstack。

## Consequences

- 測試執行紀錄和軌跡格式都不依賴 Claude Code 的功能，日後可以換用其他 harness。但同一個實驗裡的所有條件只能使用同一個 harness。
- C2b 需要非 Anthropic 的模型，無法直接在這個 harness 上執行。是否改用原始碼與文件分析來回答 RQ4，等 W13 估算成本後再決定。
- 固定版本的方法：安裝時指定 CLI 版本、設定 `DISABLE_UPDATES=1` 和 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`、一律使用完整的模型 ID。
