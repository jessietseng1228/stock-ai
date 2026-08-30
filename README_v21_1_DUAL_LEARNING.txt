股票 AI 助理 v21.1｜Dual Learning Engine
日期：2026-08-30
基底：v21.0.2 DIAGNOSTICS

【核心升級】
v21.1 將原本單一 Learning Engine 拆成雙軌：
1. Decision Learning Engine
   - 學習 Base Score / Confidence / RR / Pattern / Decision / Market Regime 對 Day+5 的實績差異。
   - 產生 decision_shadow_adjustment。

2. Factor Learning Engine
   - 學習 trend / momentum / volume / risk / position / technical 六大因子的 High/Low 實績差異。
   - 產生 factor_shadow_adjustment。

3. Dual Learning Gate
   - Decision Guard 與 Factor Guard 必須同時通過，才允許將 Shadow Adjustment 套用為正式 learned_score。
   - 任一引擎未成熟時只觀察，不改正式 Top5 分數。

【安全設計】
- 沿用 v21.0.2 logical sample dedup：scan_date + symbol，同日同股只算一次。
- 沿用 Clean Sample、Day+5 outlier、legacy diagnostics。
- Auto Apply 最低樣本預設 30 筆。
- 最少有效交易日預設 6 日。
- 單一交易日樣本占比預設不可超過 25%。
- Decision + Factor 雙引擎都要有 meaningful signal。
- 總學習校正仍限制於 LEARNING_MAX_ADJUSTMENT（預設 ±3）。
- Decision 子引擎預設最大 ±2；Factor 子引擎預設最大 ±1。

【目前資料狀態的預期行為】
如果部署前 /learning_status 仍只有 4 筆 Clean Sample：
- mode = collecting
- auto_apply_ready = false
- learning_adjustment = 0
- learned_score = base_score
因此升級 v21.1 不會因為新模型直接改變目前正式 Top5。

【新增 /learning_status 重點欄位】
- architecture = dual
- decision_learning
- factor_learning
- dual_learning_gate
- decision_max_adjustment
- factor_max_adjustment

【每支候選股票新增 learning 結果】
- learning_architecture = dual
- decision_shadow_adjustment
- factor_shadow_adjustment
- shadow_adjustment
- shadow_score
- learning_adjustment
- learned_score

【部署後驗證】
1. /health
   version 應為 v21.1-dual-learning
2. /learning_status
   version 應為 Dual Learning Engine v21.1
   architecture 應為 dual
3. 若 clean_sample_count < 10
   mode 應為 collecting，auto_apply_ready 應為 false
4. 執行 /scan_top5?limit=30 測試掃描
   learning_version 應為 Dual Learning Engine v21.1
   未通過 Dual Gate 時，正式 learning_adjustment 必須為 0

【SQL】
本版不需新增 SQL migration。
現有 ai_recommend_history 欄位即可繼續蒐集學習資料。
