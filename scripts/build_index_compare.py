# -*- coding: utf-8 -*-
"""
類股指數 vs 大盤強弱對照資料建構
=================================
抓取「電腦及週邊設備類指數」與「發行量加權股價指數（大盤）」的每日收盤，
產出 data/index_compare.json 供首頁的資金輪動強弱對照圖使用。

資料來源：證交所 MI_INDEX（每日收盤行情 - 類股指數）
    https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=IND&response=json

為什麼用這支端點：
  - 單次請求即同時含「大盤」與「類股」兩個指數，不必分兩次抓。
  - FinMind 只有大盤（`TaiwanStockPrice` data_id=TAIEX），**沒有類股指數**。
  - TWSE 不送 CORS 標頭，所以一律在後端（本機或 GitHub Actions）抓好寫成 JSON，
    前端讀同源靜態檔，與盤中報價快照同一套作法。

本腳本為 **增量更新**：已存在於 JSON 的日期不會重抓，
首次建立約需數分鐘，之後每個交易日只會多抓一天。
"""

import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

MI_INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"

SECTOR_NAME = "電腦及週邊設備類指數"
MARKET_NAME = "發行量加權股價指數"

TPE = timezone(timedelta(hours=8))

# 首次建立時的起始日（約一年）
DEFAULT_START = "2026-01-01"

# 禮貌性間隔，避免對證交所造成壓力
REQUEST_DELAY = 0.45


def _num(text):
    """'38,195.43' -> 38195.43；'--' 或空值 -> None"""
    if text is None:
        return None
    t = str(text).replace(",", "").strip()
    if not t or t in ("--", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fetch_day(date_str, retries=3):
    """
    抓取單一交易日的類股指數表。
    回傳 (大盤收盤, 類股收盤)；非交易日或查無資料回傳 (None, None)。
    """
    url = "%s?date=%s&type=IND&response=json" % (MI_INDEX_URL, date_str)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; quanta-sector-site/1.0)",
                "Referer": "https://www.twse.com.tw/",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))

            if payload.get("stat") != "OK":
                return None, None   # 非交易日

            market = sector = None
            for table in payload.get("tables") or []:
                for row in table.get("data") or []:
                    if not row:
                        continue
                    name = str(row[0]).strip()
                    if name == MARKET_NAME and market is None:
                        market = _num(row[1])
                    elif name == SECTOR_NAME and sector is None:
                        sector = _num(row[1])
                if market is not None and sector is not None:
                    break
            return market, sector

        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as exc:
            print("    [warn] %s 第 %d 次失敗：%s" % (date_str, attempt + 1, exc))
            time.sleep(2 + attempt * 3)
    return None, None


def build():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base, "data", "index_compare.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # 既有資料：增量更新，不重抓
    existing = {}
    if os.path.exists(out_path):
        try:
            with io.open(out_path, encoding="utf-8") as f:
                prev = json.load(f)
            for row in prev.get("series") or []:
                existing[row["date"]] = row
            print("已載入既有資料 %d 筆，僅補抓缺少的交易日" % len(existing))
        except Exception as exc:
            print("[warn] 既有檔案讀取失敗，將重新建立：%s" % exc)

    # 以廣達的日線當交易日曆，避免把週末與休市日也打一遍
    calendar = []
    quanta_path = os.path.join(base, "data", "quanta_latest.json")
    if os.path.exists(quanta_path):
        with io.open(quanta_path, encoding="utf-8") as f:
            q = json.load(f)
        calendar = [r["date"] for r in (q.get("daily_prices") or [])
                    if r.get("date", "") >= DEFAULT_START]

    if not calendar:
        # 後備：自行產生日期並由 API 判斷是否為交易日
        d = datetime.strptime(DEFAULT_START, "%Y-%m-%d")
        end = datetime.now(TPE).replace(tzinfo=None)
        while d <= end:
            if d.weekday() < 5:
                calendar.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

    todo = [d for d in calendar if d not in existing]
    print("交易日曆 %d 天，需抓取 %d 天" % (len(calendar), len(todo)))

    fetched = failed = 0
    for i, date_str in enumerate(todo, 1):
        market, sector = fetch_day(date_str.replace("-", ""))
        if market is not None and sector is not None:
            existing[date_str] = {"date": date_str, "market": market, "sector": sector}
            fetched += 1
        else:
            failed += 1
        if i % 25 == 0 or i == len(todo):
            print("  進度 %d/%d（成功 %d、略過 %d）" % (i, len(todo), fetched, failed))
        time.sleep(REQUEST_DELAY)

    series = [existing[k] for k in sorted(existing.keys())]
    if not series:
        print("沒有取得任何資料，不寫檔。")
        return 0

    result = {
        "updated_at": datetime.now(TPE).strftime("%Y-%m-%d %H:%M:%S"),
        "source": "TWSE MI_INDEX (www.twse.com.tw)",
        "sectorName": SECTOR_NAME,
        "marketName": MARKET_NAME,
        "count": len(series),
        "series": series,
    }

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    first, last = series[0], series[-1]
    print("\n完成：%s（%.1f KB，共 %d 筆）" % (out_path, size_kb, len(series)))
    print("  區間 %s ~ %s" % (first["date"], last["date"]))
    print("  類股 %.2f -> %.2f（%+.2f%%）" % (
        first["sector"], last["sector"],
        (last["sector"] / first["sector"] - 1) * 100))
    print("  大盤 %.2f -> %.2f（%+.2f%%）" % (
        first["market"], last["market"],
        (last["market"] / first["market"] - 1) * 100))
    return len(series)


if __name__ == "__main__":
    build()
