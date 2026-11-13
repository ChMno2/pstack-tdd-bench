# pstack-tdd-bench · AI 輔助 TDD 實驗框架

![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)
![Harness](https://img.shields.io/badge/harness-Claude%20Code%202.1.322-d97706.svg)
![Python](https://img.shields.io/badge/python-3.12-059669.svg)
![SUT](https://img.shields.io/badge/SUT-LIMS%20227be16-111827.svg)
![Scoring](https://img.shields.io/badge/scoring-pytest%20%7C%20pytest--cov%20%7C%20mutmut-7c3aed.svg)
[![bench-ci](https://github.com/ChMno2/pstack-tdd-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/ChMno2/pstack-tdd-bench/actions/workflows/ci.yml)
[![image](https://github.com/ChMno2/pstack-tdd-bench/actions/workflows/image.yml/badge.svg)](https://github.com/ChMno2/pstack-tdd-bench/actions/workflows/image.yml)

> Reproducible TDD benchmark for AI coding agents，軟體測試課程期末專題（第 7 組）。

本專案讓 AI Agent 在版本固定的容器裡無人值守地做 TDD 任務，比較「基準 Agent」和「pstack 工作流程」寫出來的測試品質。受測系統是組員參與開發的 [LIMS](https://github.com/ChuuuDwarf/Cloud-Native-Development-Project)。每次執行都保留完整軌跡。評分在 Agent 之外進行，Agent 自己的完成宣稱不列入評分，同一次執行重新評分的結果必定相同。

- 跑實驗、讀結果：[docs/guides/running.md](docs/guides/running.md)
- 撰寫任務：[docs/guides/writing-tasks.md](docs/guides/writing-tasks.md)
- 名詞定義：[GLOSSARY.md](GLOSSARY.md)
- 架構決策：[docs/adr/](docs/adr/)
- 設計規格與實作計畫：[docs/design/](docs/design/)

## 系統架構

```text
GitHub Actions：run.yml（只能手動觸發，唯一拿得到模型憑證的 workflow）
  |
  v
固定容器 ghcr.io/chmno2/pstack-tdd-bench@sha256:...（見 image/IMAGE_DIGEST）
  |
  +--> bench run
  |      +--> 起始快照：LIMS 227be16 + start.patch，全新 git、沒有歷史、沒有遠端
  |      +--> Claude Code CLI 2.1.322，以無權限帳號 agent 執行；C2a 另外載入 pstack
  |      +--> 側錄：pytest 執行紀錄、正式程式碼修改監看、軌跡
  |      +--> 收尾：清除殘留程序、保存 transcript、遮蔽憑證
  |
  +--> bench score（評分兩次，結果必須完全相同）
  |      +--> 參考實作：起始快照 + reference.patch
  |      +--> 紅綠燈、TDD 遵循度、覆蓋率、變異分數、植入 bug、污染偵測
  |
  +--> PostgreSQL 16、Redis 7 service 容器（以 digest 固定）
  |
  v
artifact：run.json、score.json、軌跡、測試紀錄、Agent 的工作區（保留 90 天）
```

使用情境有三種：

| 情境 | 用途 | 入口 |
| --- | --- | --- |
| 跑實驗 | 試跑與正式執行 | [run.yml](.github/workflows/run.yml)、`make run` |
| 映像建置與演練 | 建映像、跑 LIMS 冒煙測試、用假 Agent 跑完整流程 | [image.yml](.github/workflows/image.yml)、`make image` |
| 本機開發 | 修改 bench、跑單元測試、檢查任務 | [Makefile](Makefile) |

## Tech Stack

| 層 | 技術 |
| --- | --- |
| Harness | Claude Code CLI 2.1.322，無頭模式，模型 `claude-sonnet-5-5` |
| 工作流程 | pstack v0.15.36 的 Claude Code 版本，原封不動 |
| 框架 | Python 3.12、PyYAML |
| 側錄 | pytest 外掛（以 `PYTEST_PLUGINS` 載入）、檔案雜湊監看 |
| 評分 | pytest 8.3.3、pytest-cov 5.0.0、mutmut 3.7.0 |
| 受測系統 | LIMS：FastAPI、SQLAlchemy 2 async、PostgreSQL 16、Redis 7 |
| 執行環境 | Docker、GitHub Container Registry、GitHub Actions（ubuntu-24.04） |
| 開發工具 | uv、ruff、GitHub CLI |

## 專案結構

```text
pstack-tdd-bench/
├── README.md                    # 專案總覽
├── GLOSSARY.md                  # 名詞定義
├── Makefile                     # install/test/lint/check-task/run/download/score 常用指令
├── pyproject.toml               # 套件設定、依賴、pytest 與 ruff 設定
├── bench/                       # Python 套件
│   ├── cli.py                   # bench run / score / check-task
│   ├── pins.py                  # 所有固定的版本與實驗常數
│   ├── task/                    # 任務格式、起始快照、參考實作、check-task
│   ├── harness/                 # 實驗條件、提示詞、CLI 參數、執行器、環境指紋
│   ├── capture/                 # pytest 執行紀錄外掛、檔案監看、軌跡格式
│   └── scoring/                 # 測試差異、紅綠燈、遵循度、覆蓋率與變異分數、彙整
├── tasks/                       # 任務定義（實驗時 Agent 讀不到）
│   └── T00-smoke/
├── sut/lims/                    # 受測系統 LIMS，git submodule，固定在 227be16
├── vendor/pstack/               # pstack 的 Claude Code 版本，保留原授權
├── image/                       # 容器映像、依賴鎖定檔、目前使用的映像 digest
├── .github/workflows/           # ci（單元測試）、image（映像與演練）、run（跑實驗）
├── docs/
│   ├── guides/                  # 使用說明：跑實驗、撰寫任務
│   ├── adr/                     # 架構決策紀錄
│   └── design/                  # 設計規格與實作計畫
└── tests/                       # bench 自己的測試，分類與 bench/ 相同
    ├── task/  harness/  capture/  scoring/
    └── fixtures/                # 迷你受測系統、迷你任務、CLI 輸出樣本、假的 claude
```

## 快速啟動

### Mode A: 在 GitHub Actions 跑實驗

適合要產生實驗數據的組員。需要 repo 的 collaborator 權限，以及 [GitHub CLI](https://cli.github.com/)。

```bash
# 1. 設定憑證（只需一次，由訂閱擁有人在自己的電腦執行）
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN -R ChMno2/pstack-tdd-bench

# 2. 觸發一批實驗：任務、條件、重複次數、認證方式
make run TASK=tasks/T00-smoke COND=C1 REPS=1 AUTH=subscription

# 3. 查看狀態並下載結果
make runs
make download RUN=<run-id>
```

也可以從網頁觸發：**Actions → run → Run workflow**。每次重複會產生一個 artifact，`score.json` 也會直接顯示在該 job 的 Summary 頁面。正式執行改用 API key：先存成 secret `ANTHROPIC_API_KEY`，再以 `AUTH=api` 觸發。

### Mode B: 本機開發與測試

適合修改 bench 或撰寫任務。需要 Python 3.12 與 [uv](https://docs.astral.sh/uv/)，單元測試不需要資料庫，也不需要網路。

```bash
git clone --recurse-submodules https://github.com/ChMno2/pstack-tdd-bench.git
cd pstack-tdd-bench

make install                              # 建立 .venv 並安裝
make test                                 # 單元測試
make lint                                 # ruff
make check-task TASK=tasks/T00-smoke      # 檢查任務的 patch 是否套得上
```

### Mode C: 重現與重新評分

下載的執行目錄可以在本機重新評分，得到的 `score.json` 應該與 artifact 裡的相同。評分會執行 LIMS 的測試，所以需要一個 PostgreSQL，並設定 `TEST_DATABASE_URL` 與 `DATABASE_URL`。

```bash
make score DIR=results/<run-id>/<artifact>/<任務>-<條件>-r<重複> TASK=tasks/T00-smoke
```

要重建容器映像時，先執行 `make lock` 更新依賴鎖定檔，再執行 `make image`，在 GitHub Actions 上建置並演練。通過後把印出的 digest 寫進 `image/IMAGE_DIGEST`。

## 實驗條件

| 條件 | 內容 | 狀態 |
| --- | --- | --- |
| C1 基準 | 固定版本的 Claude Code，只給任務描述，提示要求以 TDD 進行 | 可用 |
| C2a pstack 單一模型 | C1 加上 pstack，所有角色都是 `sonnet xhigh`（[ADR 0003](docs/adr/0003-c2a-subagent-effort.md)） | 可用 |
| C2b pstack 預設多模型 | pstack 預設的 Grok 與 Opus 分工 | 視成本決定 |
| C3 測試設計技能 | C2a 加上自製的等價類、邊界值與存活 mutant 回饋技能 | 第 15 週 |

所有固定的版本集中在 [bench/pins.py](bench/pins.py)，並寫進每次執行的環境指紋（`run.json` 的 `fingerprint`）。

## 環境變數與安全

| 變數 | 用途 | 設定者 |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | 試跑用的訂閱 token | repo secret |
| `ANTHROPIC_API_KEY` | 正式執行用的 API key | repo secret |
| `TEST_DATABASE_URL`、`DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`、`ENV` | LIMS 測試需要的連線設定 | workflow |
| `BENCH_IMAGE_DIGEST`、`BENCH_POSTGRES_DIGEST`、`BENCH_REDIS_DIGEST` | 寫進環境指紋 | workflow |
| `BENCH_TESTLOG`、`PYTEST_PLUGINS` | pytest 執行紀錄的位置與外掛 | 執行器 |

安全措施：

- **artifact 是公開的。** 執行器會把憑證從執行目錄的所有檔案中遮蔽成 `[REDACTED]`，上傳前 workflow 會再掃描一次，找到憑證就不上傳。
- **Agent 讀不到答案。** Agent 以無權限帳號執行，`tasks/`、`sut/` 與 repo 的 `.git` 都被鎖住，workflow 會逐一驗證。
- **Agent 不能上網查答案。** WebFetch 與 WebSearch 已停用。工具呼叫中如果出現存取 LIMS repo 的指令，該次執行標記為受污染。
- 請勿把 token、API key 或 `.env` 提交到 repo。同一次執行只會注入一種憑證。

## 核心功能

| 模組 | 功能 |
| --- | --- |
| `bench/task` | 任務格式、起始快照、參考實作、植入 bug 版本、`check-task` |
| `bench/harness` | 實驗條件與提示詞、CLI 參數與環境、執行器（自動回覆、逾時、清理、遮蔽）、環境指紋 |
| `bench/capture` | pytest 執行紀錄外掛、正式程式碼修改監看、軌跡格式與 Claude Code 輸出轉換 |
| `bench/scoring` | 測試差異、紅綠燈、TDD 遵循度、覆蓋率、變異分數、植入 bug、污染偵測、彙整 |

`score.json` 的欄位：

| 欄位 | 意思 |
| --- | --- |
| `tests` | 新增、刪除、修改了哪些測試。新增為零就是**無測試執行** |
| `red` | 新增的測試放回起始快照上，是否至少一個失敗 |
| `green` | 新增的測試在參考實作上連跑 3 次，分成有效、失敗、不穩定 |
| `adherence` | 在 Agent 第一次修改正式程式碼之前，新測試是否已經失敗過 |
| `coverage` | 有效測試對任務模組的行覆蓋率與分支覆蓋率 |
| `mutation` | 有效測試對任務模組的變異分數 |
| `planted` | 每個植入的 bug 是否被有效測試抓到 |
| `contaminated` | Agent 是否試圖取得公開的 LIMS 原始碼 |
| `cost` | token 用量（依主 Agent 與各子 Agent 拆分）與自動回覆次數 |

解讀注意事項與已知限制見 [docs/guides/running.md](docs/guides/running.md)。

## 測試與 CI

```bash
make test         # bench 的單元測試，約 1 分鐘
make lint         # ruff
```

| Workflow | 觸發方式 | 內容 |
| --- | --- | --- |
| [ci.yml](.github/workflows/ci.yml) | 每次 push | ruff 與單元測試 |
| [image.yml](.github/workflows/image.yml) | 映像相關檔案變更時、手動 | 建置映像、LIMS 後端測試、假 Agent 全流程演練 |
| [run.yml](.github/workflows/run.yml) | 只能手動 | 跑實驗、評分兩次比對、掃描憑證、上傳結果 |

## 目前狀態

- C1、C2a 與冒煙任務 `T00-smoke` 已完成。映像建置、LIMS 冒煙測試（427 個後端測試全過）與假 Agent 全流程演練都在 GitHub Actions 上通過。
- 尚未完成：用真正的 Claude Code 跑冒煙任務（需要訂閱 token），以及正式任務集（第 12 週凍結）。

## 授權

本 repo 採用 MIT 授權。`vendor/pstack/` 保留原作者 Lauren Tan 的 MIT 授權聲明。受測系統 LIMS 沒有附授權條款，公開含 LIMS 程式碼的實驗結果之前，需先取得 LIMS 團隊同意。
