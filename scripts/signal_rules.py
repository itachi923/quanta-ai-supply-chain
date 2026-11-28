# -*- coding: utf-8 -*-
"""
訊號規則核心（build_signals.py 與 backtest_signals.py 的共用模組）
================================================================
這裡只放**純函式**：給它一段日線與籌碼，算出指標、四面向分數與進出場計畫。
不讀檔、不連網、不帶任何「今天」的概念 —— 所有函式都只看傳進來的資料。

為什麼要獨立成一個模組（重要，不要再把規則複製回去）：
  回測的意義在於驗證**線上實際在跑的那一套規則**。如果回測自己重寫一份
  規則，那它驗證的是另一個程式，結果再漂亮也不能拿來描述線上頁面的表現。
  把規則集中在這裡，build_signals.py（產生當日訊號）與 backtest_signals.py
  （回測歷史訊號）就一定執行同一份程式碼。

  推論：**改這個檔案會同時改變線上訊號與回測結果**。改完兩邊都要重跑，
  而且要確認回測的統計數字有沒有跟著變 —— 如果規則改了但回測數字沒動，
  代表某一邊沒有真的用到這個模組。

函式分三層：
  1. 指標層：sma / rsi / macd / stochastic / atr …（純數學）
  2. 評分層：score_trend / score_momentum / score_chips / score_strength
             每條規則都要回傳 (tone, text, weight, facet) 供前端攤開顯示
  3. 計畫層：build_plan（進場區、停損、停利、預估持有天數）、build_forecast
"""

import math
from datetime import datetime, timedelta


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
