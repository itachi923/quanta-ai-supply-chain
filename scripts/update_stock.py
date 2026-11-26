import urllib.request
import json
import datetime
import os

from adjust_prices import adjust_rows, summarize, events_meta

def update_quanta_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    target_path = os.path.join(data_dir, 'quanta_latest.json')

    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] Starting Quanta (2382) daily stock data update...")

    # 1. Fetch Daily Prices from 2024-01-01
    url_price = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=2382&start_date=2024-01-01'
    req_price = urllib.request.Request(url_price, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_price, timeout=15) as resp:
        price_data = json.loads(resp.read().decode('utf-8')).get('data', [])

    # 2. Fetch Monthly Revenue
    url_rev = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id=2382&start_date=2024-01-01'
    req_rev = urllib.request.Request(url_rev, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_rev, timeout=15) as resp:
        rev_data = json.loads(resp.read().decode('utf-8')).get('data', [])

    # 3. Fetch Financial Statements
    url_fin = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=2382&start_date=2024-01-01'
    req_fin = urllib.request.Request(url_fin, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_fin, timeout=15) as resp:
        fin_data = json.loads(resp.read().decode('utf-8')).get('data', [])

    # 還原股價：抹平除權息與股票分割造成的價格斷層，否則 K 線與均線會全部失真
    price_data, adj_events = adjust_rows(price_data, stock_id='2382')
    if adj_events:
        summarize(adj_events, label='2382')

    bundle = {
        'updated_at': now_str,
        'priceAdjustments': events_meta(adj_events),
        'stock_id': '2382',
        'name': '廣達電腦',
        'daily_prices': price_data,
        'monthly_revenue': rev_data,
        'financial_statements': fin_data
    }

    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False)

    print(f"Successfully saved {len(price_data)} price records to {target_path}")

if __name__ == '__main__':
    update_quanta_data()
