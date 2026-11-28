# -*- coding: utf-8 -*-
"""
訊號規則歷史回測
================
用 data/history_long.json（2023 年起的還原日線與籌碼）回放 signal_rules.py
的規則，統計它實際上的勝率、損益與持有天數，產出 data/backtest.json
供 strategy.html 顯示。

執行：python scripts\\backtest_signals.py
      需要先跑過 python scripts\\fetch_long_history.py

====================================================================
回測最容易出錯的地方是「偷看未來」。以下五件事是本腳本的核心防線，
修改時請務必維持，否則回測會變成一份看起來很漂亮的假報告。
====================================================================

1) **指標只用到第 t 根為止**
   每個決策日都重新用 rows[:t+1] 算指標，不是拿整段資料算完再回頭切。

2) **籌碼再延後一天**
   證交所的三大法人買賣超要收盤後才公布，當天盤中不可能知道。
   所以第 t 根的決策只能看到 <= 第 t-1 個交易日的籌碼。
   （線上頁面也是這樣，籌碼日期固定比股價晚一天。）

3) **最早在 t+1 才能成交**
   訊號是用第 t 根收盤算出來的，不可能在第 t 根買到。
   成交模擬從 t+1 根開始，且必須該根的最低價真的觸及掛單價位。

4) **同一根同時觸及停損與停利，一律算停損**
   日線資料看不出盤中先後順序。假設對自己有利（先停利）會系統性高估績效，
   所以一律假設最壞情況。

5) **成本要扣**
   台股買進手續費 0.1425%、賣出手續費 0.1425% + 證交稅 0.3%，
   來回約 0.585%。不扣成本的回測會把一堆本來賠錢的小賺交易算成獲利。

====================================================================
已知限制（輸出的 limitations 欄位也會寫給使用者看）
====================================================================
- 類股相對強度用「16 檔等權報酬」當代理指數，線上頁面用的是證交所真實
  類股指數（index_compare.json 只有 218 個交易日，蓋不住回測區間）。
  本腳本會計算兩者在重疊區間的相關係數並寫進輸出，讓落差可被檢視。
- 單一市場、單一類股、16 檔、約 3.9 年，而且這段期間以 AI 伺服器題材
  為主軸。換一個產業或換一段期間，結果不保證能複製。
- 假設每筆交易等額投入、同一檔同時只持有一個部位、不計滑價與流動性限制。
- 這是**樣本內**回測：規則不是從這段資料最佳化出來的（參數是先寫死的），
  但也沒有獨立的樣本外期間可以驗證。
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signal_rules import (  # noqa: E402
    PROFILES, PROFILE_ORDER, WEIGHTS,
    score_trend, score_momentum, score_chips, score_strength,
    build_indicators, build_chips, build_plan, grade_of,
    sma, pct_change, r1, r2,
)
from build_institutional_data import build_summary  # noqa: E402

TPE = timezone(timedelta(hours=8))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')

# ---- 交易成本（台股現股）
BUY_FEE = 0.001425
SELL_FEE = 0.001425
TAX = 0.003
ROUND_TRIP = BUY_FEE + SELL_FEE + TAX

# ---- 模擬參數
WARMUP = 95          # 指標暖身：MACD 要 35 根、MA60 與 60 日高低點要 60 根
MAX_WAIT = 5         # 訊號成立後最多等 5 根沒成交就撤單
BREAKAWAY = 1.05     # 等待期間若直接噴出超過進場區上緣 5%，放棄追價
GAP_BREAK = 0.97     # 開盤跳空低於進場區下緣 3% 以上，視為設定破壞，不進場


def load(name):
    with open(os.path.join(DATA, name), 'r', encoding='utf-8') as f:
        return json.load(f)


# ===================================================== 類股代理指數
def build_proxy_index(stocks):
    """以 16 檔等權日報酬串成類股代理指數。

    為什麼不用真實類股指數：index_compare.json 只有 218 個交易日，
    回測區間有 940 根，大部分日子沒有指數可對照。
    代理指數的誤差會在 proxyCheck 裡用相關係數揭露。
    """
    all_dates = set()
    for v in stocks.values():
        all_dates.update(v['date'])
    dates = sorted(all_dates)
    pos = {sid: {d: i for i, d in enumerate(v['date'])} for sid, v in stocks.items()}

    level = 100.0
    series = {}
    prev_date = None
    for d in dates:
        if prev_date is not None:
            rets = []
            for sid, v in stocks.items():
                i = pos[sid].get(d)
                j = pos[sid].get(prev_date)
                if i is None or j is None or j >= i:
                    continue
                c0, c1 = v['close'][j], v['close'][i]
                if c0:
                    rets.append(c1 / c0 - 1)
            if rets:
                level *= (1 + sum(rets) / len(rets))
        series[d] = level
        prev_date = d
    return dates, series


def validate_proxy(dates, series):
    """把代理指數與證交所真實類股指數在重疊區間做比較，揭露落差。"""
    try:
        idx = load('index_compare.json')
    except Exception:
        return None
    real = [(p['date'], p['sector']) for p in idx.get('series', []) if p.get('sector')]
    pairs = [(d, s, series[d]) for d, s in real if d in series]
    if len(pairs) < 40:
        return None

    def ret20(vals):
        return [(vals[i] / vals[i - 20] - 1) for i in range(20, len(vals))]

    a = ret20([p[1] for p in pairs])
    b = ret20([p[2] for p in pairs])
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    corr = cov / math.sqrt(va * vb) if va > 0 and vb > 0 else None
    return {
        'overlapDays': len(pairs),
        'ret20Corr': r2(corr * 100) if corr is not None else None,
        'realRet20Avg': r2(ma * 100),
        'proxyRet20Avg': r2(mb * 100),
        'note': '代理指數（16 檔等權）與證交所真實類股指數在重疊的 {} 個交易日，'
                '20 日報酬的相關係數為 {}%。'.format(
                    len(pairs), r2(corr * 100) if corr is not None else '—'),
    }


# ===================================================== 單檔資料檢視
def make_rows(v):
    """把欄位陣列轉成 build_indicators 需要的列狀結構。"""
    return [{
        'date': v['date'][i],
        'close': v['close'][i],
        'max': v['high'][i],
        'min': v['low'][i],
        'Trading_Volume': v['volume'][i],
    } for i in range(len(v['date']))]


def chips_asof(inst, hold, asof):
    """組出第 t 根決策時「實際看得到」的籌碼摘要。

    asof 是第 t-1 個交易日 —— 籌碼比股價晚一天公布（見檔頭第 2 點）。
    summary 直接用 build_institutional_data.build_summary，
    確保與線上頁面的計算語意完全相同。
    """
    daily = [d for d in inst if d['date'] <= asof]
    sh = [h for h in hold if h['date'] <= asof]
    if not daily:
        return None
    return build_chips({'daily': daily, 'shareholding': sh,
                        'summary': build_summary(daily, sh)})


def sector_phase_at(proxy_dates, proxy_series, d):
    """回測區間內的類股階段（簡化版：只看代理指數自身的月線與季線）。"""
    vals = [proxy_series[x] for x in proxy_dates if x <= d]
    if len(vals) < 60:
        return 'unknown'
    ma20, ma60 = sma(vals, 20), sma(vals, 60)
    if vals[-1] > ma20 and ma20 > ma60:
        return 'expand'
    if vals[-1] < ma20 and ma20 < ma60:
        return 'contract'
    return 'range'


# ===================================================== 出場模擬
def simulate_exit(rows, ma20_series, fill_i, fill_px, plan, model):
    """從成交那一根開始逐根模擬出場。回傳 (exit_index, exit_price, reason)。

    model='simple'：碰到停損或第一目標就全部出場，或持有到期以收盤價出場。
    model='staged'：第一目標先出一半，剩下的用 MA20 移動停利或第二目標，
                    也就是頁面上實際寫給使用者的那套紀律。
    同一根同時觸及停損與停利 → 一律算停損（見檔頭第 4 點）。
    """
    stop, t1, t2 = plan['stop'], plan['target1'], plan['target2']
    max_i = min(fill_i + plan['holdDaysMax'], len(rows) - 1)
    below = 0           # 連續收盤跌破 MA20 的根數
    half_done = False
    realized = []       # (權重, 出場價)

    for i in range(fill_i, max_i + 1):
        o = rows[i].get('open', rows[i]['close'])
        h, l, c = rows[i]['max'], rows[i]['min'], rows[i]['close']
        # 成交當根只允許停損、不允許停利。
        # 日線看不出盤中先後，若允許「同一根先買到、又剛好摸到目標」，
        # 等於對停損假設最壞、對停利假設最好 —— 兩邊假設不對稱會高估績效。
        first_bar = (i == fill_i)

        # --- 停損（最優先）
        if l <= stop:
            px = min(o, stop) if o <= stop else stop   # 跳空開低就以開盤價出
            w = 0.5 if half_done else 1.0
            realized.append((w, px))
            return i, blended(realized), ('stop_after_t1' if half_done else 'stop')

        # --- 停利
        if first_bar:
            continue
        if model == 'simple':
            if h >= t1:
                px = max(o, t1) if o >= t1 else t1
                realized.append((1.0, px))
                return i, blended(realized), 'target1'
        else:
            if not half_done and h >= t1:
                px = max(o, t1) if o >= t1 else t1
                realized.append((0.5, px))
                half_done = True
            elif half_done and h >= t2:
                px = max(o, t2) if o >= t2 else t2
                realized.append((0.5, px))
                return i, blended(realized), 'target2'
            # 剩餘部位用 MA20 當移動停利：連 2 根收盤跌破就走
            if half_done:
                m = ma20_series[i]
                if m is not None and c < m:
                    below += 1
                    if below >= 2:
                        j = min(i + 1, len(rows) - 1)
                        realized.append((0.5, rows[j].get('open', rows[j]['close'])))
                        return j, blended(realized), 'ma20_trail'
                else:
                    below = 0

    # --- 時間停損：持有到期仍未觸發任何條件
    last = rows[max_i]['close']
    realized.append((0.5 if half_done else 1.0, last))
    return max_i, blended(realized), ('time_after_t1' if half_done else 'time')


def blended(realized):
    """多段出場的加權平均出場價。"""
    tw = sum(w for w, _ in realized)
    if tw <= 0:
        return None
    return sum(w * p for w, p in realized) / tw


def net_return(entry, exit_px):
    """扣掉手續費與證交稅後的實際報酬率（%）。"""
    cost = entry * (1 + BUY_FEE)
    proceeds = exit_px * (1 - SELL_FEE - TAX)
    return (proceeds / cost - 1) * 100


# ===================================================== 統計
def wilson(wins, n, z=1.96):
    """勝率的 Wilson 95% 信賴區間 —— 樣本小的時候，點估計本身沒有意義。"""
    if n == 0:
        return None, None
    p = wins / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return r1(max(0, centre - margin) * 100), r1(min(1, centre + margin) * 100)


def max_drawdown(trades, price_lookup, timeline, slots=16):
    """每日按市值計價的投組最大回撤（%）。

    不能用「逐筆序列複利」算回撤：那等於假設 788 筆交易是一筆接一筆、
    每次都押上全部資金，算出來會是 10 倍的終值與 85% 的回撤 —— 兩個都是
    模型假象。實際上這些交易在時間上大量重疊（16 檔各自獨立進出）。

    這裡的作法：資金固定切成 16 份（每檔最多持有一個部位），
    每天把已實現損益與未實現損益一起計入，得到真正的每日權益曲線。
    """
    if not trades:
        return None, None, None
    alloc = 1.0 / slots
    opens = {}
    for k, t in enumerate(trades):
        opens.setdefault(t['entryDate'], []).append(k)
    closes = {}
    for k, t in enumerate(trades):
        closes.setdefault(t['exitDate'], []).append(k)

    realized = 0.0
    live = set()
    eq_peak, mdd = 1.0, 0.0
    curve_end = 1.0
    for d in timeline:
        for k in opens.get(d, []):
            live.add(k)
        unreal = 0.0
        for k in live:
            t = trades[k]
            px = price_lookup(t['stockId'], d)
            if px and t['entry']:
                unreal += ((px / t['entry'] - 1) * 100 - ROUND_TRIP * 100) / 100 * alloc
        eq = 1.0 + realized + unreal
        eq_peak = max(eq_peak, eq)
        if eq_peak > 0:
            mdd = max(mdd, (eq_peak - eq) / eq_peak)
        for k in closes.get(d, []):
            if k in live:
                live.discard(k)
                realized += trades[k]['ret'] / 100 * alloc
        curve_end = 1.0 + realized
    return r1(mdd * 100), r1((curve_end - 1) * 100), slots


def summarize(trades, price_lookup=None, timeline=None):
    n = len(trades)
    if n == 0:
        return {'trades': 0}
    rets = [t['ret'] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    lo, hi = wilson(len(wins), n)
    srt = sorted(rets)
    med = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2
    bench = [t['benchRet'] for t in trades]
    # 原本寫成 holdDays <= holdMax 會恆等於 100% —— 模擬本來就截在 holdDaysMax，
    # 那只是在驗證自己的迴圈邊界。改成「有碰到第一目標的交易，是否落在預估區間內」，
    # 這才真的在檢驗預估持有天數準不準。
    hit = [t for t in trades if t['reason'].startswith('target')]
    inrange = [t for t in hit if t['holdMin'] <= t['holdDays'] <= t['holdMax']]
    dd = max_drawdown(trades, price_lookup, timeline) if price_lookup else (None, None, None)
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    phases = {}
    for t in trades:
        p = phases.setdefault(t['phase'], {'n': 0, 'sum': 0.0, 'w': 0})
        p['n'] += 1
        p['sum'] += t['ret']
        if t['ret'] > 0:
            p['w'] += 1
    return {
        'trades': n,
        'wins': len(wins),
        'winRate': r1(len(wins) / n * 100),
        'winRateCI': [lo, hi],
        'avgReturn': r2(sum(rets) / n),
        'medianReturn': r2(med),
        'avgWin': r2(gross_w / len(wins)) if wins else None,
        'avgLoss': r2(sum(losses) / len(losses)) if losses else None,
        'profitFactor': r2(gross_w / gross_l) if gross_l > 0 else None,
        'expectancy': r2(sum(rets) / n),
        'best': r2(max(rets)),
        'worst': r2(min(rets)),
        'avgHoldDays': r1(sum(t['holdDays'] for t in trades) / n),
        'predictedHoldAvg': r1(sum((t['holdMin'] + t['holdMax']) / 2 for t in trades) / n),
        'targetHits': len(hit),
        'holdEstimateHitPct': r1(len(inrange) / len(hit) * 100) if hit else None,
        'maxDrawdown': dd[0],
        'totalReturnPct': dd[1],
        'portfolioSlots': dd[2],
        'benchAvgReturn': r2(sum(bench) / n),
        'alpha': r2(sum(rets) / n - sum(bench) / n),
        'beatBenchPct': r1(sum(1 for t in trades if t['ret'] > t['benchRet']) / n * 100),
        'exitReasons': reasons,
        'byPhase': {k: {'trades': v['n'], 'avgReturn': r2(v['sum'] / v['n']),
                        'winRate': r1(v['w'] / v['n'] * 100)} for k, v in phases.items()},
    }


# ===================================================== 主回測迴圈
def run():
    hist = load('history_long.json')
    stocks = hist['stocks']
    proxy_dates, proxy_series = build_proxy_index(stocks)

    # 每日收盤查表，供投組權益曲線把未平倉部位按市值計價
    close_map = {sid: dict(zip(v['date'], v['close'])) for sid, v in stocks.items()}

    def price_lookup(sid, d):
        return close_map.get(sid, {}).get(d)

    proxy_check = validate_proxy(proxy_dates, proxy_series)

    results = {}
    for model in ('simple', 'staged'):
        results[model] = {pk: [] for pk in PROFILE_ORDER}

    scanned = 0
    signals_fired = 0
    unfilled = 0

    for sid, v in sorted(stocks.items()):
        rows = make_rows(v)
        opens = v['open']
        for i, r in enumerate(rows):
            r['open'] = opens[i]
        n = len(rows)
        inst = v.get('inst') or []
        hold = v.get('shareholding') or []
        closes = v['close']

        # MA20 序列（給移動停利用），每根都只用到該根為止
        ma20_series = [sma(closes[:i + 1], 20) for i in range(n)]

        # 代理指數在各日的 20 日報酬
        pidx = {d: k for k, d in enumerate(proxy_dates)}

        for pk in PROFILE_ORDER:
            prof = PROFILES[pk]
            for model in ('simple', 'staged'):
                t = WARMUP
                while t < n - 1:
                    d = rows[t]['date']
                    ind = build_indicators({'history': rows[:t + 1]})
                    if ind is None:
                        t += 1
                        continue
                    if model == 'simple' and pk == PROFILE_ORDER[0]:
                        scanned += 1

                    # 籌碼只看到前一個交易日
                    ch = chips_asof(inst, hold, rows[t - 1]['date']) if t >= 1 else None

                    k = pidx.get(d)
                    sret20 = None
                    if k is not None and k >= 20:
                        base = proxy_series[proxy_dates[k - 20]]
                        if base:
                            sret20 = (proxy_series[d] / base - 1) * 100

                    ts, _ = score_trend(ind)
                    ms, _ = score_momentum(ind)
                    cs, _ = score_chips(ch)
                    ss, _ = score_strength(ind, sret20)
                    total = (ts * WEIGHTS['trend'] + ms * WEIGHTS['momentum']
                             + cs * WEIGHTS['chips'] + ss * WEIGHTS['strength'])

                    # 與線上 picks 完全相同的入選條件
                    bias = ind['bias20']
                    ok = (total >= prof['minScore']
                          and ts >= 40
                          and (bias is None or bias <= prof['maxBias']))
                    if not ok:
                        t += 1
                        continue

                    plan = build_plan(ind, prof, [r['date'] for r in rows[:t + 1]])
                    if plan is None or plan['needsConfirm']:
                        t += 1
                        continue
                    if model == 'simple' and pk == PROFILE_ORDER[0]:
                        signals_fired += 1

                    # ---- 成交模擬：最早 t+1，必須真的觸及掛單價位
                    fill = None
                    for u in range(t + 1, min(t + 1 + MAX_WAIT, n)):
                        o, lo_, c = rows[u]['open'], rows[u]['min'], rows[u]['close']
                        if o < plan['entryLow'] * GAP_BREAK:
                            break                      # 跳空摜破，設定已失效
                        if lo_ <= plan['entryHigh']:
                            fill = (u, min(o, plan['entryHigh']) if o <= plan['entryHigh']
                                    else plan['entryHigh'])
                            break
                        if c > plan['entryHigh'] * BREAKAWAY:
                            break                      # 直接噴出，不追價
                    if fill is None:
                        if model == 'simple' and pk == PROFILE_ORDER[0]:
                            unfilled += 1
                        t += 1
                        continue

                    fi, fpx = fill
                    ei, epx, reason = simulate_exit(rows, ma20_series, fi, fpx, plan, model)
                    ret = net_return(fpx, epx)
                    bench = net_return(rows[fi]['open'], rows[ei]['close'])

                    results[model][pk].append({
                        'stockId': sid, 'stockName': v.get('name'),
                        'signalDate': d,
                        'entryDate': rows[fi]['date'], 'entry': r2(fpx),
                        'exitDate': rows[ei]['date'], 'exit': r2(epx),
                        'ret': r2(ret), 'benchRet': r2(bench),
                        'reason': reason,
                        'holdDays': ei - fi,
                        'holdMin': plan['holdDaysMin'], 'holdMax': plan['holdDaysMax'],
                        'score': r1(total), 'grade': grade_of(total)['key'],
                        'rr': plan['rr'],
                        'phase': sector_phase_at(proxy_dates, proxy_series, d),
                    })
                    t = ei + 1          # 同一檔同時只持有一個部位
    # ---- 彙整
    out = {
        'updated_at': datetime.now(TPE).strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at_tz': '+08:00',
        'historyUpdatedAt': hist.get('updated_at'),
        'period': {
            'start': proxy_dates[0] if proxy_dates else None,
            'end': proxy_dates[-1] if proxy_dates else None,
            'tradingDays': len(proxy_dates),
            'stocks': len(stocks),
            'warmupBars': WARMUP,
        },
        'costs': {
            'buyFee': BUY_FEE, 'sellFee': SELL_FEE, 'tax': TAX,
            'roundTripPct': r2(ROUND_TRIP * 100),
            'note': '台股現股：買進手續費 0.1425%、賣出手續費 0.1425% + 證交稅 0.3%，'
                    '來回約 {:.3f}%。未計滑價與流動性限制。'.format(ROUND_TRIP * 100),
        },
        'assumptions': {
            'fill': '訊號以第 t 根收盤算出，最早第 t+1 根才可能成交；'
                    '必須該根最低價觸及進場區上緣才算成交，最多等 {} 根。'.format(MAX_WAIT),
            'chipsLag': '第 t 根的決策只看得到第 t-1 個交易日為止的籌碼（證交所出表時程）。',
            'conflict': '同一根同時觸及停損與停利，一律算停損。',
            'position': '同一檔同時只持有一個部位；每筆等額投入。',
            'needsConfirm': '收盤在 MA20 之下的訊號（needsConfirm）不進場，與線上頁面一致。',
        },
        'models': {
            'simple': '碰到停損或第一目標就全部出場，或持有到期以收盤價出場。',
            'staged': '第一目標先出一半，剩餘用 MA20 移動停利（連 2 根收盤跌破）'
                      '或第二目標出場 —— 這是頁面實際寫給使用者的紀律。',
        },
        'proxyCheck': proxy_check,
        'scan': {'barsScanned': scanned, 'signalsFired': signals_fired, 'unfilled': unfilled},
        'results': {},
        'trades': {},
        'limitations': [
            '單一市場、單一類股、{} 檔、約 {:.1f} 年，且這段期間以 AI 伺服器題材為主軸；'
            '換產業或換期間不保證能複製。'.format(len(stocks), len(proxy_dates) / 240),
            '類股相對強度用 16 檔等權代理指數，線上頁面用證交所真實類股指數，'
            '兩者的落差已用相關係數揭露在 proxyCheck。',
            '樣本內回測：規則參數是先寫死的、不是從這段資料最佳化而來，'
            '但也沒有獨立的樣本外期間可以驗證。',
            '未計滑價、漲跌停鎖死無法成交、以及個股流動性不足的情況。',
            '勝率的點估計在樣本數少時意義有限，請一併看信賴區間。',
        ],
    }
    for model in ('simple', 'staged'):
        out['results'][model] = {}
        out['trades'][model] = {}
        for pk in PROFILE_ORDER:
            tr = sorted(results[model][pk], key=lambda x: x['entryDate'])
            out['results'][model][pk] = summarize(tr, price_lookup, proxy_dates)
            # 子集分析：只取「規劃風險報酬比 >= 1.5」的訊號。
            # 回測顯示整體規劃 R:R 平均不到 1，這一欄是用來回答
            #「如果一開始就跳過賠賺比不划算的訊號，結果會不會比較好」。
            hi = [t for t in tr if t.get('rr') is not None and t['rr'] >= 1.5]
            out['results'][model][pk]['rrFiltered'] = summarize(hi, price_lookup, proxy_dates)
            out['trades'][model][pk] = tr

    # 前端只需要統計結果。完整交易明細有 1 MB 以上，分開存成另一個檔
    # （已 gitignore），避免讓每個瀏覽頁面的人都下載它。
    trades = out.pop('trades')
    sample = {}
    for model in trades:
        sample[model] = {}
        for pk in trades[model]:
            sample[model][pk] = trades[model][pk][-12:]   # 只留最近 12 筆當範例
    out['sampleTrades'] = sample

    path = os.path.join(DATA, 'backtest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    full = dict(out)
    full['trades'] = trades
    detail_path = os.path.join(DATA, 'backtest_trades.json')
    with open(detail_path, 'w', encoding='utf-8') as f:
        json.dump(full, f, ensure_ascii=False, separators=(',', ':'))
    print('[backtest] 完整明細 data/backtest_trades.json（{:.1f} KB，不進版控）'.format(
        os.path.getsize(detail_path) / 1024))

    # ---- 主控台摘要
    print('[backtest] 區間 {} ~ {}（{} 個交易日 / {} 檔）'.format(
        out['period']['start'], out['period']['end'],
        out['period']['tradingDays'], out['period']['stocks']))
    if proxy_check:
        print('[backtest] 代理指數檢核：重疊 {} 日，20 日報酬相關係數 {}%'.format(
            proxy_check['overlapDays'], proxy_check['ret20Corr']))
    for model in ('simple', 'staged'):
        print('--- 出場模型：{} ---'.format(model))
        for pk in PROFILE_ORDER:
            s = out['results'][model][pk]
            if not s.get('trades'):
                print('  {:<10} 無交易'.format(PROFILES[pk]['name']))
                continue
            print('  {:<10} {:>4} 筆 | 勝率 {:>5}% (CI {}~{}) | 平均 {:>6}% | '
                  '獲利因子 {:>5} | 對照買進持有 {:>6}% | 超額 {:>6}% | 最大回撤 {:>5}%'.format(
                      PROFILES[pk]['name'], s['trades'], s['winRate'],
                      s['winRateCI'][0], s['winRateCI'][1], s['avgReturn'],
                      s['profitFactor'], s['benchAvgReturn'], s['alpha'], s['maxDrawdown']))
    print('[backtest] 已寫入 data/backtest.json（{:.1f} KB）'.format(
        os.path.getsize(path) / 1024))


if __name__ == '__main__':
    run()
