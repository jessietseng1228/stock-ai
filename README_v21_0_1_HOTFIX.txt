股票 AI 助理 v21.0.1 HOTFIX (2026-08-30)

目的：修正 v21.0 Market Regime 在 Render / 週末可能回傳 TAIEX 0 日、UNKNOWN。

修正內容：
1. TAIEX 先使用 yfinance.download(^TWII, 1y)。
2. 若不足 60 日，改試 yfinance.Ticker(^TWII).history。
3. 若仍不足，fallback 至臺灣證券交易所官方 MI_5MINS_HIST 月歷史資料。
4. 週末與休市日不要求當日行情，自動採最近一個有效交易日。
5. market_regime_meta 新增 market_data_date、source、history_days、source_notes。
6. 不修改 Top5 Decision Filter、Sample Dedup、Learning Guard 與正式 Learning 權重。

驗證：
- /health 應顯示 version = v21.0.1-hotfix
- /scan_top5 回傳 market_regime_meta
- 正常時 market_regime 應為 BULL / NEUTRAL / BEAR
- market_data_date 應為最近有效交易日（週末執行時通常為前一交易日）
- source 可能為 yfinance.download / yfinance.Ticker.history / TWSE.MI_5MINS_HIST

若三個來源都失敗，仍安全回傳 UNKNOWN，不會影響 Top5 原有 Decision Filter。
