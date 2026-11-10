# pstack TDD 實驗框架

在固定環境下比較基準 Agent 與 pstack 工作流程在 AI 輔助 TDD 上的測試品質，每個結果都能回溯與復現。

## 實驗設計

**受測系統（SUT）**:
Agent 執行 TDD 任務的程式碼庫。正式實驗使用 LIMS，Prevention 為延伸目標。
_Avoid_: 目標系統、專案、app

**任務（Task）**:
在受測系統上要完成的一個 TDD 工作單位，分為新功能與修 bug 兩類。
_Avoid_: 題目、case、issue

**條件（Condition）**:
Agent 工作流程的一種配置，共四種：C1 基準、C2a pstack 單一模型、C2b pstack 預設多模型、C3 加入測試設計技能。
_Avoid_: 組別、模式、setting、arm

**執行（Run）**:
一個任務在一個條件下的一次完整執行，同一組任務與條件重複三次。
_Avoid_: 試跑、trial、session

**試跑（Pilot）**:
W13 在少數任務上先行的執行，用來估算成本並找出框架問題。
_Avoid_: 執行、dry run

**起始快照（Snapshot）**:
任務開始時受測系統的程式碼狀態，已移除 git history，所有條件共用同一份。
_Avoid_: base、checkout、starting commit

**參考實作（Reference Implementation）**:
組員撰寫的正確實作，各條件產出的測試一律拿到它上面評分。
_Avoid_: 標準答案、golden、解答

**植入 bug（Planted Bug）**:
組員刻意加入或還原歷史修正而得到的缺陷，整個集合在 W12 以 commit SHA 凍結。
_Avoid_: 注入錯誤、seeded fault

**變異體（Mutant）**:
變異測試工具自動對程式碼做的小改動，用來計算變異分數。
_Avoid_: 植入 bug、突變

## 執行與評分

**Harness**:
驅動 Agent 與模型互動、執行工具呼叫的程式。同一個實驗內所有條件共用同一個版本固定的 harness。
_Avoid_: Agent 後端、框架、執行器

**執行器（Runner）**:
我們自寫的程式，負責準備起始快照、啟動 harness、收集軌跡，並把產出交給評分。
_Avoid_: harness、orchestrator、框架

**完成宣稱（Completion Claim）**:
Agent 在執行結束時自己報告的成果。只記錄，不採信，不列入任何指標。
_Avoid_: 結果、驗證結果

**評分（Scoring）**:
在 Agent 之外，以起始快照與參考實作為準，量測一次執行產出的過程。
_Avoid_: 驗證、verify、檢查

**無測試執行（Testless Run）**:
結束時相對起始快照沒有新增任何測試的執行。
_Avoid_: 跳過、失敗執行

## 回溯與復現

**軌跡（Trajectory）**:
一次執行的完整紀錄，包含所有模型訊息、工具呼叫與輸出、檔案變更、用量，以及該次的環境指紋。
_Avoid_: log、transcript、紀錄檔

**環境指紋（Environment Fingerprint）**:
決定一次執行或一次評分結果的全部版本識別：harness 版本、模型 ID、pstack commit、受測系統 commit、容器映像 digest、種子資料。
_Avoid_: 版本資訊、config

**可回溯（Traceable）**:
任一次執行都能從它的軌跡完整還原 Agent 做過的每一步。

**可復現（Reproducible）**:
同一份測試在同一個環境指紋下重新評分，得到相同的測試結果與相同的植入 bug 偵測結果。Agent 的過程與產出不在保證範圍內。
