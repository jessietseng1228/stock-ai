股票 AI 助理 v20.5 Stable｜Learning Engine
日期：2026-07-26

新增：
1. 讀取 ai_recommend_history 已完成的 Day+5 績效。
2. 統計整體、AI 分數層級、Confidence、RR、型態與決策的勝率及平均報酬。
3. 依歷史表現對原始 AI Score 做受控校正，單檔最多加減 5 分。
4. 樣本未達 LEARNING_MIN_SAMPLES（預設 10）時不啟用校正。
5. 新增 /learning_status，可查看學習樣本與分組績效。
6. /scan_top5 回傳 learning_ready、learning_sample_count、learning_min_samples。
7. Top5 顯示本次學習加減分。

部署前：
請先在 Supabase SQL Editor 執行：
sql/260726_v20_5_learning_engine.sql

環境參數（選用）：
LEARNING_MIN_SAMPLES=10
LEARNING_MAX_ADJUSTMENT=5

測試順序：
/health
/learning_status
/update_performance?limit=500
/scan_top5
/top5

注意：
Learning Engine 是歷史統計校正，不是保證獲利的機器學習模型。
