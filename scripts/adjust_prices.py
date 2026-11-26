# -*- coding: utf-8 -*-
"""
還原股價 (Back-adjusted Prices)
================================
FinMind 的 `TaiwanStockPrice` 與 TWSE 原始資料皆為 **未還原** 股價。
個股一旦除權息或股票分割，價格會直接跳空，K 線出現假斷崖，
均線、報酬率與漲跌幅全部失真。

本模組把 **事件日之前** 的 OHLC 乘上還原因子、成交量乘上股數變動倍數，
讓整條序列回到與最新價格相同的基準。

兩層機制，優先順序明確：

  1. **除權息還原（精確）** —— 來源 FinMind `TaiwanStockDividend`。
     有實際配息配股金額，可算出精確因子，涵蓋現金股利與股票股利。

  2. **分割偵測（啟發式，後備）** —— 只在 **套用除權息還原之後** 仍有
     單日 ±25% 以上跳空時才啟動。因為面額變更／股票分割不會出現在
     股利資料集裡，需要這層補網。

> ⚠️ 兩層必須照這個順序，且第二層要對「已還原」的序列判斷，
> 否則同一事件會被調整兩次。
>
> 實例：緯穎 (6669) 2026-09-02 由 7,800 跳到 2,610，
> 早期版本的啟發式判定為「1:3 分割、係數 3.0」。
> 實際上那是 **股票股利 19.8279 元的除權**，配股率 1.98279，
> 精確係數為 **2.98279** —— 啟發式猜的 3.0 有 0.57% 誤差，事件類型也標錯了。
> 對照組：川湖 (2059) 同期 14,340 → 6,505 無單日斷點，屬真實連續下跌，
> 兩層機制都不會動它。
"""

from __future__ import annotations

import json
import time
import urllib.request

API = "https://api.finmindtrade.com/api/v4/data"

# 台股面額 10 元：股票股利 X 元/股 等於每股配 X/10 股
PAR_VALUE = 10.0

OHLC_KEYS = ("open", "max", "min", "close", "spread")

# --- 分割偵測（後備層）參數 ---
CANDIDATE_FACTORS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 20.0]
RATIO_TOLERANCE = 0.04
MIN_MOVE = 0.25
MIN_VOLUME_CONFIRM = 1.5


# ===================================================================
# 第一層：除權息還原
# ===================================================================
def fetch_dividends(stock_id, start_date="2023-01-01", retries=3):
    """抓取個股股利發放紀錄。失敗回傳空清單（呼叫端會自動退回啟發式偵測）。"""
    url = "%s?dataset=TaiwanStockDividend&data_id=%s&start_date=%s" % (
        API, stock_id, start_date)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "quanta-site/1.0"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == 200:
                return payload.get("data") or []
        except Exception as exc:
            print("    [warn] 股利資料 %s 第 %d 次失敗：%s" % (stock_id, attempt + 1, exc))
        time.sleep(2 + attempt * 3)
    return []


def parse_dividend_events(rows):
    """
    把股利紀錄整理成除權息事件清單：
    [{"date": 除權息日, "cash": 現金股利, "stock": 股票股利}]
    同一天的多筆（例如分別申報的盈餘配發與法定公積配發）會合併。
    """
    merged = {}
    for r in rows:
        cash = (r.get("CashEarningsDistribution") or 0) + (r.get("CashStatutorySurplus") or 0)
        stock = (r.get("StockEarningsDistribution") or 0) + (r.get("StockStatutorySurplus") or 0)
        if cash == 0 and stock == 0:
            continue
        # 除息日與除權日通常同一天；只有單邊時取有值的那個
        date = (r.get("CashExDividendTradingDate") or "").strip() \
            or (r.get("StockExDividendTradingDate") or "").strip()
        if not date:
            continue
        acc = merged.setdefault(date, {"date": date, "cash": 0.0, "stock": 0.0})
        acc["cash"] += cash
        acc["stock"] += stock
    return sorted(merged.values(), key=lambda e: e["date"])


def _prev_close(rows, ex_date):
    """取得除權息日之前最後一個交易日的收盤價（用原始未調整序列計算）。"""
    prev = None
    for r in rows:
        if r["date"] >= ex_date:
            break
        prev = r
    return prev["close"] if prev and prev.get("close") else None


def compute_dividend_factors(rows, events):
    """
    以 **原始序列** 計算每個除權息事件的還原因子。
    必須在修改任何價格之前全部算完，否則後面的事件會用到已被縮放的價格。

        配股率 r      = 股票股利 / 10
        除權息參考價  = (前一交易日收盤 - 現金股利) / (1 + r)
        還原因子 f    = 參考價 / 前一交易日收盤

    事件日「之前」的價格乘上 f、成交量乘上 (1 + r)。
    """
    out = []
    first_date = rows[0]["date"] if rows else None
    last_date = rows[-1]["date"] if rows else None

    for ev in events:
        d = ev["date"]
        # 事件必須落在序列區間「內部」才需要調整：
        # 早於或等於首筆 -> 它之前沒有資料；晚於末筆 -> 尚未發生
        if not first_date or d <= first_date or d > last_date:
            continue

        prev_close = _prev_close(rows, d)
        if not prev_close:
            continue

        r = ev["stock"] / PAR_VALUE
        ref = (prev_close - ev["cash"]) / (1.0 + r)
        if ref <= 0:
            continue

        out.append({
            "date": d,
            "kind": "dividend",
            "cash": round(ev["cash"], 4),
            "stock": round(ev["stock"], 4),
            "shareRatio": round(1.0 + r, 6),
            "factor": round(ref / prev_close, 6),
            "prevClose": prev_close,
        })
    return out


# ===================================================================
# 第二層：分割偵測（只對已還原的序列判斷）
# ===================================================================
def _match_factor(ratio):
    for f in CANDIDATE_FACTORS:
        if abs(ratio - f) / f <= RATIO_TOLERANCE:
            return f, "split"
        inv = 1.0 / f
        if abs(ratio - inv) / inv <= RATIO_TOLERANCE:
            return inv, "reverse"
    return None, None


def detect_residual_splits(rows):
    """在已套用除權息還原的序列上，找出仍然存在的跳空（視為股票分割／面額變更）。"""
    events = []
    for i in range(1, len(rows)):
        prev_close = rows[i - 1].get("close")
        close = rows[i].get("close")
        if not prev_close or not close:
            continue
        change = (close - prev_close) / prev_close
        if abs(change) <= MIN_MOVE:
            continue

        factor, kind = _match_factor(prev_close / close)
        if not factor:
            continue

        prev_vol = rows[i - 1].get("Trading_Volume") or 0
        vol = rows[i].get("Trading_Volume") or 0
        vol_ratio = (vol / prev_vol) if prev_vol else 0.0
        if kind == "split" and vol_ratio < MIN_VOLUME_CONFIRM:
            continue
        if kind == "reverse" and (vol_ratio == 0 or vol_ratio > 1.0 / MIN_VOLUME_CONFIRM):
            continue

        events.append({
            "date": rows[i]["date"],
            "kind": kind,
            "factor": round(1.0 / factor, 6) if kind == "split" else round(1.0 / factor, 6),
            "shareRatio": round(factor, 6),
            "changePct": round(change * 100, 2),
            "volumeRatio": round(vol_ratio, 2),
        })
    return events


# ===================================================================
# 套用
# ===================================================================
def _apply(rows, adjustments):
    """
    對每一列套用「該列之後所有事件」的累積因子。
    先算好全部因子再一次套用，可避免事件之間互相污染。
    """
    if not adjustments:
        return rows
    for row in rows:
        price_factor = 1.0
        share_factor = 1.0
        for adj in adjustments:
            if row["date"] < adj["date"]:
                price_factor *= adj["factor"]
                share_factor *= adj.get("shareRatio", 1.0)
        if price_factor != 1.0:
            for k in OHLC_KEYS:
                if row.get(k) is not None:
                    row[k] = round(row[k] * price_factor, 2)
            if row.get("Trading_Volume"):
                row["Trading_Volume"] = int(round(row["Trading_Volume"] * share_factor))
    return rows


def adjust_rows(rows, stock_id=None, dividends=None):
    """
    還原整條日線序列，回傳 (已還原的 rows, 事件清單)。

    stock_id  給定時會自動抓取股利資料（除非已由 dividends 傳入）
    dividends 已取得的股利原始列，可避免重複呼叫 API
    """
    if not rows:
        return rows, []

    events = []

    # --- 第一層：除權息（精確） ---
    if dividends is None and stock_id:
        dividends = fetch_dividends(stock_id)
    if dividends:
        div_events = parse_dividend_events(dividends)
        factors = compute_dividend_factors(rows, div_events)
        if factors:
            _apply(rows, factors)
            events.extend(factors)

    # --- 第二層：殘餘跳空視為股票分割（後備） ---
    residual = detect_residual_splits(rows)
    if residual:
        _apply(rows, residual)
        events.extend(residual)

    events.sort(key=lambda e: e["date"])
    return rows, events


def summarize(events, label=""):
    for ev in events:
        if ev["kind"] == "dividend":
            print("    %s 除權息 %s：現金 %.4f 元、股票 %.4f 元 -> 還原因子 %.6f"
                  % (label, ev["date"], ev["cash"], ev["stock"], ev["factor"]))
        else:
            kind_txt = "股票分割" if ev["kind"] == "split" else "股票合併"
            print("    %s %s %s：殘餘跳空 %.1f%% -> 還原因子 %.6f（量比 %.2fx）"
                  % (label, kind_txt, ev["date"], ev["changePct"], ev["factor"], ev["volumeRatio"]))


def events_meta(events):
    """精簡成要寫進 JSON 的欄位。"""
    meta = []
    for e in events:
        m = {"date": e["date"], "kind": e["kind"], "factor": e["factor"]}
        if e["kind"] == "dividend":
            m["cash"] = e["cash"]
            m["stock"] = e["stock"]
        meta.append(m)
    return meta


# ----------------------------------------------------------------- CLI
def _main():
    import argparse
    import io
    import os

    parser = argparse.ArgumentParser(description="還原股價：除權息與股票分割的回溯調整")
    parser.add_argument("--apply", action="store_true",
                        help="實際寫回檔案（預設只做 dry-run 報告）")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sector_path = os.path.join(base, "data", "sector_stocks.json")
    quanta_path = os.path.join(base, "data", "quanta_latest.json")

    print("還原股價 —— %s\n" % ("套用調整" if args.apply else "DRY-RUN（不寫檔）"))
    total = 0

    with io.open(sector_path, encoding="utf-8") as f:
        sector = json.load(f)
    for s in sector:
        rows, events = adjust_rows(s.get("history") or [], stock_id=s["id"])
        if events:
            total += len(events)
            print("  [%s %s]" % (s["id"], s["name"]))
            summarize(events)
            s["priceAdjustments"] = events_meta(events)
        s.pop("splits", None)   # 取代舊版只處理分割的欄位
        time.sleep(1.2)

    with io.open(quanta_path, encoding="utf-8") as f:
        quanta = json.load(f)
    rows, events = adjust_rows(quanta.get("daily_prices") or [], stock_id="2382")
    if events:
        total += len(events)
        print("  [2382 廣達 全期]")
        summarize(events)
        quanta["priceAdjustments"] = events_meta(events)
    quanta.pop("splits", None)

    if total == 0:
        print("  未偵測到需要還原的事件。")

    if args.apply:
        with io.open(sector_path, "w", encoding="utf-8", newline="") as f:
            json.dump(sector, f, ensure_ascii=False, indent=2)
        with io.open(quanta_path, "w", encoding="utf-8", newline="") as f:
            json.dump(quanta, f, ensure_ascii=False, separators=(",", ":"))
        print("\n已寫回 %d 筆調整。" % total)
    elif total:
        print("\n這是 dry-run，尚未寫檔。確認無誤後加上 --apply 才會實際調整。")


if __name__ == "__main__":
    _main()
