# pstack-tdd-bench 設計規格

日期：2026-11-11。名詞依 [GLOSSARY.md](../../../GLOSSARY.md)，重要決定見 [docs/adr/](../../adr/)。

## 目的

在版本固定的獨立環境中，無人值守地執行「任務 × 條件 × 3 次」的 TDD 實驗。每次執行留下可回溯的軌跡，評分結果在同一個環境指紋下可以復現。

## 範圍

最小可用版本（2026-11-29 前）只需支援 C1 與 C2a，以及一個冒煙測試任務。C2b、C3、C2c 與 Prevention 不在這一版。

## 執行流程

1. **起始快照**：從 LIMS 固定 commit 匯出程式碼，套用任務的 `start.patch`，以單一 commit 建立全新的 git repo，不保留歷史，也沒有遠端。
2. **執行**：執行器以無頭模式啟動固定版本的 Claude Code CLI，依條件給定提示與 pstack 外掛。CLI 的輸出原樣存檔，再轉成我們自己的軌跡格式。
3. **自動回覆**：Agent 結束時若在請求決策，執行器以同一個 session 續跑，回覆固定訊息「請依你的判斷繼續，不要再詢問」，最多 3 次。
4. **側錄**：容器內的 pytest 外掛記錄每一次 pytest 執行與各測試結果。執行器另外每秒比對正式程式碼的檔案內容，記下第一次被修改的時間。兩者都不依賴 harness。
5. **評分**：在 Agent 之外進行，Agent 的完成宣稱只記錄。

## 評分項目

- 新增、刪除、修改的測試：以測試 node ID 比對最終工作區與起始快照。新增為零即為無測試執行。
- 紅燈：新增測試在起始快照上至少一個失敗或收集錯誤。
- 綠燈：新增測試在參考實作上連跑 3 次，3 次都通過才算有效，結果不一致者列為不穩定。
- 覆蓋率與變異分數：只用有效的新增測試，只針對任務指定的模組。每個測試的變異分數 = 殺死的 mutant 數 ÷ 新增測試數。
- 植入 bug 偵測：把每個植入 bug 的 patch 套到參考實作上，有效新增測試任一失敗即算偵測到。
- TDD 遵循度：測試紀錄中，某個新增測試在正式程式碼第一次被修改之前至少失敗過一次。
- 成本：token 依主 Agent 與各子 Agent 拆分、耗時、自動回覆次數。

## 環境指紋

harness 名稱與版本、模型 ID、pstack commit、LIMS commit、bench 自身 commit、執行容器與 PostgreSQL、Redis 映像 digest、任務內容雜湊、`TZ` 與 `PYTHONHASHSEED`。

## 執行環境

GitHub Actions `ubuntu-24.04`，只能手動觸發。Agent 與評分在以 digest 固定的容器中執行，PostgreSQL 16 與 Redis 7 以 digest 固定的 service 容器提供。試跑用 `CLAUDE_CODE_OAUTH_TOKEN`，正式執行用 `ANTHROPIC_API_KEY`，同一次執行只能存在其中一個。原始輸出、軌跡、測試紀錄與評分結果以 artifact 上傳，保留 90 天，涵蓋整個課程期間。

## 任務格式

每個任務一個目錄 `tasks/<id>/`：

- `task.yaml`：id、類型（bugfix 或 feature）、給 Agent 的任務描述、測試指令、受評模組路徑、植入 bug 清單。
- `start.patch`：LIMS 固定 commit 到起始快照的差異。
- `reference.patch`：起始快照到參考實作的差異。
- `planted/*.patch`：每個植入 bug 一個，套在參考實作上。
