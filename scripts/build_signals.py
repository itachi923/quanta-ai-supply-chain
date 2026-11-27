# -*- coding: utf-8 -*-
"""
投資策略訊號建構（strategy.html 的資料來源）
==========================================
把站上既有的五份 JSON（日線、籌碼、指數、新聞、收盤快照）換算成
**規則透明**的技術面＋籌碼面訊號，產出 data/signals.json。

設計原則（請接手者務必維持）：
  1. **不連網**。本腳本只讀 data/*.json，不打任何 API。
     所以它必須排在 daily_update.ps1 的最後一步，而且可以隨時重跑。
  2. **每個分數都要能回推到規則**。stocks[].reasons 會把加分/扣分的理由
     逐條寫出來並附上該條的權重，前端直接顯示給使用者看。
     不要為了讓分數「好看」而加入無法解釋的調整項。
  3. **不輸出單一預測點位**。forecast 只給以歷史波動度推算的區間
     （±1σ），並標明是情境推估。絕對不要改成「預測目標價 X 元」。
  4. **資料日期一律標出**。籌碼資料通常比股價晚一天（證交所出表時程），
     兩個日期分開存成 dataDate / instDate，前端必須同時顯示。

為什麼不用機器學習：
  16 檔 × 60 根日線的樣本量遠不足以訓練出有統計意義的模型，
  任何擬合結果都只是在描述這 60 天。規則引擎至少是可檢驗、可解釋的。
"""

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')


def load(name):
    path = os.path.join(DATA, name)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def dump(name, obj):
    path = os.path.join(DATA, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


# ===================================================== 技術指標（純函式）
def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def sma_at(vals, n, offset):
    """offset=0 為最後一根；offset=5 為 5 根前。"""
    end = len(vals) - offset
    if end < n:
        return None
    return sum(vals[end - n:end]) / n


def ema_series(vals, n):
    if not vals:
        return []
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(closes) - n, len(closes)):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - (100 / (1 + rs))


def macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig:
        return None, None, None, None
    ef = ema_series(closes, fast)
    es = ema_series(closes, slow)
    line = [a - b for a, b in zip(ef, es)]
    signal = ema_series(line, sig)
    hist = [a - b for a, b in zip(line, signal)]
    return line[-1], signal[-1], hist[-1], hist[-2]


def stochastic(highs, lows, closes, n=9, d=3):
    """台股慣用 9 日 KD。回傳 (K, D)。"""
    if len(closes) < n + d:
        return None, None
    rsvs = []
    for i in range(len(closes) - (n + d) + 1, len(closes) + 1):
        hh = max(highs[i - n:i])
        ll = min(lows[i - n:i])
        rsvs.append(50.0 if hh == ll else (closes[i - 1] - ll) / (hh - ll) * 100)
    k, dv = 50.0, 50.0
    for r in rsvs:
        k = k * 2 / 3 + r / 3
        dv = dv * 2 / 3 + k / 3
    return k, dv


def atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(len(closes) - n, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs) / n


def stdev(vals):
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def pct_change(series, n):
    if len(series) < n + 1 or series[-n - 1] == 0:
        return None
    return (series[-1] / series[-n - 1] - 1) * 100


def streak(vals):
    """回傳連續同號天數（正為連買、負為連賣）。"""
    if not vals:
        return 0
    sign = 1 if vals[-1] > 0 else (-1 if vals[-1] < 0 else 0)
    if sign == 0:
        return 0
    cnt = 0
    for v in reversed(vals):
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            cnt += 1
        else:
            break
    return cnt * sign


def r2(x):
    return None if x is None else round(x, 2)


def r1(x):
    return None if x is None else round(x, 1)


# ===================================================== 風險屬性參數
# 三種風險屬性只調整「門檻與倍數」，不改變評分規則本身，
# 這樣同一檔股票在三種屬性下的分數一致，只有進出場寬度與入選門檻不同。
PROFILES = {
    'steady': {
        'key': 'steady', 'name': '穩健型', 'desc': '只取高分且不追高，停損寬、目標近',
        'minScore': 65, 'maxPicks': 3,
        'stopAtr': 2.0, 't1Atr': 2.0, 't2Atr': 3.0,
        'maxBias': 8.0,   # 乖離率超過此值視為追高，不列入建議
    },
    'balanced': {
        'key': 'balanced', 'name': '平衡型', 'desc': '分數與位階兼顧，標準停損停利',
        'minScore': 58, 'maxPicks': 5,
        'stopAtr': 1.6, 't1Atr': 2.2, 't2Atr': 3.6,
        'maxBias': 12.0,
    },
    'aggressive': {
        'key': 'aggressive', 'name': '積極型', 'desc': '容許較高位階與較緊停損，目標較遠',
        'minScore': 50, 'maxPicks': 7,
        'stopAtr': 1.3, 't1Atr': 2.5, 't2Atr': 4.2,
        'maxBias': 18.0,
    },
}
PROFILE_ORDER = ['steady', 'balanced', 'aggressive']


# ===================================================== 評分（四大面向）
# reasons 的格式統一為 (tone, text, weight, facet)
#   tone  : bull / bear / watch   前端用來上色
#   weight: 該條規則在所屬面向裡的配分，讓使用者知道這條有多重要
def score_trend(ind):
    """趨勢面：價格與均線的相對位置、均線自身方向。權重 35%。"""
    s, reasons = 0, []
    c, ma5, ma10, ma20, ma60 = ind['close'], ind['ma5'], ind['ma10'], ind['ma20'], ind['ma60']
    if ma20 and c > ma20:
        s += 25
        reasons.append(('bull', '收盤站上 MA20 月線', 25, '趨勢'))
    elif ma20:
        reasons.append(('bear', '收盤跌破 MA20 月線', 25, '趨勢'))
    if ma5 and ma20 and ma5 > ma20:
        s += 20
        reasons.append(('bull', 'MA5 在 MA20 之上（短多排列）', 20, '趨勢'))
    elif ma5 and ma20:
        reasons.append(('bear', 'MA5 跌破 MA20（短空排列）', 20, '趨勢'))
    if ind['ma20Slope'] is not None:
        if ind['ma20Slope'] > 0:
            s += 20
            reasons.append(('bull', 'MA20 近 5 日向上（月線翻揚）', 20, '趨勢'))
        else:
            reasons.append(('bear', 'MA20 近 5 日向下（月線下彎）', 20, '趨勢'))
    if ma60:
        if c > ma60:
            s += 20
            reasons.append(('bull', '收盤站上 MA60 季線', 20, '趨勢'))
        else:
            reasons.append(('bear', '收盤跌破 MA60 季線', 20, '趨勢'))
    elif ma10:
        # 日線不足 60 根時以 MA10 代位，避免這個面向的分母失衡
        if c > ma10:
            s += 20
            reasons.append(('bull', '收盤站上 MA10（季線資料不足，以 MA10 代位）', 20, '趨勢'))
    if ma5 and ma10 and ma5 > ma10:
        s += 15
        reasons.append(('bull', 'MA5 在 MA10 之上', 15, '趨勢'))
    return s, reasons


def score_momentum(ind):
    """動能面：MACD、RSI、KD、短期報酬。權重 25%。"""
    s, reasons = 0, []
    mh, mhp = ind['macdHist'], ind['macdHistPrev']
    rsi14, k, d = ind['rsi14'], ind['kdK'], ind['kdD']
    if mh is not None:
        if mh > 0:
            s += 25
            reasons.append(('bull', 'MACD 柱狀體為正（多方動能）', 25, '動能'))
        else:
            reasons.append(('bear', 'MACD 柱狀體為負（空方動能）', 25, '動能'))
        if mhp is not None and mh > mhp:
            s += 15
            reasons.append(('bull', 'MACD 柱狀體放大（動能增強）', 15, '動能'))
        elif mhp is not None:
            reasons.append(('bear', 'MACD 柱狀體收縮（動能減弱）', 15, '動能'))
    if rsi14 is not None:
        txt = '{:.0f}'.format(rsi14)
        if 50 <= rsi14 <= 70:
            s += 25
            reasons.append(('bull', 'RSI ' + txt + ' 位於 50~70 健康多方區', 25, '動能'))
        elif 70 < rsi14 <= 80:
            s += 12
            reasons.append(('watch', 'RSI ' + txt + ' 偏高，短線易震盪', 25, '動能'))
        elif rsi14 > 80:
            reasons.append(('bear', 'RSI ' + txt + ' 過熱，追高風險大', 25, '動能'))
        elif 40 <= rsi14 < 50:
            s += 12
            reasons.append(('watch', 'RSI ' + txt + ' 位於多空分界，方向未明', 25, '動能'))
        elif 30 <= rsi14 < 40:
            s += 6
            reasons.append(('bear', 'RSI ' + txt + ' 偏弱', 25, '動能'))
        else:
            s += 10
            reasons.append(('watch', 'RSI ' + txt + ' 超賣，屬反彈候選而非趨勢做多', 25, '動能'))
    if k is not None and d is not None:
        kd = 'K {:.0f} / D {:.0f}'.format(k, d)
        if k > d:
            s += 20
            reasons.append(('bull', 'KD 多方交叉（' + kd + '）', 20, '動能'))
        else:
            reasons.append(('bear', 'KD 空方交叉（' + kd + '）', 20, '動能'))
    if ind['ret5'] is not None:
        if ind['ret5'] > 0:
            s += 15
            reasons.append(('bull', '近 5 日報酬 {:+.1f}%'.format(ind['ret5']), 15, '動能'))
        else:
            reasons.append(('bear', '近 5 日報酬 {:+.1f}%'.format(ind['ret5']), 15, '動能'))
    return s, reasons


def score_chips(ch):
    """籌碼面：三大法人買賣超與外資持股變化。權重 25%。"""
    s, reasons = 0, []
    if ch is None:
        return 50, [('watch', '查無籌碼資料，此面向以中性 50 分計', 0, '籌碼')]
    if ch['foreign5'] is not None:
        if ch['foreign5'] > 0:
            s += 25
            reasons.append(('bull', '外資近 5 日買超 {:,.0f} 張'.format(ch['foreign5']), 25, '籌碼'))
        else:
            reasons.append(('bear', '外資近 5 日賣超 {:,.0f} 張'.format(abs(ch['foreign5'])), 25, '籌碼'))
    if ch['trust5'] is not None:
        if ch['trust5'] > 0:
            s += 20
            reasons.append(('bull', '投信近 5 日買超 {:,.0f} 張'.format(ch['trust5']), 20, '籌碼'))
        else:
            reasons.append(('bear', '投信近 5 日賣超 {:,.0f} 張'.format(abs(ch['trust5'])), 20, '籌碼'))
    if ch['total20'] is not None:
        if ch['total20'] > 0:
            s += 20
            reasons.append(('bull', '三大法人近 20 日合計買超 {:,.0f} 張'.format(ch['total20']), 20, '籌碼'))
        else:
            reasons.append(('bear', '三大法人近 20 日合計賣超 {:,.0f} 張'.format(abs(ch['total20'])), 20, '籌碼'))
    if ch['foreignRatioChg20'] is not None:
        if ch['foreignRatioChg20'] > 0:
            s += 15
            reasons.append(('bull', '外資持股比 20 日增加 {:+.2f} 個百分點'.format(ch['foreignRatioChg20']), 15, '籌碼'))
        else:
            reasons.append(('bear', '外資持股比 20 日減少 {:+.2f} 個百分點'.format(ch['foreignRatioChg20']), 15, '籌碼'))
    if ch['foreign1'] is not None and ch['foreign1'] > 0:
        s += 10
        reasons.append(('bull', '外資最新交易日買超 {:,.0f} 張'.format(ch['foreign1']), 10, '籌碼'))
    if ch['trustStreak'] is not None and ch['trustStreak'] >= 3:
        s += 10
        reasons.append(('bull', '投信連 {} 日買超'.format(ch['trustStreak']), 10, '籌碼'))
    elif ch['trustStreak'] is not None and ch['trustStreak'] <= -3:
        reasons.append(('bear', '投信連 {} 日賣超'.format(abs(ch['trustStreak'])), 10, '籌碼'))
    return s, reasons


def score_strength(ind, sector_ret20):
    """相對強度：與類股指數比較、60 日區間位階、量能。權重 15%。"""
    s, reasons = 0, []
    if ind['ret20'] is not None and sector_ret20 is not None:
        rsv = ind['ret20'] - sector_ret20
        if rsv > 0:
            s += 40
            reasons.append(('bull', '近 20 日贏類股指數 {:+.1f} 個百分點'.format(rsv), 40, '相對強度'))
        else:
            reasons.append(('bear', '近 20 日輸類股指數 {:+.1f} 個百分點'.format(rsv), 40, '相對強度'))
    pos = ind['pricePos60']
    if pos is not None:
        ptxt = '{:.0f}%'.format(pos * 100)
        if pos >= 0.7:
            s += 30
            reasons.append(('bull', '股價位於 60 日區間 ' + ptxt + ' 高檔（強勢）', 30, '相對強度'))
        elif pos >= 0.5:
            s += 20
            reasons.append(('watch', '股價位於 60 日區間 ' + ptxt + ' 中上', 30, '相對強度'))
        elif pos >= 0.3:
            s += 10
            reasons.append(('watch', '股價位於 60 日區間 ' + ptxt + ' 中下', 30, '相對強度'))
        else:
            reasons.append(('bear', '股價位於 60 日區間 ' + ptxt + ' 低檔', 30, '相對強度'))
    if ind['ret20'] is not None:
        if ind['ret20'] > 0:
            s += 20
            reasons.append(('bull', '近 20 日報酬 {:+.1f}%'.format(ind['ret20']), 20, '相對強度'))
        else:
            reasons.append(('bear', '近 20 日報酬 {:+.1f}%'.format(ind['ret20']), 20, '相對強度'))
    if ind['volRatio'] is not None:
        if ind['volRatio'] >= 1.0:
            s += 10
            reasons.append(('bull', '成交量為 20 日均量 {:.2f} 倍（量能有承接）'.format(ind['volRatio']), 10, '相對強度'))
        else:
            reasons.append(('watch', '成交量僅 20 日均量 {:.2f} 倍（量能偏縮）'.format(ind['volRatio']), 10, '相對強度'))
    return s, reasons


WEIGHTS = {'trend': 0.35, 'momentum': 0.25, 'chips': 0.25, 'strength': 0.15}

GRADES = [
    (72, 'strong',  '強勢偏多', '優先觀察進場'),
    (60, 'good',    '中性偏多', '可分批布局'),
    (48, 'neutral', '中性整理', '觀望為宜'),
    (36, 'weak',    '中性偏弱', '減碼或暫避'),
    (0,  'bad',     '弱勢',     '建議回避'),
]


def grade_of(total):
    for lo, key, label, action in GRADES:
        if total >= lo:
            return {'key': key, 'label': label, 'action': action}
    return {'key': 'bad', 'label': '弱勢', 'action': '建議回避'}


# ===================================================== 進出場計畫
def trading_days_later(dates, n):
    """以最後一個交易日為基準，用 5/7 的週比例把交易日換算成日曆日期。"""
    if not dates:
        return None
    last = datetime.strptime(dates[-1], '%Y-%m-%d')
    return (last + timedelta(days=int(round(n * 7 / 5)))).strftime('%Y-%m-%d')


def build_plan(ind, prof, dates):
    """以 ATR 與 MA20 推導參考進場區、停損、停利與預估持有天數。

    刻意不給「單一買點」：台股跳動大，單一價位實務上常常掛不到，
    所以一律給區間，並把觸發條件寫成文字讓使用者自己判斷。
    """
    c, ma20, a = ind['close'], ind['ma20'], ind['atr14']
    ma60 = ind['ma60']
    if not a or not ma20 or not c:
        return None
    above = c > ma20
    if above:
        # 順勢：等回測不追高。下緣取 MA20 與近 10 日低點的較高者。
        low10 = ind['low10'] or ma20
        entry_low = max(ma20, low10)
        entry_high = min(c * 1.01, entry_low + 0.8 * a)
        if entry_high <= entry_low:
            entry_high = entry_low * 1.012
        trigger = '股價回測 NT$ {:.1f}~{:.1f} 區間、且回測當日成交量縮小至 20 日均量以下時分批進場；若直接跳空向上不回測，則不追價。'.format(entry_low, entry_high)
    else:
        # 逆勢：必須先站回月線才談進場，避免接刀
        entry_low = ma20 * 0.99
        entry_high = ma20 * 1.015
        trigger = '目前收盤在 MA20 之下，屬於等待訊號轉強的狀態。須等到「收盤站回 MA20（NT$ {:.1f}）並連續 2 個交易日守住」才視為進場條件成立，在 NT$ {:.1f}~{:.1f} 區間分批進場。'.format(ma20, entry_low, entry_high)
    entry_mid = (entry_low + entry_high) / 2
    stop = entry_low - prof['stopAtr'] * a
    # 停損上限以「進場中值」為基準（使用者實際的成本基準），
    # 不是以下緣為基準 —— 以下緣算會讓實際 stopPct 突破 12%（高波動股曾出現 -14.7%）。
    stop = max(stop, entry_mid * 0.88)
    # 第一目標要認壓力區：前波高點就在上方時，拿 ATR 硬推出一個更遠的目標
    # 等於假設它會一次穿越壓力，實務上多半先在前高遇到賣壓。
    # 壓力區候選：取「位在進場中值之上、又還沒超過 ATR 推算目標」的最近一個。
    # 下跌段裡 60 日高點往往遠在天邊，真正的第一道壓力通常是季線或月線，
    # 只看 60 日高點會讓每檔的目標距離都等於 ATR 倍數，預估天數就失去個股差異。
    # 只採計 60 日高點與季線這兩種真實壓力。
    # 不要把 MA20 加一個百分比當目標 —— 跌破月線的個股進場區本身就落在月線上，
    # 那樣算出來的目標只距進場 2~3%，風險報酬比會掉到 0.2 幾，是沒有意義的交易。
    atr_t1 = entry_mid + prof['t1Atr'] * a
    high60 = ind['high60'] or 0
    cands = []
    if high60:
        cands.append((high60, '前波 60 日高點'))
    if ma60:
        cands.append((ma60, 'MA60 季線'))
    # 壓力必須距進場中值至少 1 個 ATR，否則一天的正常振幅就吃掉整段獲利空間
    floor_t1 = entry_mid + 1.0 * a
    near = [(v, lbl) for v, lbl in cands if floor_t1 < v < atr_t1]
    tight = [(v, lbl) for v, lbl in cands if entry_mid * 1.005 < v <= floor_t1]
    tight_note = None
    if near:
        v, lbl = min(near, key=lambda x: x[0])
        t1 = v
        t1_basis = '{} NT$ {:.1f} —— 這是上方第一道壓力，先在此停利一半'.format(lbl, v)
    else:
        t1 = atr_t1
        if tight:
            v, lbl = min(tight, key=lambda x: x[0])
            tight_note = '{} NT$ {:.1f} 距進場不到 1 個 ATR，上方壓力很近，突破前獲利空間有限。'.format(lbl, v)
            t1_basis = ('進場中值加 {:.1f} 倍 ATR；但請注意 {}'
                        .format(prof['t1Atr'], tight_note))
        else:
            t1_basis = '進場中值加 {:.1f} 倍 ATR（上方 60 日內無明顯壓力可參考）'.format(prof['t1Atr'])
    t2 = max(high60 * 1.03, entry_mid + prof['t2Atr'] * a)
    risk = entry_mid - stop
    rr = (t1 - entry_mid) / risk if risk > 0 else None
    # 預估到達第一目標的交易日數：趨勢行進中淨推進約每日 0.4 個 ATR
    # （不是單日振幅，是扣掉來回震盪後的淨位移）
    span = (t1 - entry_mid) / (a * 0.4) if a > 0 else None
    hold_min = max(4, int(math.ceil(span))) if span else 10
    hold_max = min(60, int(round(hold_min * 2.2)))
    return {
        'profile': prof['key'],
        'entryLow': r1(entry_low), 'entryHigh': r1(entry_high), 'entryMid': r1(entry_mid),
        'trigger': trigger,
        'stop': r1(stop), 'stopPct': r1((stop / entry_mid - 1) * 100),
        'target1': r1(t1), 'target1Pct': r1((t1 / entry_mid - 1) * 100), 'target1Basis': t1_basis,
        'target2': r1(t2), 'target2Pct': r1((t2 / entry_mid - 1) * 100),
        'rr': r2(rr),
        # 風險報酬比低於 1.5 時明確標出：這種交易即使勝率不差也不容易長期獲利，
        # 不要只因為「分數高」就忽略賠賺比例。
        'rrWarning': (rr is not None and rr < 1.5),
        'tightResistance': tight_note,
        'atr': r2(a),
        'atrPct': r2(a / entry_mid * 100),
        'volatile': (a / entry_mid * 100) >= 5.0,
        'holdDaysMin': hold_min, 'holdDaysMax': hold_max,
        'reviewBy': trading_days_later(dates, hold_max),
        'needsConfirm': not above,
        'exitRules': [
            '收盤跌破停損價 NT$ {:.1f} → 當日或隔日開盤無條件出場，不等反彈。'.format(stop),
            '觸及第一目標 NT$ {:.1f} → 先減碼一半，剩餘改用 MA20 當移動停利（跌破就走）。'.format(t1),
            '觸及第二目標 NT$ {:.1f} → 全部了結，不留倉過高位階。'.format(t2),
            '連續 2 個交易日收盤跌破 MA20（目前 NT$ {:.1f}）→ 趨勢條件已失效，減碼。'.format(ma20),
            'MACD 柱狀體由正翻負 → 動能轉空，減碼。',
            '外資連 3 個交易日賣超 → 籌碼條件失效，減碼。',
            '持有超過 {} 個交易日（約至 {}）仍未觸及第一目標 → 資金效率不佳，換股處理。'.format(hold_max, trading_days_later(dates, hold_max)),
        ],
    }


def build_forecast(ind, closes):
    """以歷史波動度推估未來 20 交易日的波動區間（非預測點位）。"""
    if len(closes) < 22:
        return None
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(len(closes) - 20, len(closes))]
    sd = stdev(rets)
    if sd is None:
        return None
    sigma20 = sd * math.sqrt(20)
    c = closes[-1]
    return {
        'sigmaDaily': r2(sd * 100),
        'sigma20': r2(sigma20 * 100),
        'band68Low': r1(c * (1 - sigma20)), 'band68High': r1(c * (1 + sigma20)),
        'band90Low': r1(c * (1 - 1.645 * sigma20)), 'band90High': r1(c * (1 + 1.645 * sigma20)),
        'note': '以近 20 日實際日波動度年化推算的統計區間（68% / 90% 信賴區間），'
                '代表「若波動型態不變」的合理震盪範圍，不是方向預測，也不保證不會超出。',
    }


# ===================================================== 當日事件警示
NEWS_BULL = ['法說', '新高', '大單', '訂單', '擴產', '漲價', '調升', '目標價', '買進', '看好',
             '成長', '創高', '得標', '合作', '出貨', '營收創', '受惠', '量產', '拉貨', '急單',
             '增產', '轉單', '回升', '題材', '認證', '打入', '供應']
NEWS_BEAR = ['下修', '衰退', '降評', '賣出', '看壞', '利空', '裁員', '火災', '罰', '訴訟',
             '召回', '砍單', '庫存', '跌價', '警告', '虧損', '減產', '停工', '延後', '流失',
             '殺價', '疑慮', '下滑', '轉弱', '出貨不如']
NEWS_NOTE = ['財報', '營收', '除息', '除權', '法說會', '董事會', '股利', '增資', '減資',
             '併購', '分割', '上市', '財測']

SEV_RANK = {'high': 3, 'medium': 2, 'low': 1}


def build_events(ind, ch, news_today):
    """產出當日需要立刻注意的事件。只收「今天才成立」的變化，不收長期狀態。"""
    ev = []

    def add(sev, direction, title, detail):
        ev.append({'severity': sev, 'direction': direction, 'title': title, 'detail': detail})

    pct = ind['pct']
    if pct is not None:
        if pct >= 9:
            add('high', 'bullish', '接近漲停（{:+.2f}%）'.format(pct),
                '單日漲幅已接近 10% 漲停板，追價風險極高。已持有者可考慮分批獲利了結，未持有者不宜在漲停附近追進。')
        elif pct >= 5:
            add('high', 'bullish', '單日大漲 {:+.2f}%'.format(pct),
                '出現明顯買盤。需確認是否伴隨放量與法人買超，若只有價漲量縮，追高容易套在短線高點。')
        elif pct <= -9:
            add('high', 'bearish', '接近跌停（{:+.2f}%）'.format(pct),
                '單日跌幅已接近 10% 跌停板。多半有具體利空，請先查明原因再決定；不要在跌停附近搶反彈。')
        elif pct <= -5:
            add('high', 'bearish', '單日大跌 {:+.2f}%'.format(pct),
                '賣壓沉重。若同時跌破停損價或 MA20，依紀律應先減碼，不要凹單等反彈。')
    if ind['volRatio'] and ind['volRatio'] >= 2.0:
        d = 'bullish' if (pct or 0) > 0 else ('bearish' if (pct or 0) < 0 else 'neutral')
        add('medium', d, '爆量 {:.1f} 倍'.format(ind['volRatio']),
            '成交量達 20 日均量的 {:.1f} 倍。放量上漲通常代表資金進場，放量下跌則常是出貨訊號，方向要搭配當日漲跌幅一起看。'.format(ind['volRatio']))
    if ind['high60'] and ind['close'] >= ind['high60'] * 0.999:
        add('high', 'bullish', '創 60 日新高',
            '股價突破近 3 個月最高點，壓力區已被消化，上方沒有套牢賣壓。但突破後常有回測，追價前宜等回測確認。')
    if ind['low60'] and ind['close'] <= ind['low60'] * 1.001:
        add('high', 'bearish', '創 60 日新低',
            '股價跌破近 3 個月最低點，為明確的弱勢訊號。不要以「跌深了」為理由進場，趨勢未轉強前應迴避。')
    if ind['ma20'] and ind['prevClose']:
        if ind['prevClose'] >= ind['ma20'] > ind['close']:
            add('medium', 'bearish', '今日失守 MA20 月線',
                '由月線之上跌到之下，是短線趨勢轉弱的第一個訊號。觀察明日能否立刻收復，連 2 日站不回去就該減碼。')
        elif ind['prevClose'] < ind['ma20'] <= ind['close']:
            add('medium', 'bullish', '今日站回 MA20 月線',
                '重新站上月線，短線轉強的第一步。須連續 2 個交易日守住才算確立，單日假突破很常見。')
    if ind['macdHist'] is not None and ind['macdHistPrev'] is not None:
        if ind['macdHistPrev'] >= 0 > ind['macdHist']:
            add('medium', 'bearish', 'MACD 翻空（柱狀體由正轉負）',
                '中期動能由多轉空，依出場紀律屬於減碼訊號之一。')
        elif ind['macdHistPrev'] < 0 <= ind['macdHist']:
            add('medium', 'bullish', 'MACD 翻多（柱狀體由負轉正）',
                '中期動能由空轉多，常是波段起漲的早期訊號，但需搭配均線與籌碼確認。')
    if ind['rsi14'] is not None and ind['rsi14'] >= 80:
        add('low', 'bearish', 'RSI {:.0f} 進入過熱區'.format(ind['rsi14']),
            '短線漲多，隨時可能出現獲利賣壓回檔。不是賣出訊號，但不應在此位階加碼。')
    if ind['rsi14'] is not None and ind['rsi14'] <= 20:
        add('low', 'bullish', 'RSI {:.0f} 進入超賣區'.format(ind['rsi14']),
            '短線跌深，可能有技術性反彈。屬於搶反彈性質而非趨勢做多，風險較高。')
    if ch and ch['foreign1'] is not None and ch['foreignAbsAvg20']:
        if abs(ch['foreign1']) >= 2.5 * ch['foreignAbsAvg20'] and ch['foreignAbsAvg20'] > 0:
            d = 'bullish' if ch['foreign1'] > 0 else 'bearish'
            word = '買超' if ch['foreign1'] > 0 else '賣超'
            add('medium', d, '外資異常大{} {:,.0f} 張'.format(word, abs(ch['foreign1'])),
                '為近 20 日平均進出量的 {:.1f} 倍，屬於明顯的籌碼異動，通常對應特定消息或法人調整部位。'.format(abs(ch['foreign1']) / ch['foreignAbsAvg20']))
    if ch and ch['trustStreak'] is not None and ch['trustStreak'] >= 5:
        add('low', 'bullish', '投信連 {} 日買超'.format(ch['trustStreak']),
            '投信具有作帳與追蹤績效的動機，連續買超常見於中期看好的標的，但月底季底也可能出現調節。')
    for n in news_today:
        title = n.get('title') or ''
        bull = any(k in title for k in NEWS_BULL)
        bear = any(k in title for k in NEWS_BEAR)
        note = any(k in title for k in NEWS_NOTE)
        if bear and not bull:
            add('high', 'bearish', '今日負面消息', title)
        elif bull and not bear:
            add('medium', 'bullish', '今日正面消息', title)
        elif note:
            add('medium', 'neutral', '今日重要事件消息', title)
    ev.sort(key=lambda e: -SEV_RANK.get(e['severity'], 0))
    return ev


# ===================================================== 類股整體研判
def build_sector(idx, stocks_ind):
    series = idx.get('series') or []
    if not series:
        return None
    sec = [p['sector'] for p in series if p.get('sector')]
    mkt = [p['market'] for p in series if p.get('market')]
    dates = [p['date'] for p in series]
    sec_ma20, sec_ma60 = sma(sec, 20), sma(sec, 60)
    sec_r20, mkt_r20 = pct_change(sec, 20), pct_change(mkt, 20)
    sec_r60, mkt_r60 = pct_change(sec, 60), pct_change(mkt, 60)
    above = [i for i in stocks_ind if i['ma20'] and i['close'] > i['ma20']]
    breadth = len(above)
    total = len(stocks_ind)
    bpct = breadth / total * 100 if total else 0
    reasons = []
    if sec_ma20 and sec[-1] > sec_ma20:
        reasons.append(('bull', '類股指數站上自身 MA20'))
    else:
        reasons.append(('bear', '類股指數跌破自身 MA20'))
    if sec_ma20 and sec_ma60 and sec_ma20 > sec_ma60:
        reasons.append(('bull', 'MA20 在 MA60 之上（中期多頭排列）'))
    elif sec_ma20 and sec_ma60:
        reasons.append(('bear', 'MA20 在 MA60 之下（中期空頭排列）'))
    if sec_r20 is not None and mkt_r20 is not None:
        if sec_r20 > mkt_r20:
            reasons.append(('bull', '近 20 日贏大盤 {:+.1f} 個百分點（資金流入本類股）'.format(sec_r20 - mkt_r20)))
        else:
            reasons.append(('bear', '近 20 日輸大盤 {:+.1f} 個百分點（資金流出本類股）'.format(sec_r20 - mkt_r20)))
    reasons.append(('bull' if bpct >= 55 else ('bear' if bpct < 40 else 'watch'),
                    '16 檔中有 {} 檔站上 MA20（市場廣度 {:.0f}%）'.format(breadth, bpct)))
    strong = sec_ma20 and sec[-1] > sec_ma20
    if strong and sec_ma20 and sec_ma60 and sec_ma20 > sec_ma60 and bpct >= 55:
        phase, phase_key = '擴張期', 'expand'
        outlook = ('類股指數站上月線、月線在季線之上，且多數個股同步走強 —— 屬於資金持續流入的擴張格局。'
                   '這種環境下順勢操作（買強勢股回測）的勝率相對高，但仍須設停損，廣度一旦跌破 50% 就要警覺。')
    elif (not strong) and bpct < 40:
        phase, phase_key = '收縮期', 'contract'
        outlook = ('類股指數跌破月線，且站上月線的個股不到四成 —— 屬於資金撤出的收縮格局。'
                   '這種環境下任何個股訊號的可靠度都會下降，建議降低持股比重、縮小單筆部位，'
                   '等指數重新站回月線且廣度回到五成以上再談加碼。')
    else:
        phase, phase_key = '整理期', 'range'
        outlook = ('類股指數與均線糾結、個股強弱分歧 —— 屬於整理格局。'
                   '這種環境下類股整體不提供方向，報酬主要來自選股而非押注類股，'
                   '應嚴守個股的停損條件，避免因為「類股會漲」而放寬紀律。')
    return {
        'name': idx.get('sectorName') or '電腦及週邊設備類指數',
        'marketName': idx.get('marketName') or '發行量加權股價指數',
        'date': dates[-1] if dates else None,
        'sectorClose': r2(sec[-1]), 'marketClose': r2(mkt[-1]),
        'sectorMa20': r2(sec_ma20), 'sectorMa60': r2(sec_ma60),
        'sectorRet20': r2(sec_r20), 'marketRet20': r2(mkt_r20),
        'sectorRet60': r2(sec_r60), 'marketRet60': r2(mkt_r60),
        'rs20': r2(None if sec_r20 is None or mkt_r20 is None else sec_r20 - mkt_r20),
        'rs60': r2(None if sec_r60 is None or mkt_r60 is None else sec_r60 - mkt_r60),
        'breadth': breadth, 'breadthTotal': total, 'breadthPct': r1(bpct),
        'phase': phase, 'phaseKey': phase_key,
        'reasons': [{'tone': t, 'text': x} for t, x in reasons],
        'outlook': outlook,
    }


# ===================================================== 單檔指標組裝
def build_indicators(stock):
    hist = [h for h in (stock.get('history') or []) if h.get('close')]
    if len(hist) < 25:
        return None
    dates = [h['date'] for h in hist]
    closes = [float(h['close']) for h in hist]
    highs = [float(h.get('max') or h['close']) for h in hist]
    lows = [float(h.get('min') or h['close']) for h in hist]
    vols = [float(h.get('Trading_Volume') or 0) for h in hist]
    ma5, ma10, ma20 = sma(closes, 5), sma(closes, 10), sma(closes, 20)
    ma60 = sma(closes, 60)
    ma20_prev = sma_at(closes, 20, 5)
    line, sig, hist_v, hist_prev = macd(closes)
    k, d = stochastic(highs, lows, closes)
    a = atr(highs, lows, closes)
    avg_vol20 = sma(vols, 20)
    high60 = max(closes[-60:]) if len(closes) >= 2 else None
    low60 = min(closes[-60:]) if len(closes) >= 2 else None
    pos = None
    if high60 is not None and low60 is not None and high60 > low60:
        pos = (closes[-1] - low60) / (high60 - low60)
    return {
        'dates': dates, 'closes': closes,
        'date': dates[-1],
        'close': closes[-1],
        'prevClose': closes[-2] if len(closes) >= 2 else None,
        'pct': r2((closes[-1] / closes[-2] - 1) * 100) if len(closes) >= 2 else None,
        'volume': vols[-1],
        'ma5': r2(ma5), 'ma10': r2(ma10), 'ma20': r2(ma20), 'ma60': r2(ma60),
        'ma20Slope': r2(None if (ma20 is None or ma20_prev is None) else ma20 - ma20_prev),
        'rsi14': r2(rsi(closes)),
        'macd': r2(line), 'macdSignal': r2(sig), 'macdHist': r2(hist_v), 'macdHistPrev': r2(hist_prev),
        'kdK': r2(k), 'kdD': r2(d),
        'atr14': r2(a),
        'atrPct': r2(None if (a is None or not closes[-1]) else a / closes[-1] * 100),
        'bias20': r2(None if not ma20 else (closes[-1] - ma20) / ma20 * 100),
        'volRatio': r2(None if not avg_vol20 else vols[-1] / avg_vol20),
        'avgVol20': int(avg_vol20) if avg_vol20 else None,
        'high60': r2(high60), 'low60': r2(low60),
        'low10': r2(min(closes[-10:])) if len(closes) >= 10 else None,
        'pricePos60': r2(pos),
        'ret5': r2(pct_change(closes, 5)),
        'ret20': r2(pct_change(closes, 20)),
        'ret60': r2(pct_change(closes, 59)),
        'bars': len(closes),
    }


def build_chips(inst_stock):
    if not inst_stock:
        return None
    daily = inst_stock.get('daily') or []
    summ = inst_stock.get('summary') or {}
    sh = inst_stock.get('shareholding') or []
    f = [x.get('foreign') or 0 for x in daily]
    t = [x.get('trust') or 0 for x in daily]
    abs20 = sum(abs(v) for v in f[-20:]) / max(1, len(f[-20:])) if f else None
    return {
        'date': summ.get('lastDate') or (daily[-1]['date'] if daily else None),
        'foreign1': summ.get('foreign1'), 'foreign5': summ.get('foreign5'), 'foreign20': summ.get('foreign20'),
        'trust1': summ.get('trust1'), 'trust5': summ.get('trust5'), 'trust20': summ.get('trust20'),
        'dealer1': summ.get('dealer1'), 'dealer5': summ.get('dealer5'), 'dealer20': summ.get('dealer20'),
        'total1': summ.get('total1'), 'total5': summ.get('total5'), 'total20': summ.get('total20'),
        'foreignRatio': summ.get('foreignRatio'),
        'foreignRatioChg20': summ.get('foreignRatioChg20'),
        'foreignStreak': streak(f), 'trustStreak': streak(t),
        'foreignAbsAvg20': r1(abs20),
        'shareholdingLast': sh[-1] if sh else None,
    }


GLOSSARY = {
    'MA20': 'MA20 是「20 日移動平均線」，俗稱月線 —— 把最近 20 個交易日的收盤價平均。它代表近一個月進場者的平均成本：股價在月線之上，多數人賺錢、趨勢偏多；跌破月線，多數人虧損、容易引發賣壓。本站所有進出場規則都以 MA20 當趨勢分界。',
    'MA60': 'MA60 是「60 日移動平均線」，俗稱季線 —— 最近約一季的平均成本，是判斷中期趨勢的分界。站上季線通常代表中期轉強，跌破則代表中期轉弱。',
    'RSI': 'RSI（相對強弱指標）衡量近 14 日「上漲力道占總波動的比例」，數值 0~100。50 以上偏多、50 以下偏空；超過 80 代表短線過熱容易回檔，低於 20 代表超賣可能技術性反彈。注意：強勢股可以在 70 以上待很久，RSI 高不等於要賣。',
    'KD': 'KD（隨機指標）用近 9 日的高低區間判斷目前收盤落在哪個位階。K 線向上穿越 D 線叫「黃金交叉」偏多，向下穿越叫「死亡交叉」偏空。KD 在高檔（80 以上）鈍化時，常代表趨勢非常強而非該賣。',
    'MACD': 'MACD 用兩條不同長度的指數均線的差距判斷中期動能。本站看的是「柱狀體」：柱狀體由負轉正代表動能轉多，由正轉負代表動能轉空，柱子愈長代表動能愈強。',
    'ATR': 'ATR（真實波動幅度均值）是近 14 日的平均單日波動金額。它用來決定停損該設多遠 —— 波動大的股票停損要放寬，否則正常震盪就被洗出場。本站的停損價就是「進場區下緣減去 N 倍 ATR」。',
    '乖離率': '乖離率是收盤價偏離 MA20 的百分比。正乖離太大（例如超過 15%）代表短線漲多、追高風險高；負乖離太大代表跌深。本站的穩健型會排除乖離率超過 8% 的個股，就是為了避免追高。',
    '停損': '停損是「事先決定的最大可承受虧損價位」，跌破就無條件出場。它的目的不是預測，而是確保單筆虧損不會大到無法翻身。本站每檔都給明確停損價，紀律上跌破就該走，不要改成「再等反彈」。',
    '風險報酬比': '風險報酬比（R:R）= 可能賺的距離 ÷ 可能賠的距離。例如目標價距進場 10%、停損距進場 5%，R:R 就是 2.0。長期而言 R:R 低於 1.5 的交易即使勝率不錯也不容易賺，因為一次虧損就吃掉多次獲利。',
    '外資持股比': '外資持股比例是外資持有的股數占總股本的百分比。它比單日買賣超更能看出長期態度 —— 單日大買但持股比持續下降，代表整體仍在調節。本站看的是 20 日的變化方向。',
    '投信': '投信是國內的投資信託基金（共同基金）。投信有績效排名與作帳壓力，連續買超常見於中期看好的標的，對中小型股的影響力常大於外資；但月底、季底可能為了作帳而短期進出。',
    '三大法人': '三大法人指外資、投信、自營商。買賣超單位是「張」（1 張 = 1000 股）。外資資金最大、看中長期；投信看中期績效；自營商常做短線與避險，訊號參考性最低。',
    '市場廣度': '市場廣度指類股中有多少比例的個股站上 MA20。它用來驗證指數的漲勢是否健康 —— 指數上漲但廣度只有三成，代表只有少數權值股在撐，風險較高。',
    '相對強度': '相對強度是個股報酬減去類股指數報酬。贏指數代表資金相對集中在這檔；輸指數代表即使上漲也只是跟著大環境，不具選股價值。',
    '信賴區間': '本站的未來區間是用近 20 日實際波動度算出的統計範圍：68% 區間代表「若波動型態不變，約七成時間會落在此範圍」。它描述震盪幅度，不是方向預測，實際走勢完全可能超出。',
}


def main():
    stocks_raw = load('sector_stocks.json')
    inst = load('institutional.json')
    idx = load('index_compare.json')
    news = load('news.json')
    try:
        rt = load('realtime.json')
    except Exception:
        rt = {}

    # 依股號把新聞分組，只取最新交易日當天的做為事件來源
    news_items = news.get('items') or []
    news_by_stock = {}
    for n in news_items:
        for sid in (n.get('stocks') or []):
            news_by_stock.setdefault(sid, []).append(n)
    for v in news_by_stock.values():
        v.sort(key=lambda x: x.get('date') or '', reverse=True)

    inst_stocks = inst.get('stocks') or {}

    # 第一輪：算指標（類股廣度與相對強度需要全部個股的結果）
    prepared = []
    for st in stocks_raw:
        ind = build_indicators(st)
        if ind is None:
            continue
        prepared.append((st, ind))

    sector = build_sector(idx, [i for _, i in prepared])
    sector_ret20 = sector['sectorRet20'] if sector else None
    data_date = max(i['date'] for _, i in prepared) if prepared else None

    out_stocks = []
    all_alerts = []
    for st, ind in prepared:
        sid = st['id']
        ch = build_chips(inst_stocks.get(sid))
        t_s, t_r = score_trend(ind)
        m_s, m_r = score_momentum(ind)
        c_s, c_r = score_chips(ch)
        s_s, s_r = score_strength(ind, sector_ret20)
        total = (t_s * WEIGHTS['trend'] + m_s * WEIGHTS['momentum']
                 + c_s * WEIGHTS['chips'] + s_s * WEIGHTS['strength'])
        g = grade_of(total)
        reasons = t_r + m_r + c_r + s_r
        # 當日新聞：日期字串格式為 "YYYY-MM-DD HH:MM:SS"
        snews = news_by_stock.get(sid, [])
        today_news = [n for n in snews if (n.get('date') or '')[:10] == (data_date or '')]
        events = build_events(ind, ch, today_news)
        for e in events:
            a = dict(e)
            a['stockId'] = sid
            a['stockName'] = st['name']
            all_alerts.append(a)
        plans = {}
        for pk in PROFILE_ORDER:
            p = build_plan(ind, PROFILES[pk], ind['dates'])
            if p:
                plans[pk] = p
        rec = {
            'id': sid, 'name': st['name'], 'fullName': st.get('fullName'),
            'subGroup': st.get('subGroup'), 'subGroupName': st.get('subGroupName'),
            'isLeader': bool(st.get('isLeader')), 'leaderRole': st.get('leaderRole'),
            'description': st.get('description'),
            'date': ind['date'], 'close': ind['close'], 'pct': ind['pct'], 'volume': int(ind['volume']),
            'financials': st.get('financials'),
            'ind': {k: v for k, v in ind.items() if k not in ('dates', 'closes')},
            'chips': ch,
            'score': {
                'total': r1(total), 'trend': r1(t_s), 'momentum': r1(m_s),
                'chips': r1(c_s), 'strength': r1(s_s),
                'key': g['key'], 'label': g['label'], 'action': g['action'],
            },
            'reasons': [{'tone': t, 'text': x, 'weight': w, 'facet': f} for t, x, w, f in reasons],
            'plans': plans,
            'forecast': build_forecast(ind, ind['closes']),
            'events': events,
            'news': [{'title': n.get('title'), 'link': n.get('link'), 'date': n.get('date'),
                      'sources': n.get('sources') or []} for n in snews[:5]],
            'rs20': r2(None if (ind['ret20'] is None or sector_ret20 is None) else ind['ret20'] - sector_ret20),
        }
        out_stocks.append(rec)

    out_stocks.sort(key=lambda x: -(x['score']['total'] or 0))

    # 依風險屬性挑選建議名單：分數達門檻、乖離率不過高、且趨勢面不能太差
    picks = {}
    for pk in PROFILE_ORDER:
        p = PROFILES[pk]
        sel = []
        for s in out_stocks:
            if (s['score']['total'] or 0) < p['minScore']:
                continue
            bias = s['ind'].get('bias20')
            if bias is not None and bias > p['maxBias']:
                continue
            if (s['score']['trend'] or 0) < 40:
                continue
            sel.append(s['id'])
            if len(sel) >= p['maxPicks']:
                break
        picks[pk] = sel

    all_alerts.sort(key=lambda e: (-SEV_RANK.get(e['severity'], 0), e['stockId']))

    payload = {
        'updated_at': datetime.now(TPE).strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at_tz': '+08:00',
        'dataDate': data_date,
        'instDate': (max((s['chips']['date'] for s in out_stocks
                          if s.get('chips') and s['chips'].get('date')), default=None)),
        'newsUpdatedAt': news.get('updated_at'),
        'quoteDate': rt.get('marketDate'),
        'quoteTime': rt.get('marketTime'),
        'weights': WEIGHTS,
        'grades': [{'min': lo, 'key': k, 'label': lb, 'action': ac} for lo, k, lb, ac in GRADES],
        'profiles': PROFILES,
        'profileOrder': PROFILE_ORDER,
        'sector': sector,
        'stocks': out_stocks,
        'picks': picks,
        'alerts': all_alerts,
        'alertCounts': {
            'high': sum(1 for a in all_alerts if a['severity'] == 'high'),
            'medium': sum(1 for a in all_alerts if a['severity'] == 'medium'),
            'low': sum(1 for a in all_alerts if a['severity'] == 'low'),
        },
        'glossary': GLOSSARY,
        'methodology': {
            'weights': '總分 = 趨勢面 35% + 動能面 25% + 籌碼面 25% + 相對強度 15%，各面向先換算為 0~100 再加權。',
            'dataBasis': '技術指標取自還原股價後的日線收盤（除權息已還原，避免假跳空）；籌碼取自證交所三大法人買賣超與外資持股；相對強度對照電腦及週邊設備類指數。',
            'entry': '進場區以 MA20 與近 10 日低點的較高者為下緣，加上 0.8 倍 ATR 為上緣，刻意不給單一買點。收盤在 MA20 之下者一律標為「需先站回月線」而非直接建議進場。',
            'exit': '停損為進場區下緣減 N 倍 ATR（上限 12%），第一目標為進場中值加 N 倍 ATR，第二目標取 60 日高點與更遠的 ATR 倍數的較高者。',
            'holdDays': '預估持有天數以「到第一目標的距離 ÷ 每日 0.5 倍 ATR 的淨推進」估算，是資金效率的檢查點，不是預測。',
            'limits': '樣本僅 16 檔、60 根日線，不含基本面估值、產業循環與總體經濟變數，亦未做歷史回測驗證。所有訊號均為規則運算結果，不構成投資建議。',
        },
        'disclaimer': '本頁所有內容為依公開資料與固定技術規則自動運算的結果，僅供研究參考，'
                      '不構成任何投資建議、要約或保證。股價走勢受無法事前量化的因素影響，'
                      '過去的規則表現不代表未來獲利。投資決策與其後果由投資人自行承擔，'
                      '進行任何交易前請自行查核並評估自身風險承受度，必要時諮詢持照專業人士。',
    }
    path = dump('signals.json', payload)
    print('[signals] 已寫入 {}'.format(os.path.relpath(path, REPO)))
    print('[signals] 資料日 {} / 籌碼日 {} / 個股 {} 檔'.format(
        payload['dataDate'], payload['instDate'], len(out_stocks)))
    print('[signals] 類股研判：{}（廣度 {}/{}）'.format(
        sector['phase'] if sector else '無', sector['breadth'] if sector else '-',
        sector['breadthTotal'] if sector else '-'))
    for pk in PROFILE_ORDER:
        names = [s['name'] for s in out_stocks if s['id'] in picks[pk]]
        print('[signals] {} 建議名單（{} 檔）：{}'.format(
            PROFILES[pk]['name'], len(names), '、'.join(names) if names else '無符合條件者'))
    print('[signals] 事件警示：高 {} / 中 {} / 低 {}'.format(
        payload['alertCounts']['high'], payload['alertCounts']['medium'], payload['alertCounts']['low']))


if __name__ == '__main__':
    main()
