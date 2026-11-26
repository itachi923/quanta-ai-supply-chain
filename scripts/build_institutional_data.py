# -*- coding: utf-8 -*-
"""
籌碼面資料建構腳本 (Institutional Investors / Chips Data Builder)
================================================================
抓取「電腦及週邊設備類股」16 檔個股的三大法人買賣超與外資持股比例，
產出 data/institutional.json 供 index.html 個股彈窗與 quanta.html 籌碼面專章使用。

資料來源：FinMind 開放 API（開放 CORS、免 token）
  - TaiwanStockInstitutionalInvestorsBuySell : 三大法人每日買賣張數
  - TaiwanStockShareholding                  : 外資持股比例（每日申報）

法人分類對應（FinMind name 欄位 -> 台股慣用三大法人）
  外資   = Foreign_Investor + Foreign_Dealer_Self
  投信   = Investment_Trust
  自營商 = Dealer_self + Dealer_Hedging
單位一律換算為「張」（1 張 = 1000 股），正數為買超、負數為賣超。
"""

import urllib.request
import urllib.error
import json
import time
import os
from datetime import datetime, timedelta

API_BASE = "https://api.finmindtrade.com/api/v4/data"

# 與 sector_stocks.json 一致的 16 檔精選個股
STOCK_IDS = [
    ("2382", "廣達"), ("6669", "緯穎"), ("3231", "緯創"), ("2356", "英業達"),
    ("2376", "技嘉"), ("2357", "華碩"), ("2377", "微星"), ("2059", "川湖"),
    ("3017", "奇鋐"), ("3324", "雙鴻"), ("8210", "勤誠"), ("2395", "研華"),
    ("6414", "樺漢"), ("3706", "神達"), ("2352", "佳世達"), ("4915", "致伸"),
]

# 保留天數：約 120 個日曆天（≈ 80 個交易日），足夠畫近 60 日籌碼走勢
LOOKBACK_DAYS = 150

FOREIGN_KEYS = ("Foreign_Investor", "Foreign_Dealer_Self")
TRUST_KEYS = ("Investment_Trust",)
DEALER_KEYS = ("Dealer_self", "Dealer_Hedging")


def fetch_json(dataset, stock_id, start_date, retries=3):
    """呼叫 FinMind API，失敗時退避重試。"""
    url = (
        f"{API_BASE}?dataset={dataset}"
        f"&data_id={stock_id}&start_date={start_date}"
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "quanta-sector-site/1.0"}
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == 200:
                return payload.get("data") or []
            print(f"    [warn] {dataset} {stock_id} 回應 status={payload.get('status')}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"    [warn] {dataset} {stock_id} 第 {attempt + 1} 次失敗：{exc}")
        time.sleep(2 + attempt * 3)
    return []


def build_daily_net(rows):
    """把 FinMind 的逐筆買賣資料彙總為每日三大法人淨買賣超（張）。"""
    by_date = {}
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        bucket = by_date.setdefault(d, {"foreign": 0, "trust": 0, "dealer": 0})
        net_shares = (r.get("buy") or 0) - (r.get("sell") or 0)
        name = r.get("name")
        if name in FOREIGN_KEYS:
            bucket["foreign"] += net_shares
        elif name in TRUST_KEYS:
            bucket["trust"] += net_shares
        elif name in DEALER_KEYS:
            bucket["dealer"] += net_shares

    daily = []
    for d in sorted(by_date.keys()):
        b = by_date[d]
        foreign = round(b["foreign"] / 1000)
        trust = round(b["trust"] / 1000)
        dealer = round(b["dealer"] / 1000)
        daily.append({
            "date": d,
            "foreign": foreign,
            "trust": trust,
            "dealer": dealer,
            "total": foreign + trust + dealer,
        })
    return daily


def window_sum(daily, key, days):
    """近 N 個交易日累計買賣超。"""
    if not daily:
        return 0
    return sum(d.get(key, 0) for d in daily[-days:])


def build_summary(daily, shareholding):
    """產生卡片用的摘要指標。"""
    latest_ratio = None
    ratio_chg_20 = None
    if shareholding:
        latest_ratio = shareholding[-1].get("foreignRatio")
        if len(shareholding) > 20 and latest_ratio is not None:
            past = shareholding[-21].get("foreignRatio")
            if past is not None:
                ratio_chg_20 = round(latest_ratio - past, 2)

    streak = 0
    for d in reversed(daily):
        v = d.get("foreign", 0)
        if streak == 0:
            if v > 0:
                streak = 1
            elif v < 0:
                streak = -1
            else:
                break
        elif (streak > 0 and v > 0):
            streak += 1
        elif (streak < 0 and v < 0):
            streak -= 1
        else:
            break

    return {
        "lastDate": daily[-1]["date"] if daily else None,
        "foreign1": window_sum(daily, "foreign", 1),
        "foreign5": window_sum(daily, "foreign", 5),
        "foreign20": window_sum(daily, "foreign", 20),
        "trust1": window_sum(daily, "trust", 1),
        "trust5": window_sum(daily, "trust", 5),
        "trust20": window_sum(daily, "trust", 20),
        "dealer1": window_sum(daily, "dealer", 1),
        "dealer5": window_sum(daily, "dealer", 5),
        "dealer20": window_sum(daily, "dealer", 20),
        "total1": window_sum(daily, "total", 1),
        "total5": window_sum(daily, "total", 5),
        "total20": window_sum(daily, "total", 20),
        "foreignRatio": latest_ratio,
        "foreignRatioChg20": ratio_chg_20,
        "foreignStreak": streak,
    }


def build():
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    print(f"抓取區間起始日：{start_date}")

    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startDate": start_date,
        "stocks": {},
    }

    for idx, (sid, name) in enumerate(STOCK_IDS, 1):
        print(f"[{idx}/{len(STOCK_IDS)}] {sid} {name}")

        raw_inst = fetch_json(
            "TaiwanStockInstitutionalInvestorsBuySell", sid, start_date
        )
        daily = build_daily_net(raw_inst)
        time.sleep(1.2)

        raw_hold = fetch_json("TaiwanStockShareholding", sid, start_date)
        shareholding = []
        for r in sorted(raw_hold, key=lambda x: x.get("date") or ""):
            ratio = r.get("ForeignInvestmentSharesRatio")
            if r.get("date") and ratio is not None:
                shareholding.append({
                    "date": r["date"],
                    "foreignRatio": round(float(ratio), 2),
                })
        time.sleep(1.2)

        # 僅保留最近 80 個交易日，控制檔案大小
        daily = daily[-80:]
        shareholding = shareholding[-80:]

        result["stocks"][sid] = {
            "name": name,
            "daily": daily,
            "shareholding": shareholding,
            "summary": build_summary(daily, shareholding),
        }
        print(f"    法人 {len(daily)} 日 / 持股 {len(shareholding)} 筆"
              f" / 外資近20日 {result['stocks'][sid]['summary']['foreign20']:+,} 張")

    target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "institutional.json")
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(target_path) / 1024
    print(f"\n完成：{target_path} ({size_kb:.1f} KB)，共 {len(result['stocks'])} 檔")


if __name__ == "__main__":
    build()
