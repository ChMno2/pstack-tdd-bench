# 正式實驗的受測系統使用 LIMS，Prevention 改為延伸目標

提案原本以 Prevention 校務系統為受測系統。Prevention 的程式碼只能在校內網路存取，GitHub 的雲端 runner 連不進去，把程式碼送到雲端模型也需要系統負責單位同意。因此正式實驗（RQ1 到 RQ5）改在 LIMS 上進行。LIMS 是組員參與開發的公開 repo，後端同樣是 FastAPI 與 SQLAlchemy，原本規劃的測試工具大多能沿用。

## Consequences

- LIMS 固定在 commit `227be16`，資料庫改用 PostgreSQL 16。
- Prevention 階段要另開 private repo，並在校內網路架設 self-hosted runner。它的結果只在 Prevention 內部比較，不和 LIMS 的結果並列。
- LIMS 沒有附授權條款。本 repo 公開含 LIMS 程式碼的內容之前，要先取得 LIMS 團隊同意。
