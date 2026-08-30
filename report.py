from typing import Dict, List, Tuple
from stock import analyze_stock, get_stock_data, top5_candidates
from market_scan import get_saved_or_scan_top5, today_taipei, market_top5_status
from ai import ai_comment, factor_summary, technical_summary, trade_plan, SCORE_VERSION
from supabase_db import get_latest_ai_recommend_history, get_ai_performance_history
from performance_analytics import build_performance_analytics

DISCLAIMER = "提醒：v20.8 採每日正式 Top5 快照；績效統計為歷史驗證，不保證未來獲利，也不是投資建議。"


def _arrow(data: Dict) -> str:
    return "▲" if data.get("change", 0) >= 0 else "▼"


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def build_watchlist_report(symbols: List[str]) -> str:
    if not symbols:
        return "📋 目前自選清單是空的。\n請先點「➕ 加股票」加入股票代號。"

    lines = ["📋 自選清單", "────────────"]
    ok = 0
    for idx, s in enumerate(symbols, 1):
        data = get_stock_data(s)
        if data:
            ok += 1
            arrow = _arrow(data)
            lines.append(
                f"{idx}. {data['title']}\n"
                f"   {data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜{data['stars']}"
            )
        else:
            lines.append(f"{idx}. {s}｜查無資料")

    lines.append("────────────")
    lines.append(f"共 {len(symbols)} 檔，成功取得 {ok} 檔資料")
    return "\n".join(lines)


def build_morning_report(symbols: List[str]) -> str:
    if not symbols:
        return "☀️ 今日早報\n目前尚未加入自選股。\n請先點「➕ 加股票」。"

    lines = ["☀️ 股票 AI 今日早報", "────────────"]
    valid_count = 0

    for s in symbols:
        data = get_stock_data(s)
        if not data:
            lines.append(f"\n{s}\n查無資料，請確認股票代號。")
            continue

        valid_count += 1
        arrow = _arrow(data)
        lines.append(
            f"\n{data['title']}\n"
            f"AI 3.0：{data['score']} 分 {data['stars']}｜{(data.get('trade_plan') or trade_plan(data))['decision']}\n"
            f"價格：{data['price']:.2f}\n"
            f"漲跌：{arrow} {data['change']:.2f} ({data['change_pct']:.2f}%)\n"
            f"五日：{data['five_pct']:.2f}%\n"
            f"支撐/壓力：{data['support']:.2f} / {data['resistance']:.2f}\n"
            f"評語：{ai_comment(data)}"
        )

    if valid_count == 0:
        return "☀️ 今日早報\n目前自選股都查不到資料，請確認股票代號。"

    lines.append("\n────────────")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def build_top5_report(symbols: List[str] = None) -> str:
    top5 = get_saved_or_scan_top5(auto_scan=False)
    if not top5:
        status = market_top5_status()
        scan_date = status.get("scan_date") or today_taipei()
        if status.get("has_result"):
            return (
                f"📭 今日無符合進場條件標的｜掃描日期 {scan_date}\n"
                "────────────\n"
                "今日市場掃描已完成，但沒有股票同時通過進場條件與風險門檻。\n\n"
                "今日建議：保留現金，等待更明確的進場機會。\n\n"
                "提醒：系統不會為了湊滿五檔而加入等待回檔、避免追高或持續觀察的股票。"
            )
        return "⏳ 今日尚未完成市場掃描。請等待正式 /scan_top5_cron 排程完成；/scan_top5 僅供預覽，不會寫入正式結果。"

    result_date = top5[0].get("scan_date") or today_taipei()
    is_today = str(result_date) == str(today_taipei())
    title = "🔥 今日 TOP5可買" if is_today else "📚 最近一次 Top5"
    lines = [f"{title}｜掃描日期 {result_date}", "────────────"]
    for idx, data in enumerate(top5, 1):
        arrow = _arrow(data)
        reasons = "、".join(data.get("reasons", []))
        lines.append(
            f"{idx}. {data['title']}\n"
            f"   Final：{data.get('final_score', data['score'])} 分 {data['stars']}｜{(data.get('trade_plan') or trade_plan(data))['decision']}\n"
            f"   {data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜5日 {data['five_pct']:.2f}%\n"
            f"   理由：{reasons}"
        )

    lines.append("\n提醒：Top5 由 v20.6 Entry Filter + v20.7 Decision Engine 產生，不使用自選清單。")
    lines.append(DISCLAIMER)
    return "\n".join(lines)



def _history_return_text(value) -> str:
    if value is None:
        return "等待中"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "等待中"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def build_ai_history_report() -> str:
    rows = get_latest_ai_recommend_history(limit=5)
    if not rows:
        return "📚 AI推薦歷史\n目前尚無歷史資料，請先執行 /scan_top5。"

    scan_date = str(rows[0].get("scan_date") or "")
    lines = [f"📚 AI推薦歷史｜{scan_date}", "────────────"]
    for row in rows:
        symbol = str(row.get("symbol") or "")
        name = str(row.get("name") or "")
        title = f"{symbol} {name}".strip()
        lines.append(
            f"{int(row.get('rank') or 0)}. {title}｜AI {int(row.get('ai_score') or 0)}\n"
            f"   推薦價：{float(row.get('entry_price') or 0):.2f}\n"
            f"   Day+1：{_history_return_text(row.get('day1_return'))}\n"
            f"   Day+5：{_history_return_text(row.get('day5_return'))}"
        )
    lines.append("────────────")
    lines.append("Day+1、Day+5 依實際交易日計算。")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def build_ai_history_flex() -> Tuple[str, Dict, str]:
    fallback = build_ai_history_report()
    rows = get_latest_ai_recommend_history(limit=5)
    if not rows:
        return "AI推薦歷史", {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [_text(fallback)]}}, fallback

    scan_date = str(rows[0].get("scan_date") or "")
    contents = [
        _text("📚 AI推薦歷史", "xl", "bold"),
        _text(f"最近一次掃描：{scan_date}", "xs", color="#666666"),
    ]
    for row in rows:
        symbol = str(row.get("symbol") or "")
        name = str(row.get("name") or "")
        title = f"{int(row.get('rank') or 0)}. {symbol} {name}".strip()
        contents.append({
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "margin": "md",
            "paddingAll": "12px",
            "backgroundColor": "#F7F7F7",
            "cornerRadius": "10px",
            "contents": [
                _text(title, "md", "bold"),
                _text(f"AI 3.0：{int(row.get('ai_score') or 0)}分｜推薦價 {float(row.get('entry_price') or 0):.2f}", "sm"),
                _text(f"Day+1：{_history_return_text(row.get('day1_return'))}｜Day+5：{_history_return_text(row.get('day5_return'))}", "sm", "bold"),
                _button("分析", f"action=analyze_symbol&symbol={symbol}"),
            ],
        })
    contents.append(_text("Day+1、Day+5 依實際交易日計算。", "xs", color="#666666"))
    contents.append(_text(DISCLAIMER, "xs", color="#888888"))
    flex = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contents}}
    return "AI推薦歷史", flex, fallback


def build_single_analysis(symbol: str) -> str:
    return analyze_stock(symbol)


def _text(contents: str, size: str = "sm", weight: str = "regular", color: str = "#222222", wrap: bool = True) -> Dict:
    return {"type": "text", "text": str(contents), "size": size, "weight": weight, "color": color, "wrap": wrap}


def _button(label: str, data: str) -> Dict:
    return {
        "type": "button",
        "style": "secondary",
        "height": "sm",
        "action": {"type": "postback", "label": label[:20], "data": data, "displayText": label},
    }


def _stock_box(data: Dict, rank: int = 0) -> Dict:
    title = f"{rank}. {data['title']}" if rank else data["title"]
    arrow = _arrow(data)
    plan = data.get("trade_plan") or trade_plan(data)
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "margin": "md",
        "paddingAll": "12px",
        "backgroundColor": "#F7F7F7",
        "cornerRadius": "10px",
        "contents": [
            _text(title, "md", "bold"),
            _text(f"Final {int(data.get('final_score', data['score']) or 0)}分 {data['stars']}｜{plan['decision']}", "sm", "bold"),
            _text(
                f"AI {int(data.get('base_score', data.get('learned_score', data['score'])) or 0)}｜學習 {float(data.get('learning_adjustment', 0) or 0):+g}｜進場 +{int(data.get('entry_quality_bonus', 0) or 0)}｜風險 -{int(data.get('risk_penalty', 0) or 0)}",
                "xs", color="#555555"
            ),
            _text(
                f"風險 {data.get('risk_level', '未評估')}｜信心 {plan['confidence']}%｜型態 {plan['pattern']}",
                "xs", color="#555555"
            ),
            _text(f"{data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜5日 {data['five_pct']:.2f}%"),
            _text(f"買點 {plan['entry_low']:.2f}～{plan['entry_high']:.2f}｜停損 {data.get('stop_loss', 0):.2f}", "xs", color="#555555"),
            _text(f"目標 {plan['target1']:.2f}｜RR 1：{plan['rr']:.2f}", "xs", color="#555555"),
            _button("分析", f"action=analyze_symbol&symbol={data['symbol']}"),
        ],
    }


def build_morning_flex(symbols: List[str]) -> Tuple[str, Dict, str]:
    fallback = build_morning_report(symbols)
    rows = []
    for s in symbols[:10]:
        data = get_stock_data(s)
        if data:
            rows.append(_stock_box(data))

    if not rows:
        return "股票 AI 今日早報", {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [_text(fallback)]}}, fallback

    contents = [
        _text("☀️ 股票 AI 今日早報", "xl", "bold"),
        _text("自選股量價快速掃描", "xs", color="#666666"),
    ] + rows + [_text(DISCLAIMER, "xs", color="#888888")]

    flex = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contents}}
    return "股票 AI 今日早報", flex, fallback


def build_top5_flex(symbols: List[str] = None) -> Tuple[str, Dict, str]:
    fallback = build_top5_report()
    top5 = get_saved_or_scan_top5(auto_scan=False)
    if not top5:
        status = market_top5_status()
        title = "今日無符合標的" if status.get("has_result") else "今日尚未掃描"
        return title, {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [_text(fallback)]}}, fallback

    result_date = top5[0].get('scan_date') or today_taipei()
    is_today = str(result_date) == str(today_taipei())
    heading = "🔥 今日 TOP5可買" if is_today else "📚 最近一次 Top5"
    contents = [
        _text(heading, "xl", "bold"),
        _text(f"全市場成交值篩選＋AI Score 3.0＋Decision Engine v20.7.2｜掃描日期 {result_date}", "xs", color="#666666"),
    ]
    for idx, data in enumerate(top5, 1):
        contents.append(_stock_box(data, idx))
    contents.append(_text(DISCLAIMER, "xs", color="#888888"))
    flex = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contents}}
    return "今日 TOP5", flex, fallback


def build_single_flex(symbol: str) -> Tuple[str, Dict, str]:
    fallback = build_single_analysis(symbol)
    data = get_stock_data(symbol)
    if not data:
        return "個股分析", {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [_text(fallback)]}}, fallback

    arrow = _arrow(data)
    reasons = data.get("reasons", []) or ["資料不足"]
    plan = data.get("trade_plan") or trade_plan(data)
    contents = [
        _text(f"📈 {data['title']}", "xl", "bold"),
        _text(f"{data['price']:.2f}｜{arrow}{data['change']:.2f} ({data['change_pct']:.2f}%)", "md", "bold"),
        _text(f"AI 3.0：{data['score']}分 {data['stars']}｜{plan['decision']}", "sm", "bold"),
        _text("Decision + Learning Engine v21.0｜Dedup・Guard・Regime Shadow", "xs", color="#666666"),
        _text(f"型態：{plan['pattern']}｜Confidence：{plan['confidence']}%", "xs", color="#555555"),
        _text(data.get("factor_summary") or factor_summary(data), "xs", color="#555555"),
        _text(data.get("technical_summary") or technical_summary(data), "xs", color="#555555"),
        _text(f"五日：{data['five_pct']:.2f}%"),
        _text(f"MA5/10/20：{data['ma5']:.2f} / {data['ma10']:.2f} / {data['ma20']:.2f}"),
        _text(f"斜率5/10/20：{data.get('ma5_slope_pct', 0):.2f}% / {data.get('ma10_slope_pct', 0):.2f}% / {data.get('ma20_slope_pct', 0):.2f}%", "xs"),
        _text(f"RSI14：{data.get('rsi14', 0):.1f}｜ATR14：{data.get('atr14', 0):.2f} ({data.get('atr_pct', 0):.1f}%)", "xs"),
        _text(f"MACD：{data.get('macd', 0):.2f}｜Signal：{data.get('macd_signal', 0):.2f}｜Hist：{data.get('macd_hist', 0):.2f}", "xs"),
        _text(f"支撐：{data['support']:.2f}｜壓力：{data['resistance']:.2f}"),
        _text(f"建議買點：{plan['entry_low']:.2f}～{plan['entry_high']:.2f}"),
        _text(f"停損參考：{data['stop_loss']:.2f}"),
        _text(f"第一目標：{plan['target1']:.2f}｜第二目標：{plan['target2']:.2f}"),
        _text(f"風險報酬比：1：{plan['rr']:.2f}"),
        _text("AI理由", "sm", "bold"),
    ]
    contents += [_text(f"✔ {r}", "xs", color="#555555") for r in reasons[:3]]
    contents += [_text(ai_comment(data), "xs", color="#555555"), _text(DISCLAIMER, "xs", color="#888888")]
    flex = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contents}}
    return f"個股分析 {data['symbol']}", flex, fallback


def build_performance_report(limit: int = 2000) -> str:
    rows = get_ai_performance_history(limit=limit)
    a = build_performance_analytics(rows)
    cur, hist, clean = a["current_strategy"], a["all_history"], a["clean_learning"]
    d1, d5 = cur["day1"], cur["day5"]
    lines = [
        "📊 AI Top5 績效驗證｜v21.0", "────────────",
        "【現行策略樣本】",
        f"正式樣本：{cur['total_count']} 筆",
        f"Day+1：{d1['count']} 筆｜勝率 {d1['win_rate']:.1f}%｜均報酬 {d1['avg_return']:+.2f}%",
        f"Day+5：{d5['count']} 筆｜勝率 {d5['win_rate']:.1f}%｜均報酬 {d5['avg_return']:+.2f}%",
        "", "【歷史全部樣本｜僅供參考】",
        f"歷史推薦：{hist['total_count']} 筆",
        f"Day+5：{hist['day5']['count']} 筆｜勝率 {hist['day5']['win_rate']:.1f}%｜均報酬 {hist['day5']['avg_return']:+.2f}%",
        f"Legacy 排除：{a['legacy_count']} 筆",
        "", f"【Clean Learning Sample】{clean['total_count']} 筆",
    ]
    buckets = cur.get("score_buckets") or {}
    if buckets:
        lines.append("現行策略 Base Score → Day+5：")
        for key in ["90+","85-89","80-84","75-79","<75"]:
            st=buckets.get(key)
            if st and st.get("count"):
                lines.append(f"• {key}：{st['count']}筆｜勝率 {st['win_rate']:.1f}%｜均報酬 {st['avg_return']:+.2f}%")
    worst=cur.get("worst_cases") or []
    if worst:
        lines.extend(["", "近期現行策略失敗案例："])
        for r in worst[:3]:
            title=f"{r.get('symbol')} {r.get('name') or ''}".strip()
            lines.append(f"• {r.get('scan_date')} {title}｜Base {r.get('base_score')}｜Day+5 {r.get('day5_return'):+.2f}%")
    lines.extend(["", "⚠️ Legacy 資料不納入 Learning Engine 權重調整。",
                  "v21.0 採 Dedup + Learning Guard；即使 Clean Sample ≥30，未通過資料分散與有效訊號門檻仍維持 Shadow。", "────────────",
                  "提醒：績效統計為歷史驗證，不保證未來獲利，也不是投資建議。"] )
    return "\n".join(lines)
