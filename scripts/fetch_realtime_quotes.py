# -*- coding: utf-8 -*-
"""
盤中即時報價抓取 (Intraday Quote Snapshot)
==========================================
為什麼需要這支腳本：

FinMind 的 `TaiwanStockPrice` 只有 **日線收盤** 資料，盤中查不到當日報價
（盤中查詢當日會回傳空陣列），所以網站原本顯示的一直是「前一交易日收盤價」。
FinMind 的即時快照端點 `taiwan_stock_tick_snapshot` 需要付費等級。

真正的即時來源是證交所 MIS（`mis.twse.com.tw`），但它 **不送 CORS 標頭**，
瀏覽器從 GitHub Pages 直接呼叫會被擋掉。

解法：由 GitHub Actions 定時執行本腳本，把報價快照寫成 JSON 推到 `data-live`
分支；網頁再從 `raw.githubusercontent.com` 讀取（該網域有
`Access-Control-Allow-Origin: *`，實測可直連），完全繞開 CORS 且不需要後端。

價格取值順序（盤中逐筆撮合下，頂層 `z` 多半是 "-"）：
    z（當前成交價） -> trade.z（最近一筆成交價） -> b 委買首檔 -> o 開盤價
"""

import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

# 16 檔精選個股。3324 雙鴻為櫃買（OTC），其餘為上市（TSE）。
STOCKS = [
    ("2382", "廣達", "tse"), ("6669", "緯穎", "tse"), ("3231", "緯創", "tse"),
    ("2356", "英業達", "tse"), ("2376", "技嘉", "tse"), ("2357", "華碩", "tse"),
    ("2377", "微星", "tse"), ("2059", "川湖", "tse"), ("3017", "奇鋐", "tse"),
    ("3324", "雙鴻", "otc"), ("8210", "勤誠", "tse"), ("2395", "研華", "tse"),
    ("6414", "樺漢", "tse"), ("3706", "神達", "tse"), ("2352", "佳世達", "tse"),
    ("4915", "致伸", "tse"),
]

TPE = timezone(timedelta(hours=8))


def _num(value):
    """MIS 的數值欄位可能是 '-'、'' 或 '281.0000'。"""
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_of_list(value):
    """委買／委賣五檔格式為 '281.0000_280.5000_..._'。"""
    if not value or value == "-":
        return None
    return _num(value.split("_")[0])


def fetch_batch(channels, retries=3):
    """一次查詢多檔。channels 形如 ['tse_2382.tw', 'otc_3324.tw']。"""
    url = "%s?json=1&delay=0&ex_ch=%s&_=%d" % (
        MIS_URL, "|".join(channels), int(time.time() * 1000)
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; quanta-sector-site/1.0)",
                "Referer": "https://mis.twse.com.tw/stock/",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("rtcode") == "0000":
                return payload.get("msgArray") or []
            print("    [warn] MIS rtcode=%s" % payload.get("rtcode"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as exc:
            print("    [warn] 第 %d 次查詢失敗：%s" % (attempt + 1, exc))
        time.sleep(2 + attempt * 3)
    return []


def parse_quote(row):
    """把一筆 MIS 紀錄轉成乾淨的報價物件。"""
    sid = row.get("c")
    if not sid:
        return None, None

    prev_close = _num(row.get("y"))

    price = _num(row.get("z"))
    source = "成交"
    if price is None:
        trade = row.get("trade") or {}
        price = _num(trade.get("z"))
        source = "最近成交"
    if price is None:
        price = _first_of_list(row.get("b"))
        source = "委買"
    if price is None:
        price = _num(row.get("o"))
        source = "開盤"
    if price is None:
        price = prev_close
        source = "昨收"

    spread = None
    pct = None
    if price is not None and prev_close:
        spread = round(price - prev_close, 2)
        pct = round(spread / prev_close * 100, 2)

    quote = {
        "price": price,
        "prevClose": prev_close,
        "spread": spread,
        "pct": pct,
        "open": _num(row.get("o")),
        "high": _num(row.get("h")),
        "low": _num(row.get("l")),
        "limitUp": _num(row.get("u")),
        "limitDown": _num(row.get("w")),
        "volume": int(_num(row.get("v")) or 0),   # 累積成交張數
        "time": row.get("t"),
        "date": row.get("d"),
        "priceSource": source,
    }
    return sid, quote


def build():
    now = datetime.now(TPE)
    print("抓取時間（台北）：%s" % now.strftime("%Y-%m-%d %H:%M:%S"))

    channels = ["%s_%s.tw" % (market, sid) for sid, _, market in STOCKS]
    rows = fetch_batch(channels)

    quotes = {}
    for row in rows:
        sid, quote = parse_quote(row)
        if sid and quote:
            quotes[sid] = quote

    # 補抓：若有個股掛在另一個市場別，改用相反的前綴再試一次
    missing = [(sid, name, market) for sid, name, market in STOCKS if sid not in quotes]
    if missing:
        print("  首輪未取得：%s，改用相反市場別重試" % ", ".join(s for s, _, _ in missing))
        alt = ["%s_%s.tw" % ("otc" if m == "tse" else "tse", s) for s, _, m in missing]
        for row in fetch_batch(alt):
            sid, quote = parse_quote(row)
            if sid and quote:
                quotes[sid] = quote

    name_map = {sid: name for sid, name, _ in STOCKS}
    for sid, q in quotes.items():
        q["name"] = name_map.get(sid, "")

    # 以回傳資料中最新的報價時間作為整份快照的時間戳
    times = [q["time"] for q in quotes.values() if q.get("time")]
    dates = [q["date"] for q in quotes.values() if q.get("date")]
    market_time = max(times) if times else None
    market_date = max(dates) if dates else None
    if market_date and len(market_date) == 8:
        market_date = "%s-%s-%s" % (market_date[:4], market_date[4:6], market_date[6:])

    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at_tz": "Asia/Taipei",
        "marketDate": market_date,
        "marketTime": market_time,
        "source": "TWSE MIS (mis.twse.com.tw)",
        "count": len(quotes),
        "quotes": quotes,
    }

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(base, "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "realtime.json")
    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    print("取得 %d / %d 檔，報價時間 %s %s" % (
        len(quotes), len(STOCKS), market_date, market_time))
    for sid, name, _ in STOCKS:
        q = quotes.get(sid)
        if q:
            print("  %-5s %-5s %10s  %+8s (%+6s%%)  量 %-8s [%s]" % (
                sid, name, q["price"], q["spread"], q["pct"], q["volume"], q["priceSource"]))
        else:
            print("  %-5s %-5s  未取得" % (sid, name))
    print("已寫入 %s" % out_path)

    return len(quotes)


if __name__ == "__main__":
    build()
