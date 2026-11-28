# -*- coding: utf-8 -*-
"""
龍頭個股長期日線（stock.html 專用）
==================================
產出 data/leaders_history.json：6 檔族群龍頭各約 300 個交易日的還原日線，
供個股專頁畫「近 1 個月 ~ 全區間」的量價走勢與均線。

為什麼需要這一支：
  前端原本只有兩種日線來源 ——
    - data/sector_stocks.json：16 檔各 60 根（滾動視窗，畫不出季線與長波段）
    - data/quanta_latest.json：只有廣達一檔有 700+ 根
  其他 5 檔龍頭要比照廣達做專頁，就需要一份夠長的日線。

增量更新（重要）：
  首次執行時從 data/history_long.json（回測用的 2023 年起長期資料）取種，
  之後每天只從 sector_stocks.json 的最新一根補進來，不再打任何 API。
  所以這支腳本**不連網**，可以安全地排在每日更新的最後。

  若 history_long.json 不存在（它已 gitignore，換一台機器就沒有），
  腳本仍可運作：會從 sector_stocks.json 的 60 根開始累積，
  只是前期的歷史較短，跑久了自然會長到上限。

保留天數上限 KEEP_DAYS 設 300：夠畫季線與一年期走勢，檔案也只有幾百 KB。
"""

import json
import os
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')

KEEP_DAYS = 300
OUT = 'leaders_history.json'


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    sector = load('sector_stocks.json')
    if not sector:
        raise SystemExit('找不到 data/sector_stocks.json')

    leaders = [s for s in sector if s.get('isLeader')]
    print('族群龍頭 {} 檔：{}'.format(
        len(leaders), '、'.join('{} {}'.format(s['id'], s['name']) for s in leaders)))

    existing = load(OUT) or {}
    prev_stocks = existing.get('stocks') or {}
    long_hist = load('history_long.json')          # 可能不存在（已 gitignore）
    long_stocks = (long_hist or {}).get('stocks') or {}

    out_stocks = {}
    for s in leaders:
        sid = s['id']
        # 以「日期 -> 單根日線」的字典合併，天然去重且不在意來源順序
        bars = {}

        # 1) 既有檔案（最優先保留，它累積了歷史）
        for b in (prev_stocks.get(sid) or {}).get('bars') or []:
            if b.get('date'):
                bars[b['date']] = b

        # 2) 回測用長期資料（只有第一次或換機器時才派上用場）
        lv = long_stocks.get(sid)
        if lv:
            for i, d in enumerate(lv['date']):
                bars.setdefault(d, {
                    'date': d,
                    'open': lv['open'][i], 'high': lv['high'][i],
                    'low': lv['low'][i], 'close': lv['close'][i],
                    'volume': lv['volume'][i],
                })

        # 3) 今日最新：sector_stocks.json 的 60 根滾動視窗（每日更新的來源）
        for h in (s.get('history') or []):
            if not h.get('date') or not h.get('close'):
                continue
            bars[h['date']] = {
                'date': h['date'],
                'open': float(h.get('open') or h['close']),
                'high': float(h.get('max') or h['close']),
                'low': float(h.get('min') or h['close']),
                'close': float(h['close']),
                'volume': int(h.get('Trading_Volume') or 0),
            }

        ordered = [bars[d] for d in sorted(bars)][-KEEP_DAYS:]
        out_stocks[sid] = {
            'name': s['name'],
            'fullName': s.get('fullName'),
            'bars': ordered,
        }
        print('  {} {}：{} 根（{} ~ {}）'.format(
            sid, s['name'], len(ordered),
            ordered[0]['date'] if ordered else '-',
            ordered[-1]['date'] if ordered else '-'))

    payload = {
        'updated_at': datetime.now(TPE).strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at_tz': '+08:00',
        'keepDays': KEEP_DAYS,
        'note': '族群龍頭的還原日線（除權息與分割已還原），供個股專頁繪圖使用。'
                '本檔為增量累積，不連網。',
        'stocks': out_stocks,
    }
    path = os.path.join(DATA, OUT)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print('\n[leaders] 已寫入 data/{}（{:.1f} KB）'.format(OUT, os.path.getsize(path) / 1024))


if __name__ == '__main__':
    main()
