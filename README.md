# pstack-tdd-bench

比較基準 Agent 與 pstack 工作流程在 AI 輔助 TDD 上的測試品質。Agent 在版本固定的容器中無人值守執行，每次執行都留下可回溯的軌跡，評分結果可以復現。

這是軟體測試課程的期末專題（第 7 組）。

## 狀態

建構中。框架的最小可用版本預計在 2026-11-29 完成。

## 受測系統

LIMS：[ChuuuDwarf/Cloud-Native-Development-Project](https://github.com/ChuuuDwarf/Cloud-Native-Development-Project)，固定在 commit `227be16`。

## 文件

- 名詞定義：[GLOSSARY.md](GLOSSARY.md)
- 重要決定：[docs/adr/](docs/adr/)

## 授權

本 repo 採用 MIT 授權。之後從 [pstack](https://github.com/cursor/plugins/tree/main/pstack) 複製進來的檔案會保留原作者的 MIT 授權聲明。
