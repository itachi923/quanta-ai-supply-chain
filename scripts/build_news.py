# -*- coding: utf-8 -*-
"""
類股新聞情報建構
=================
抓取 16 檔個股的相關新聞，彙整成 data/news.json 供情報頁 (news.html) 使用。

資料來源：FinMind `TaiwanStockNews`（免 token）
    https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockNews&data_id=2382&start_date=YYYY-MM-DD

API 的兩個重要行為（實測得出，與直覺不同）：
  1. **只會回傳 `start_date` 當天的新聞**，不是「該日之後的全部」。
  2. 加上 `end_date` 反而回傳 0 筆。
  => 因此必須「逐檔 × 逐日」查詢，無法一次抓一段區間。

為控制請求數，本腳本採 **滾動式封存**：
  - 已存在於 news.json 的 (個股, 日期) 組合不再重抓
  - 只保留最近 KEEP_DAYS 天，舊的自動汰除
  - 每日排程執行時通常只需抓「今天 + 昨天」×16 檔 = 約 32 次請求

去重與合併（兩個層次）：
  1. **跨個股合併**：同一則新聞常同時掛在多檔個股下（例如一篇提到廣達與緯創的報導），
     合併成一筆並記錄所有相關個股代號，前端就能顯示「相關個股：廣達、緯創」。
  2. **跨媒體合併**：同一則報導常被多家媒體轉載，FinMind 的標題結尾會帶上來源名
     （例如「神達董座：…… - 聚財網」「神達董座：…… - 自由時報」），
     若不處理，新聞牆上會出現好幾則只差結尾的重複標題。
     因此以「去掉來源後綴的標題」為鍵合併，並保留所有來源名。
"""

import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.finmindtrade.com/api/v4/data"

STOCKS = [
    ("2382", "廣達"), ("6669", "緯穎"), ("3231", "緯創"), ("2356", "英業達"),
    ("2376", "技嘉"), ("2357", "華碩"), ("2377", "微星"), ("2059", "川湖"),
    ("3017", "奇鋐"), ("3324", "雙鴻"), ("8210", "勤誠"), ("2395", "研華"),
    ("6414", "樺漢"), ("3706", "神達"), ("2352", "佳世達"), ("4915", "致伸"),
]

TPE = timezone(timedelta(hours=8))

# 保留天數（滾動視窗）
KEEP_DAYS = 10

# 禮貌性間隔；FinMind 免費額度被限流時會回 HTTP 402
REQUEST_DELAY = 0.8


def normalize_title(title, source):
    """
    去掉標題結尾的來源後綴，讓同一則報導的多家轉載可以合併。
    FinMind 的標題常見形式：
        「神達董座：AI產業面臨四大挑戰 對明年充滿信心 - 聚財網」
        「……｜股市話題 - 永豐金證券」
    """
    t = (title or "").strip()
    src = (source or "").strip()

    # 優先精確移除「 - 來源名」
    if src and t.endswith(" - " + src):
        t = t[: -(len(src) + 3)]
    else:
        # 後備：移除最後一段「 - xxx」，但只在該段夠短（像來源名而非內文）時才動手
        idx = t.rfind(" - ")
        if idx > 0 and len(t) - idx - 3 <= 12:
            t = t[:idx]

    return t.strip()


def fetch_news(stock_id, date_str, retries=4):
    """
    抓取單一個股、單一日期的新聞。

    回傳 (rows, ok)。
    **必須區分「當天沒有新聞」與「查詢失敗」**：兩者都會得到空清單，
    若一律視為成功而記進已抓清單，被限流的那些日期就再也不會重試，
    該檔個股的新聞會永久消失（實測確實發生過，FinMind 回 HTTP 402 限流）。
    """
    url = "%s?dataset=TaiwanStockNews&data_id=%s&start_date=%s" % (API, stock_id, date_str)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "quanta-sector-site/1.0"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == 200:
                return payload.get("data") or [], True
            print("    [warn] %s %s 回應 status=%s" % (stock_id, date_str, payload.get("status")))
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as exc:
            print("    [warn] %s %s 第 %d 次失敗：%s" % (stock_id, date_str, attempt + 1, exc))
        # 限流時退避時間要拉長，否則連續重試只會繼續撞牆
        time.sleep(3 + attempt * 5)
    return [], False


def build():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base, "data", "news.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    now = datetime.now(TPE)
    today = now.date()
    cutoff = (today - timedelta(days=KEEP_DAYS - 1)).isoformat()

    # --- 讀入既有封存 ---
    items = {}          # key -> 新聞物件
    done_pairs = set()  # 已抓過的 (個股, 日期)
    if os.path.exists(out_path):
        try:
            with io.open(out_path, encoding="utf-8") as f:
                prev = json.load(f)
            for it in prev.get("items") or []:
                if it.get("date", "")[:10] >= cutoff:
                    items[it["key"]] = it
            for pair in prev.get("fetched") or []:
                if pair.split("|")[1] >= cutoff:
                    done_pairs.add(pair)
            print("已載入封存 %d 則新聞、%d 組已抓取紀錄" % (len(items), len(done_pairs)))
        except Exception as exc:
            print("[warn] 既有 news.json 讀取失敗，將重新建立：%s" % exc)

    # --- 自癒：清掉可疑的已抓紀錄 ---
    # 若某檔個股在整個保留視窗內一則新聞都沒有，極可能是當初被限流、
    # 卻被（舊版有缺陷的）程式碼誤記為「已抓過」，導致永遠不再重試。
    # 真的整整十天沒新聞的機率很低，而重抓的成本也很小，因此一律清掉重試。
    stocks_with_news = {s for it in items.values() for s in it.get("stocks", [])}
    suspect = [sid for sid, _ in STOCKS if sid not in stocks_with_news]
    if suspect and done_pairs:
        before = len(done_pairs)
        done_pairs = {p for p in done_pairs
                      if p.split("|")[0] not in suspect}
        cleared = before - len(done_pairs)
        if cleared:
            print("自癒：%s 在視窗內沒有任何新聞，清除 %d 組可疑紀錄以便重試"
                  % ("、".join(suspect), cleared))

    # --- 決定要抓的 (個股, 日期) ---
    dates = [(today - timedelta(days=i)).isoformat() for i in range(KEEP_DAYS)]
    todo = []
    for sid, _ in STOCKS:
        for d in dates:
            pair = "%s|%s" % (sid, d)
            # 今天的新聞會持續增加，所以當天一律重抓
            if pair in done_pairs and d != today.isoformat():
                continue
            todo.append((sid, d, pair))

    print("保留 %d 天（%s ~ %s），需查詢 %d 組" % (KEEP_DAYS, dates[-1], dates[0], len(todo)))

    name_map = {sid: name for sid, name in STOCKS}
    added = 0

    failed_pairs = 0

    for i, (sid, date_str, pair) in enumerate(todo, 1):
        rows, ok = fetch_news(sid, date_str)
        if not ok:
            # 失敗就不要記成已抓，下次執行會自動重試這一組
            failed_pairs += 1
            if i % 20 == 0 or i == len(todo):
                print("  進度 %d/%d（累計 %d 則，失敗 %d 組待重試）"
                      % (i, len(todo), len(items), failed_pairs))
            time.sleep(REQUEST_DELAY)
            continue

        for r in rows:
            raw_title = (r.get("title") or "").strip()
            link = (r.get("link") or "").strip()
            source = (r.get("source") or "").strip()
            if not raw_title:
                continue

            title = normalize_title(raw_title, source)
            key = title            # 以去掉來源後綴的標題為鍵，合併多家轉載
            it = items.get(key)
            if it is None:
                it = {
                    "key": key,
                    "title": title,
                    "link": link,
                    "sources": [],
                    "date": str(r.get("date") or date_str),
                    "stocks": [],
                }
                items[key] = it
                added += 1
            # 同一則新聞可能同時掛在多檔個股下
            if sid not in it["stocks"]:
                it["stocks"].append(sid)
            if source and source not in it["sources"]:
                it["sources"].append(source)
            # 保留最早出現的時間與當時的連結
            d_new = str(r.get("date") or date_str)
            if d_new < it["date"]:
                it["date"] = d_new
                if link:
                    it["link"] = link

        done_pairs.add(pair)
        if i % 20 == 0 or i == len(todo):
            print("  進度 %d/%d（累計 %d 則，失敗 %d 組待重試）"
                  % (i, len(todo), len(items), failed_pairs))
        time.sleep(REQUEST_DELAY)

    # --- 整理輸出 ---
    final = [it for it in items.values() if it["date"][:10] >= cutoff]
    for it in final:
        it["stockNames"] = [name_map.get(s, s) for s in it["stocks"]]
    final.sort(key=lambda x: x["date"], reverse=True)

    # 每檔個股的新聞則數，供前端篩選標籤顯示
    per_stock = {}
    for it in final:
        for s in it["stocks"]:
            per_stock[s] = per_stock.get(s, 0) + 1

    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at_tz": "Asia/Taipei",
        "source": "FinMind TaiwanStockNews",
        "keepDays": KEEP_DAYS,
        "count": len(final),
        "perStock": per_stock,
        "stockNames": name_map,
        "fetched": sorted(p for p in done_pairs if p.split("|")[1] >= cutoff),
        "items": final,
    }

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    print("\n完成：%s（%.1f KB）" % (out_path, size_kb))
    print("  共 %d 則（本次新增 %d 則），區間 %s ~ %s" % (
        len(final), added,
        final[-1]["date"][:10] if final else "-",
        final[0]["date"][:10] if final else "-"))
    print("  有新聞的個股（%d/%d 檔）：%s" % (
        len(per_stock), len(STOCKS),
        ", ".join("%s %s(%d)" % (s, name_map.get(s, ""), c)
                  for s, c in sorted(per_stock.items(), key=lambda x: -x[1]))))

    missing = [("%s %s" % (s, n)) for s, n in STOCKS if s not in per_stock]
    if missing:
        print("  [注意] 以下個股本次沒有任何新聞：%s" % ", ".join(missing))
    if failed_pairs:
        print("  [注意] %d 組查詢失敗（多半是 FinMind 限流），未記入已抓清單，"
              "下次執行會自動重試" % failed_pairs)
    return len(final)


if __name__ == "__main__":
    build()
