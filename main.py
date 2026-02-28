import yfinance as yf
import pandas as pd
import datetime
import time

def get_detailed_info(ticker):
    """מושך חדשות ונתוני אינסיידרים"""
    try:
        stock = yf.Ticker(ticker)
        # לינק לחדשות
        news_link = f"https://www.google.com/search?q={ticker}+stock+news&tbm=nws"
        news_html = f"<a href='{news_link}' target='_blank' style='text-decoration:none;'>🔍 News</a>"
        
        # נתוני אינסיידרים
        insider = stock.insider_transactions
        ins_val = "No Data"
        if insider is not None and not insider.empty:
            text = str(insider.iloc[0].get('Text', ''))
            if "Purchase" in text or "Buy" in text:
                ins_val = "<span style='color:#27ae60; font-weight:bold;'>🟢 Buy</span>"
            elif "Sale" in text or "Sell" in text:
                ins_val = "<span style='color:#e74c3c;'>🔴 Sell</span>"
            else: ins_val = text[:20]
        return news_html, ins_val
    except: return "No News", "No Data"

def run_scanner():
    print("Starting Deep Scan...")
    # משיכת רשימת מניות (S&P 500 + Nasdaq 100)
    try:
        sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]['Symbol'].tolist()
        nasdaq = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]['Ticker'].tolist()
        tickers = list(set(sp500 + nasdaq))
    except:
        tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD", "META", "GOOGL", "AMZN"]

    results = []
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        try:
            ticker = ticker.replace('.', '-')
            if i % 50 == 0: print(f"Progress: {i}/{total}")
            
            df = yf.download(ticker, period="1y", interval="1d", progress=False, timeout=8)
            if df.empty or len(df) < 130: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

            price = float(df['Close'].iloc[-1])
            ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            ma150 = df['Close'].rolling(window=150).mean().iloc[-1]
            
            # חישוב ביצועים חצי שנה (כ-126 ימי מסחר)
            price_6m_ago = float(df['Close'].iloc[-126])
            perf_6m = ((price - price_6m_ago) / price_6m_ago) * 100
            
            # חישוב RVOL
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol > 0 else 0
            
            # תנאי סינון: קרוב לממוצע 50 או 150 (טווח של 5%)
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100

            if dist_50 < 5 or dist_150 < 5:
                news, insider = get_detailed_info(ticker)
                
                # עיצוב RVOL
                rvol_str = f"{rvol:.2f}"
                if rvol > 1.5: rvol_str = f"<b style='color:#27ae60;'>{rvol:.2f} 🔥</b>"

                # סטטוס Bullish או Recovery
                status = "BULLISH"
                if perf_6m < -30:
                    status = "<span style='background:#fce8e6; color:#d93025; padding:3px; border-radius:3px; font-weight:bold;'>💎 RECOVERY</span>"

                results.append({
                    "Ticker": f"<b>{ticker}</b>",
                    "Price": f"{price:.2f}$",
                    "Status": status,
                    "Condition": "Near MA50" if dist_50 < 5 else "Near MA150",
                    "RVOL": rvol_str,
                    "Insider": insider,
                    "Market News": news
                })
                time.sleep(0.1) # מניעת חסימה מ-Yahoo
        except: continue

    # יצירת דף ה-HTML המעוצב
    if results:
        df_res = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
        html_table = df_res.to_html(escape=False, index=False)
    else:
        html_table = "<h2>No matches found in the 5% range today.</h2>"

    full_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Stock Master Scanner</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; padding: 20px; }}
            .container {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a73e8; text-align: center; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th {{ background: #1a73e8; color: white; padding: 12px; text-align: left; }}
            td {{ padding: 12px; border-bottom: 1px solid #eee; }}
            tr:hover {{ background: #f8f9fa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 Real-Time Stock Scanner</h1>
            <p style="text-align:center; color:#666;">Last Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)</p>
            {html_table}
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    run_scanner()
