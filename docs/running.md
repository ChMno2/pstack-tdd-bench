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

每次重複會上傳一個 artifact，保留 90 天，內容是整個執行目錄。**這個 repo 是公開的，artifact 任何人都下載得到。** 執行器會把憑證的值從執行目錄裡的所有檔案中遮蔽成 `[REDACTED]`。上傳前，workflow 會再掃描一次，只要找到憑證就不上傳。

| 檔案 | 內容 |
|---|---|
| `raw/session-<n>.jsonl` | CLI 的原始輸出，每次自動回覆後續跑的 session 各一份 |
| `trajectory.jsonl` | 轉換後的軌跡 |
| `transcripts/` | Claude Code 自己的對話紀錄，包含子 Agent 的工具呼叫 |
| `testlog.jsonl` | Agent 每一次執行 pytest 的結果。執行結束後改為 root 擁有、唯讀 |
| `watch.json` | 每個正式程式檔第一次被修改的時間 |
| `run.json` | 狀態、自動回覆次數、殘留程序數、完成宣稱、token 用量、環境指紋 |
| `score.json` | 評分結果。workflow 會評分兩次，兩次不一致就讓 job 失敗 |
| `scoring/mutmut.log` | mutmut 的完整輸出與每個 mutant 的結果 |
| `workspace/` | Agent 結束時的工作區。`.git` 已移除，因為壓縮過的物件無法遮蔽憑證 |
| `workspace-git.patch` | Agent 的 commit 歷史，以文字形式保存 |

讀 `score.json` 時要注意：

- `coverage.ok` 或 `mutation.ok` 為 `false`，代表工具執行失敗，數值是 `null`。這種情況和量到 0 是兩回事，原因在 `mutation.error` 與 `scoring/mutmut.log`。
- `adherence.unmeasured` 為 `true`，代表 Agent 跑過 pytest，但測試紀錄是空的。這次的遵循度無法判定，不能算成「沒有遵循」。

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
- **Agent 可以竄改自己的測試紀錄**：執行期間 `testlog.jsonl` 必須讓 agent 可寫，pytest 才能記錄。執行結束後才改成唯讀，所以執行期間的竄改防不了。
- **mutmut 不突變有 decorator 的函式**：`@staticmethod` 和 `@classmethod` 例外。有 decorator 的 class（例如 `@dataclass`）裡的方法也不突變。在 LIMS 裡，這代表 `@router` 端點、`@property`、celery task 和 pydantic 欄位驗證都量不到變異分數。設計任務時，要讓被測邏輯放在沒有 decorator 的函式裡。
- **變異分數以整個檔案為分母**：T00 的分母是 1332 個 mutant。同一個任務內比較不同條件時，分母相同，比較仍然公平。不同任務之間的絕對分數不能直接比。
