import yfinance as yf
import pandas as pd
import datetime
import requests
import time

def get_detailed_info(ticker):
    """משיכת חדשות ונתוני אינסיידרים"""
    try:
        stock = yf.Ticker(ticker)
        news_link = f"https://www.google.com/search?q={ticker}+stock+news&tbm=nws"
        news_html = f"<a href='{news_link}' target='_blank' style='text-decoration:none;'>🔍 News</a>"
        
        insider = stock.insider_transactions
        ins_val = "No Data"
        if insider is not None and not insider.empty:
            text = str(insider.iloc[0].get('Text', ''))
            if "Purchase" in text or "Buy" in text:
                ins_val = "<span style='color:#27ae60; font-weight:bold;'>🟢 Buy</span>"
            elif "Sale" in text or "Sell" in text:
                ins_val = "<span style='color:#e74c3c;'>🔴 Sell</span>"
            else: ins_val = text[:15]
        return news_html, ins_val
    except: return "No News", "No Data"

def run_scanner():
    print("Starting Focused Scan (Approaching MA150 from Below)...")
    tickers = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # משיכת מניות S&P 500 ו-Nasdaq 100
    try:
        url_sp = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        resp_sp = requests.get(url_sp, headers=headers)
        sp500 = pd.read_html(resp_sp.text)[0]['Symbol'].tolist()
        tickers.extend(sp500)
        
        url_nas = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        resp_nas = requests.get(url_nas, headers=headers)
        nasdaq = pd.read_html(resp_nas.text)[4]['Ticker'].tolist()
        tickers.extend(nasdaq)
    except: 
        print("Wiki fetch failed, using backup...")
        tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD", "META", "AMZN", "GOOGL"]

    tickers = list(set([str(t).replace('.', '-') for t in tickers]))
    results = []
    print(f"Scanning {len(tickers)} stocks...")

    for i, ticker in enumerate(tickers):
        try:
            if i % 50 == 0: print(f"Progress: {i}/{len(tickers)}")
            df = yf.download(ticker, period="1y", interval="1d", progress=False, timeout=10)
            
            if df.empty or len(df) < 151: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

            price = float(df['Close'].iloc[-1])
            ma150 = df['Close'].rolling(window=150).mean().iloc[-1]
            
            # חישוב ביצועים ל-6 חודשים (Recovery)
            price_6m_ago = float(df['Close'].iloc[-126])
            perf_6m = ((price - price_6m_ago) / price_6m_ago) * 100
            
            # חישוב RVOL
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol > 0 else 0
            
            # התנאי החדש: מתקרב ל-MA150 מלמטה (מתחת לממוצע ועד 5% ממנו)
            # אם המחיר קטן מהממוצע (Price < MA150)
            # והמרחק (MA150 - Price) חלקי הממוצע קטן מ-5%
            dist_from_below = (ma150 - price) / ma150
            
            if 0 < dist_from_below <= 0.05:
                news, insider = get_detailed_info(ticker)
                
                rvol_str = f"{rvol:.2f}"
                if rvol > 1.5: rvol_str = f"<b style='color:#27ae60;'>{rvol:.2f} 🔥</b>"

                status = "BULLISH"
                if perf_6m < -30:
                    status = "<span style='background:#fce8e6; color:#d93025; padding:4px; border-radius:4px; font-weight:bold;'>💎 RECOVERY</span>"

                results.append({
                    "Ticker": f"<b>{ticker}</b>",
                    "Price": f"{price:.2f}$",
                    "Status": status,
                    "Condition": f"Below MA150 ({dist_from_below*100:.1f}%)",
                    "RVOL": rvol_str,
                    "Insider": insider,
                    "News": news
                })
        except: continue

    # בניית ה-HTML
    if results:
        df_res = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
        table_html = df_res.to_html(escape=False, index=False)
    else:
        table_html = "<h3 style='text-align:center;'>No stocks currently approaching MA150 from below (0-5% range).</h3>"

    full_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', Arial; background: #f4f7f9; padding: 20px; }}
            .card {{ background: white; padding: 25px; border-radius: 15px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); }}
            h1 {{ color: #1a73e8; text-align: center; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th {{ background: #1a73e8; color: white; padding: 15px; text-align: left; }}
            td {{ padding: 15px; border-bottom: 1px solid #eee; }}
            tr:hover {{ background: #f1f8ff; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📉 Under-MA150 Recovery Scanner</h1>
            <p style="text-align:center; color:#666;">Showing stocks approaching MA150 from below (within 5% range)<br>
            Last Scan: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
            {table_html}
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    run_scanner()
