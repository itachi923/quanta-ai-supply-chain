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
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 評分與進出場規則一律來自 signal_rules，不在本檔重複定義 ——
# 這樣 backtest_signals.py 才能保證回測的是線上同一套規則。
from signal_rules import (  # noqa: E402
    PROFILES, PROFILE_ORDER, WEIGHTS, GRADES, grade_of,
    score_trend, score_momentum, score_chips, score_strength,
    build_indicators, build_chips, build_plan, build_forecast,
    sma, pct_change, r1, r2,
)

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
            'limits': '樣本僅 16 檔、60 根日線，不含基本面估值、產業循環與總體經濟變數。'
                      '規則已以 2023 年起約 4 年的資料做過回測（見本頁回測區塊），但那是樣本內結果，'
                      '且優勢很薄、高度依賴類股環境。所有訊號均為規則運算結果，不構成投資建議。',
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
