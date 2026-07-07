from typing import List
from stock import analyze_stock, get_stock_data, top5_candidates
from ai import ai_comment


def build_watchlist_report(symbols: List[str]) -> str:
    if not symbols:
        return "📋 目前自選清單是空的。\n請先點「➕ 加股票」加入股票代號。"

    lines = ["📋 自選清單", "────────────"]
    ok = 0
    for idx, s in enumerate(symbols, 1):
        data = get_stock_data(s)
        if data:
            ok += 1
            arrow = "▲" if data["change"] >= 0 else "▼"
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
        arrow = "▲" if data["change"] >= 0 else "▼"
        lines.append(
            f"\n{data['title']}\n"
            f"AI：{data['score']} 分 {data['stars']}｜{data['trend']}\n"
            f"價格：{data['price']:.2f}\n"
            f"漲跌：{arrow} {data['change']:.2f} ({data['change_pct']:.2f}%)\n"
            f"五日：{data['five_pct']:.2f}%\n"
            f"評語：{ai_comment(data)}"
        )

    if valid_count == 0:
        return "☀️ 今日早報\n目前自選股都查不到資料，請確認股票代號。"

    lines.append("\n────────────")
    lines.append("提醒：AI分數是量價模型，不是投資建議。")
    return "\n".join(lines)


def build_top5_report(symbols: List[str]) -> str:
    if not symbols:
        return "🔥 TOP5可買\n目前尚未加入自選股，無法評分。"

    top5 = top5_candidates(symbols)
    if not top5:
        return "🔥 TOP5可買\n目前查不到可評分資料。"

    lines = ["🔥 今日 TOP5｜AI評分", "────────────"]
    for idx, data in enumerate(top5, 1):
        arrow = "▲" if data["change"] >= 0 else "▼"
        reasons = "、".join(data.get("reasons", []))
        lines.append(
            f"{idx}. {data['title']}\n"
            f"   {data['score']} 分 {data['stars']}｜{data['trend']}\n"
            f"   {data['price']:.2f}｜{arrow}{data['change_pct']:.2f}%｜5日 {data['five_pct']:.2f}%\n"
            f"   理由：{reasons}"
        )

    lines.append("\n提醒：這是量價動能評分，不是投資建議。")
    return "\n".join(lines)


def build_single_analysis(symbol: str) -> str:
    return analyze_stock(symbol)
