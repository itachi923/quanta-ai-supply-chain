# -*- coding: utf-8 -*-
"""
還原股價：股票分割／合併的回溯調整 (Back-adjustment for Stock Splits)
======================================================================
FinMind 的 `TaiwanStockPrice` 與 TWSE 原始資料皆為 **未還原** 股價。
個股一旦進行股票分割（面額分割），分割日當天的價格會直接跳空，
在 K 線圖上形成一道「假斷崖」，均線與報酬率也會全部失真。

本模組偵測這類斷點並把 **分割日之前** 的 OHLC 統一除以還原係數、
成交量乘以還原係數，讓整條序列回到同一個價格基準。

偵測條件（必須同時成立，避免把真實的連續下跌誤判為分割）：
  1. 單日收盤變動幅度超過 ±25%
  2. 價格比值（前一日收盤 / 當日收盤）接近某個常見分割倍數，誤差在 4% 以內
  3. 成交量同步往相反方向放大／縮小（分割後股數變多，成交張數通常同步放大）

已知案例：緯穎 (6669) 於 2026-09-02 由 7,800 跳至 2,610，
比值 2.989 ≈ 1:3 分割、成交量放大 3.81 倍。
對照組：川湖 (2059) 同期 14,340 → 6,505 無單日斷點，屬真實連續下跌，不會被調整。
"""

from __future__ import annotations

# 常見的分割／合併倍數
CANDIDATE_FACTORS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 20.0]

# 比值與候選倍數的容許誤差（4%）
RATIO_TOLERANCE = 0.04

# 觸發偵測的單日最小變動幅度
MIN_MOVE = 0.25

# 分割後成交量應同步放大的最低倍數（反向合併則為縮小）
MIN_VOLUME_CONFIRM = 1.5

OHLC_KEYS = ("open", "max", "min", "close", "spread")


def _match_factor(ratio):
    """把價格比值對應到最接近的常見分割倍數；對不上則回傳 None。"""
    for f in CANDIDATE_FACTORS:
        if abs(ratio - f) / f <= RATIO_TOLERANCE:
            return f, "split"        # 分割：價格變小、股數變多
        inv = 1.0 / f
        if abs(ratio - inv) / inv <= RATIO_TOLERANCE:
            return inv, "reverse"    # 合併：價格變大、股數變少
    return None, None


def detect_splits(rows):
    """
    掃描日線序列，回傳偵測到的分割事件：
    [{"date": 分割日, "factor": 還原係數, "kind": "split"|"reverse", ...}]
    """
    events = []
    for i in range(1, len(rows)):
        prev_close = rows[i - 1].get("close")
        close = rows[i].get("close")
        if not prev_close or not close:
            continue

        change = (close - prev_close) / prev_close
        if abs(change) <= MIN_MOVE:
            continue

        ratio = prev_close / close
        factor, kind = _match_factor(ratio)
        if not factor:
            continue  # 比值對不上常見倍數 → 視為真實漲跌，不調整

        prev_vol = rows[i - 1].get("Trading_Volume") or 0
        vol = rows[i].get("Trading_Volume") or 0
        vol_ratio = (vol / prev_vol) if prev_vol else 0.0

        # 成交量必須往預期方向變化，否則不敢認定為分割
        if kind == "split" and vol_ratio < MIN_VOLUME_CONFIRM:
            continue
        if kind == "reverse" and (vol_ratio == 0 or vol_ratio > 1.0 / MIN_VOLUME_CONFIRM):
            continue

        events.append({
            "date": rows[i]["date"],
            "index": i,
            "factor": round(factor, 4),
            "kind": kind,
            "prevClose": prev_close,
            "close": close,
            "changePct": round(change * 100, 2),
            "volumeRatio": round(vol_ratio, 2),
        })
    return events


def adjust_rows(rows):
    """
    就地回溯調整日線序列，回傳 (已調整的 rows, 偵測到的事件清單)。
    分割日之前的 OHLC 除以累積係數、成交量乘以累積係數，
    使整條序列與最新價格處於同一基準。
    """
    events = detect_splits(rows)
    if not events:
        return rows, []

    # 由最新往回累乘係數：越早的資料需要除以越大的累積倍數
    for ev in events:
        factor = ev["factor"]
        for r in rows[: ev["index"]]:
            for k in OHLC_KEYS:
                if r.get(k) is not None:
                    r[k] = round(r[k] / factor, 2)
            if r.get("Trading_Volume"):
                r["Trading_Volume"] = int(round(r["Trading_Volume"] * factor))
            # Trading_money（成交金額）為價 × 量，分割前後總額不變，毋須調整

    return rows, events


def summarize(events, label=""):
    """把偵測結果印成人看得懂的摘要。"""
    if not events:
        return
    for ev in events:
        kind_txt = "股票分割" if ev["kind"] == "split" else "股票合併"
        print(
            "    %s %s：%s %s -> %s (%.1f%%)，還原係數 %s，量比 %.2fx"
            % (label, kind_txt, ev["date"], ev["prevClose"], ev["close"],
               ev["changePct"], ev["factor"], ev["volumeRatio"])
        )


# ----------------------------------------------------------------- CLI
def _main():
    import argparse
    import io
    import json
    import os

    parser = argparse.ArgumentParser(description="還原股價：偵測並調整股票分割造成的價格斷層")
    parser.add_argument("--apply", action="store_true",
                        help="實際寫回檔案（預設只做 dry-run 報告，不改任何資料）")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sector_path = os.path.join(base, "data", "sector_stocks.json")
    quanta_path = os.path.join(base, "data", "quanta_latest.json")

    mode = "套用調整" if args.apply else "DRY-RUN（不寫檔）"
    print("還原股價掃描 —— %s\n" % mode)

    total = 0

    # --- 16 檔類股資料庫 ---
    with io.open(sector_path, encoding="utf-8") as f:
        sector = json.load(f)
    for s in sector:
        rows, events = adjust_rows(s.get("history") or [])
        if events:
            total += len(events)
            print("  [%s %s]" % (s["id"], s["name"]))
            summarize(events)
            s["splits"] = [
                {"date": e["date"], "factor": e["factor"], "kind": e["kind"]}
                for e in events
            ]

    # --- 廣達 701 日全期 ---
    with io.open(quanta_path, encoding="utf-8") as f:
        quanta = json.load(f)
    rows, events = adjust_rows(quanta.get("daily_prices") or [])
    if events:
        total += len(events)
        print("  [2382 廣達 全期]")
        summarize(events)
        quanta["splits"] = [
            {"date": e["date"], "factor": e["factor"], "kind": e["kind"]}
            for e in events
        ]

    if total == 0:
        print("  未偵測到任何分割斷點，資料無需調整。")

    if args.apply and total:
        with io.open(sector_path, "w", encoding="utf-8", newline="") as f:
            json.dump(sector, f, ensure_ascii=False, indent=2)
        with io.open(quanta_path, "w", encoding="utf-8", newline="") as f:
            json.dump(quanta, f, ensure_ascii=False, separators=(",", ":"))
        print("\n已寫回 %d 筆調整。" % total)
    elif total:
        print("\n這是 dry-run，尚未寫檔。確認無誤後加上 --apply 才會實際調整。")


if __name__ == "__main__":
    _main()
