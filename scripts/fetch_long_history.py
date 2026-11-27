# -*- coding: utf-8 -*-
"""
長期歷史資料抓取（回測專用）
============================
抓 16 檔個股自 2023 年起的還原日線、三大法人買賣超與外資持股，
寫成 data/history_long.json 供 scripts/backtest_signals.py 使用。

為什麼需要這一支：
  網站日常運作只需要 60 根日線（sector_stocks.json）與 80 日籌碼
  （institutional.json），但回測需要夠長的樣本：
    - 指標暖身就要吃掉 35 根（MACD 的 26+9）
    - MA60 與 60 日高低點再要 60 根
    - 剩下的才是可以產生訊號的區間
  用 60 根日線做回測只會剩下 20 幾個觀察值，比不做還危險 —— 它會給出
  一個看起來像數字的結論，但那個數字沒有任何統計意義。

資料量（實測）：每檔約 940 根日線（2023-01-03 起），三大法人約 4,700 列
（每日三到四個法人別各一列），外資持股約 940 列。

執行：python scripts\\fetch_long_history.py
      加 --stock 2382 可只抓單一檔（除錯用）

注意：本檔案是回測的輸入，**不是網站前端的資料來源**，前端不會讀它。
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adjust_prices import adjust_rows, summarize  # noqa: E402

TPE = timezone(timedelta(hours=8))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')

API = 'https://api.finmindtrade.com/api/v4/data'
START_DATE = '2023-01-01'
REQUEST_DELAY = 1.2          # FinMind 免費額度限流時回 HTTP 402，間隔放寬一點
RETRIES = 3


def fetch(dataset, stock_id, start_date=START_DATE):
    url = '{}?dataset={}&data_id={}&start_date={}'.format(API, dataset, stock_id, start_date)
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            if payload.get('status') != 200:
                raise RuntimeError('status {} {}'.format(payload.get('status'), payload.get('msg')))
            return payload.get('data', [])
        except Exception as e:
            print('    [warn] {} {} 第 {} 次失敗：{}'.format(stock_id, dataset, attempt + 1, e))
            time.sleep(3 + attempt * 5)
    return []


def collapse_institutional(rows):
    """FinMind 的三大法人是「每個法人別一列」，先依日期彙整成單日淨買賣超（張）。

    name 欄位的取值：Foreign_Investor / Foreign_Dealer_Self / Investment_Trust /
    Dealer_self / Dealer_Hedging。外資要把 Foreign_Dealer_Self 併入，
    自營商要把自行買賣與避險兩類相加 —— 與 build_institutional_data.py 一致。
    """
    by_date = {}
    for r in rows:
        d = r.get('date')
        if not d:
            continue
        name = r.get('name') or ''
        net = (float(r.get('buy') or 0) - float(r.get('sell') or 0)) / 1000.0  # 股 -> 張
        slot = by_date.setdefault(d, {'foreign': 0.0, 'trust': 0.0, 'dealer': 0.0})
        if name.startswith('Foreign'):
            slot['foreign'] += net
        elif name == 'Investment_Trust':
            slot['trust'] += net
        elif name.startswith('Dealer'):
            slot['dealer'] += net
    out = []
    for d in sorted(by_date):
        v = by_date[d]
        out.append({
            'date': d,
            'foreign': round(v['foreign']),
            'trust': round(v['trust']),
            'dealer': round(v['dealer']),
            'total': round(v['foreign'] + v['trust'] + v['dealer']),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stock', help='只抓單一股號（除錯用）')
    args = ap.parse_args()

    with open(os.path.join(DATA, 'sector_stocks.json'), 'r', encoding='utf-8') as f:
        sector = json.load(f)
    targets = [(s['id'], s['name']) for s in sector]
    if args.stock:
        targets = [t for t in targets if t[0] == args.stock]

    out = {
        'updated_at': datetime.now(TPE).strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at_tz': '+08:00',
        'startDate': START_DATE,
        'note': '回測專用的長期歷史資料，前端不讀取。股價已還原除權息與分割。',
        'stocks': {},
    }

    for sid, name in targets:
        print('--- {} {} ---'.format(sid, name))
        price = fetch('TaiwanStockPrice', sid)
        time.sleep(REQUEST_DELAY)
        if not price:
            print('    [略過] 取不到日線')
            continue
        price, events = adjust_rows(price, stock_id=sid)
        summarize(events, label='    {} 還原'.format(sid))
        time.sleep(REQUEST_DELAY)

        inst_raw = fetch('TaiwanStockInstitutionalInvestorsBuySell', sid)
        time.sleep(REQUEST_DELAY)
        inst = collapse_institutional(inst_raw)

        hold_raw = fetch('TaiwanStockShareholding', sid)
        time.sleep(REQUEST_DELAY)
        hold = []
        for r in hold_raw:
            ratio = r.get('ForeignInvestmentSharesRatio')
            if r.get('date') and ratio is not None:
                hold.append({'date': r['date'], 'foreignRatio': round(float(ratio), 2)})
        hold.sort(key=lambda x: x['date'])

        # 以欄位陣列（columnar）儲存，比每根一個物件省掉大量重複的鍵名
        out['stocks'][sid] = {
            'name': name,
            'date': [r['date'] for r in price],
            'open': [float(r.get('open') or 0) for r in price],
            'high': [float(r.get('max') or 0) for r in price],
            'low': [float(r.get('min') or 0) for r in price],
            'close': [float(r.get('close') or 0) for r in price],
            'volume': [int(r.get('Trading_Volume') or 0) for r in price],
            'inst': inst,
            'shareholding': hold,
        }
        print('    日線 {} 根（{} ~ {}）／法人 {} 日／持股 {} 日'.format(
            len(price), price[0]['date'], price[-1]['date'], len(inst), len(hold)))

    path = os.path.join(DATA, 'history_long.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(path) / 1024 / 1024
    print('\n[history] 已寫入 data/history_long.json（{} 檔，{:.2f} MB）'.format(
        len(out['stocks']), size))


if __name__ == '__main__':
    main()
