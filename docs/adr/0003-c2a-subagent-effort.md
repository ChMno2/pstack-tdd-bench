# C2a 的 pstack 角色一律設為 `sonnet xhigh`

C2a 要代表「只有一個模型的一般使用者照 pstack 預設流程使用」。pstack 的 Claude Code 版本規定，角色的值寫成 `<模型> <推理強度>`，預設的預算是 large，也就是 xhigh。所以 `~/.claude/rules/pstack-models.md` 的每個角色都寫成 `sonnet xhigh`，panel 角色維持 pstack 預設的兩個名額。實際使用的模型另外由 `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-5-5` 強制固定。

## Consequences

- C2a 的子 Agent 以 xhigh 推理強度執行。C1 和 C2a 的主 Agent 都使用 CLI 的預設推理強度。兩個條件在推理強度上的差異屬於 pstack 流程本身，不另外拉平。
- 如果想改成「pstack 子 Agent 和 C1 同樣使用預設推理強度」，只要修改 `bench/pins.py` 的 `PSTACK_EFFORT`。但改了就是另一個條件，已經跑過的結果不能混用。
