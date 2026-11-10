# 撰寫任務

**任務**是 Agent 要在受測系統上完成的一個 TDD 工作單位，分成修 bug（`bugfix`）和新功能（`feature`）兩類。名詞定義見 [GLOSSARY.md](../GLOSSARY.md)。

## 目錄格式

```
tasks/<id>/
  task.yaml          任務設定與給 Agent 的描述
  start.patch        LIMS 固定 commit → 起始快照
  reference.patch    起始快照 → 參考實作
  planted/<name>.patch   參考實作 → 植入一個 bug 的版本，每個 bug 一份
```

`<id>` 建議用 `T<兩位數>-<簡短描述>`，例如 `T03-quota-check`。`tasks/` 在實驗時會被鎖住，Agent 讀不到。

## task.yaml

以冒煙任務 [tasks/T00-smoke/task.yaml](../tasks/T00-smoke/task.yaml) 為例：

```yaml
id: T00-smoke
kind: bugfix
workdir: backend
test_command: cd backend && python -m pytest
modules:
  - app/services/sample_service.py
prod_globs:
  - backend/app/**/*.py
planted:
  - boundary
description: |
  Bug report: lab codes that arrive with surrounding whitespace are not normalised ...
```

| 欄位 | 說明 |
|---|---|
| `id` | 任務代號，要和目錄名稱相同 |
| `kind` | `bugfix` 或 `feature`。C2a 會依此選 pstack 的 Bug fix 或 Feature playbook |
| `description` | 給 Agent 的任務描述，用英文寫 |
| `workdir` | pytest 的執行目錄，相對於 LIMS 根目錄 |
| `test_command` | 寫進提示詞，告訴 Agent 怎麼跑測試 |
| `modules` | 要量覆蓋率和變異分數的檔案，相對於 `workdir` |
| `prod_globs` | 哪些檔案算正式程式碼，用來判斷 Agent 何時第一次修改正式程式碼。相對於 LIMS 根目錄 |
| `planted` | 植入 bug 的名稱，每個名稱對應 `planted/<名稱>.patch` |

## 三份 patch 的關係

```
LIMS 227be16 --start.patch--> 起始快照 --reference.patch--> 參考實作 --planted/x.patch--> 植入 bug 的版本
```

- **修 bug 任務**：`start.patch` 把 bug 放進去，可以是自行植入的 bug，或還原 LIMS 的某個歷史修正。`reference.patch` 把它修好。
- **新功能任務**：起始快照通常就是原本的 LIMS，`start.patch` 可以是空檔。`reference.patch` 是組員寫好的功能實作。
- **植入 bug**：套在參考實作上，模擬「實作裡藏了一個缺陷」。評分時會看 Agent 寫的有效測試抓不抓得到。

## 產生 patch

在暫存目錄展開固定版本的 LIMS，依序修改並把差異存成 patch。patch 裡的路徑相對於 LIMS 根目錄，例如 `backend/app/...`。

```bash
REPO="$PWD"                       # pstack-tdd-bench 的根目錄
ID=T03-quota-check
mkdir -p "tasks/$ID/planted"
T=$(mktemp -d)
git -C sut/lims archive 227be16e3365e9956da0dec8efa987db3e0f3e4f | tar -x -C "$T"
cd "$T" && git init -q && git add -A && git commit -qm base

# 1. 做出起始狀態。修 bug 任務在這裡植入 bug；新功能任務不用改，會得到空的 start.patch
"$EDITOR" backend/app/...
git diff > "$REPO/tasks/$ID/start.patch" && git commit -qam start --allow-empty

# 2. 做出參考實作
"$EDITOR" backend/app/...
git diff > "$REPO/tasks/$ID/reference.patch" && git commit -qam reference

# 3. 每個植入 bug 各做一次：修改、存檔、還原
"$EDITOR" backend/app/...
git diff > "$REPO/tasks/$ID/planted/boundary.patch" && git checkout .

cd "$REPO" && rm -rf "$T"
```

最後在 `tasks/$ID/` 寫好 `task.yaml`。

## 規則

1. **被測邏輯要放在沒有 decorator 的函式裡。** mutmut 不會突變有 decorator 的函式，`@staticmethod` 和 `@classmethod` 例外。有 decorator 的 class（例如 `@dataclass`）裡的方法也不會突變。在 LIMS 裡，`@router` 端點、`@property`、celery task 和 pydantic 欄位驗證都量不到變異分數。適合的位置是 `app/services/` 這類 service 層函式。
2. **`modules` 只列被測的檔案。** 變異分數的分母是整個檔案的 mutant，所以檔案裡不相關的函式越多，分數越低。同一個任務內比較不同條件時不受影響。
3. **修 bug 任務的 bug，不能被 LIMS 既有的測試抓到。** 否則 Agent 一開始跑測試就會看到紅燈，量不出它自己寫測試的能力。先用 `grep -rn <函式名稱> sut/lims/backend/tests` 確認既有測試沒有涵蓋。
4. **新功能任務要在 `description` 裡附上介面約定**，包括 endpoint 路徑、request 與 response 格式、錯誤碼，最好用 OpenAPI 片段。參考實作必須完全照約定實作，否則 Agent 寫的測試會只因命名不同而被剔除。
5. **`description` 只寫症狀與要求，不寫修法。** 測試指令和 TDD 要求由提示詞範本統一加上，不用寫在這裡。
6. **每個任務至少一個植入 bug**，而且要是一個好的測試能抓到的缺陷，例如邊界值、條件寫反、漏掉的檢查。
7. **任務集在第 12 週以 commit SHA 凍結。** 設計 C3 技能的組員不參與植入 bug。

## 驗證

寫完後在本機檢查，需要先照 [README](../README.md#本機開發) 建好開發環境：

```bash
bench check-task --task tasks/<id>
```

輸出 `OK` 就代表三份 patch 都套得上，`modules` 和 `prod_globs` 也都找得到檔案。有問題時會逐條列出 `PROBLEM:`。

`check-task` 不會跑 LIMS 的測試。要確認整個任務端到端可以跑，用 `run.yml` 以 `reps=1` 跑一次，這會用到模型額度。
