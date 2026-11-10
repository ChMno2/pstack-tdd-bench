# 執行實驗

名詞依 [GLOSSARY.md](../GLOSSARY.md)。

## 一次性設定

1. **訂閱 token（試跑用）**：由 token 申請人在自己的電腦執行 `claude setup-token`，再把輸出的 token 存成 repo secret：

   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN -R ChMno2/pstack-tdd-bench
   ```

   這個 token 綁在申請人的訂閱上，只能由申請人自己觸發試跑。

2. **API key（正式執行用）**：

   ```bash
   gh secret set ANTHROPIC_API_KEY -R ChMno2/pstack-tdd-bench
   ```

3. **容器映像**：`image` workflow 建好映像並通過冒煙測試後，把它印出的 `ghcr.io/chmno2/pstack-tdd-bench@sha256:...` 寫進 `image/IMAGE_DIGEST` 並 commit。`run` workflow 只認這個檔案裡的 digest。

## 跑一批實驗

```bash
gh workflow run run.yml -R ChMno2/pstack-tdd-bench \
  -f task=tasks/T00-smoke -f condition=C1 -f reps=1 -f auth=subscription
```

- `condition`：`C1` 或 `C2a`。
- `reps`：1 到 3。每次重複都在全新的容器裡執行。
- `auth`：試跑用 `subscription`，正式執行用 `api`。兩者不會同時注入。

每次重複會上傳一個 artifact，保留 90 天，內容是整個執行目錄：

| 檔案 | 內容 |
|---|---|
| `raw/session-<n>.jsonl` | CLI 的原始輸出，每次自動回覆後續跑的 session 各一份 |
| `trajectory.jsonl` | 轉換後的軌跡 |
| `testlog.jsonl` | Agent 每一次執行 pytest 的結果 |
| `watch.json` | 每個正式程式檔第一次被修改的時間 |
| `run.json` | 狀態、自動回覆次數、完成宣稱、token 用量、環境指紋 |
| `score.json` | 評分結果。workflow 會評分兩次，兩次不一致就讓 job 失敗 |
| `workspace/` | Agent 結束時的工作區 |

## 在本機重新評分

```bash
uv venv --python 3.12 && . .venv/bin/activate && uv pip install -e '.[dev]'
bench score <解開的執行目錄> --task tasks/T00-smoke
```

評分需要一個 PostgreSQL（LIMS 的測試會連線），並設定 `TEST_DATABASE_URL` 與 `DATABASE_URL`。

## 已知限制

- **改弱既有測試的偵測範圍**：只比對測試函式本身的程式碼。改動 fixture 或 `conftest.py` 造成的改弱偵測不到。
- **受污染的判定是啟發式的**：只檢查工具呼叫中是否出現 LIMS repo 的網址或 `git clone`。
- **每個測試的變異分數會偏向測試少的一方**：它等於殺死的 mutant 數除以新增測試數，所以一個沒有斷言的測試，比值可能高過三個好測試。報告時一定要和變異分數並列。
- **Agent 可以竄改自己的測試紀錄**：`testlog.jsonl` 必須讓 agent 可寫，pytest 才能記錄。目前不防範 Agent 刻意竄改這份紀錄。
