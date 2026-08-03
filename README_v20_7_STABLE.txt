股票 AI 助理 v20.7 STABLE
版本日期：2026-08-03

【核心目標】
在 v20.6 Entry Filter 基礎上加入 Decision Engine，讓 Top5 不只看 AI 分數，也綜合進場品質與風險後排序。

【新增功能】
1. Final Score
   Final Score = Learning 後分數 + Entry Quality Bonus - Risk Penalty
   最終限制在 0～100 分，Top5 改依 Final Score 排序。

2. Risk Engine
   評估 RSI、距離 20MA、近 5 日漲幅、ATR、RR、停損距離。
   產出 risk_points、risk_penalty、risk_level、risk_reasons。

3. Entry Quality Bonus
   評估 RR、量能、上揚月線、MACD 動能及進場決策。
   最高加 5 分。

4. LINE Top5 顯示
   顯示 Final、AI 基礎分、Learning、進場加分、風險扣分、風險等級。

5. API 診斷
   /scan_top5 top5 每檔包含：
   learned_score、final_score、risk_points、risk_penalty、risk_level、risk_reasons、entry_quality_bonus、entry_quality_reasons。

【相容性】
- 保留 v20.6 Entry Filter，不建議進場及等待回檔仍不能進 Top5。
- 不需要新增 Supabase 欄位。v20.7 資料封裝於 market_top5_results.trend 的 V20PLAN JSON。
- 舊資料仍可讀取，缺少 v20.7 欄位時會使用既有 score。

【主要修改檔案】
- decision_engine.py（新增）
- market_scan.py
- supabase_db.py
- report.py
- app.py
