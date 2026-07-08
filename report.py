from typing import Dict, List, Tuple
from stock import analyze_stock, get_stock_data, top5_candidates
from market_scan import get_saved_or_scan_top5, today_taipei
from ai import ai_comment

DISCLAIMER = "提醒：AI分數是量價模型，不是投資建議。"


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
            f"AI：{data['score']} 分 {data['stars']}｜{data['trend']}\n"
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
        return "🔥 TOP5可買\n今天還沒有市場掃描結果。請先執行 /scan_top5，或等早上 Cron 自動產生。"

    lines = [f"🔥 今日 TOP5可買｜全市場預掃描 {today_taipei()}", "────────────"]
    for idx, data in enumerate(top5, 1):
        arrow = _arrow(data)
        reasons = "、".join(data.get("reasons", []))
        lines.append(
            f"{idx}. {data['title']}\n"
            f"   {data['score']} 分 {data['stars']}｜{data['trend']}\n"
            f"   {data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜5日 {data['five_pct']:.2f}%\n"
            f"   理由：{reasons}"
        )

    lines.append("\n提醒：Top5 由 v17 每日市場掃描結果產生，不使用自選清單。")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


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
            _text(f"AI {data['score']}分 {data['stars']}｜{data['trend']}", "sm", "bold"),
            _text(f"{data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜5日 {data['five_pct']:.2f}%"),
            _text(f"支撐/壓力：{data['support']:.2f} / {data['resistance']:.2f}", "xs", color="#666666"),
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
        return "今日 TOP5", {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [_text(fallback)]}}, fallback

    contents = [
        _text("🔥 今日 TOP5可買", "xl", "bold"),
        _text(f"全市場成交值篩選＋AI評分｜{today_taipei()}", "xs", color="#666666"),
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
    contents = [
        _text(f"📈 {data['title']}", "xl", "bold"),
        _text(f"{data['price']:.2f}｜{arrow}{data['change']:.2f} ({data['change_pct']:.2f}%)", "md", "bold"),
        _text(f"AI：{data['score']}分 {data['stars']}｜{data['trend']}", "sm", "bold"),
        _text(f"五日：{data['five_pct']:.2f}%"),
        _text(f"MA5/10/20：{data['ma5']:.2f} / {data['ma10']:.2f} / {data['ma20']:.2f}"),
        _text(f"支撐：{data['support']:.2f}｜壓力：{data['resistance']:.2f}"),
        _text(f"停損參考：{data['stop_loss']:.2f}"),
        _text("AI理由", "sm", "bold"),
    ]
    contents += [_text(f"✔ {r}", "xs", color="#555555") for r in reasons[:3]]
    contents += [_text(ai_comment(data), "xs", color="#555555"), _text(DISCLAIMER, "xs", color="#888888")]
    flex = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contents}}
    return f"個股分析 {data['symbol']}", flex, fallback
