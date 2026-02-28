import yfinance as yf
import pandas as pd
import time

def get_detailed_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        google_news_link = f"https://www.google.com/search?q={ticker}+stock+news&tbm=nws"
        news_html = f"<a href='{google_news_link}' target='_blank' style='color: #3498db; font-weight: bold;'>🔍 News</a>"
        
        insider = stock.insider_transactions
        ins_val = "No Recent Data"
        if insider is not None and not insider.empty:
            first_row = insider.iloc[0]
            text = str(first_row.get('Text', 'Reported'))
            if "Purchase" in text or "Buy" in text:
                ins_val = f"<span style='color: #27ae60; font-weight: bold;'>🟢 Buy</span>"
            elif "Sale" in text or "Sell" in text:
                ins_val = f"<span style='color: #e74c3c;'>🔴 Sell</span>"
            else: ins_val = text
        return news_html, ins_val
    except: return "No News", "No Data"

def run_scanner():
    print("Fetching tickers...")
    all_tickers = set()
    try:
        sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]['Symbol'].tolist()
        all_tickers.update(sp500)
        nasdaq = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]['Ticker'].tolist()
        all_tickers.update(nasdaq)
    except: 
        all_tickers.update(["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "AMD"])

    final_list = sorted([str(t).replace('.', '-') for t in all_tickers])
    results = []
    
    print(f"Scanning {len(final_list)} stocks with 10% threshold...")
    for i, ticker in enumerate(final_list):
        try:
            if i % 100 == 0: print(f"Progress: {i}/{len(final_list)}")
            df = yf.download(ticker, period="2y", progress=False, interval="1d", timeout=10)
            if df.empty or len(df) < 151: continue
            
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA150'] = df['Close'].rolling(window=150).mean()
            
            price = float(df['Close'].iloc[-1])
            ma50 = float(df['MA50'].iloc[-1])
            ma150 = float(df['MA150'].iloc[-1])
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol != 0 else 0
            
            perf_6m = ((price - float(df['Close'].iloc[-126])) / float(df['Close'].iloc[-126])) * 100
            
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100
            
            # שינינו ל-10% כדי להבטיח תוצאות
            if dist_50 < 10 or dist_150 < 10:
                news_btn, insider_info = get_detailed_info(ticker)
                rvol_display = f"{rvol:.2f}"
                if rvol > 1.5:
                    rvol_display = f"<span style='color: #27ae60; font-weight: bold;'>{rvol:.2f} 🔥</span>"

                results.append({
                    "Ticker": f"<b>{ticker}</b>",
                    "Price": f"{price:.2f}$",
                    "Status": "<span style='color:red'>💎 RECOVERY</span>" if perf_6m < -20 else "BULLISH",
                    "Condition": "Near MA50" if dist_50 < 10 else "Near MA150",
                    "RVOL": rvol_display,
                    "Insider": insider_info,
                    "News": news_btn
                })
        except: continue

    if results:
        df_res = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
        html = f"""
        <html><head><meta charset="UTF-8"><style>
        body {{ font-family: sans-serif; margin: 20px; background: #f4f7f6; }}
        table {{ border-collapse: collapse; width: 100%; background: white; }}
        th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
        th {{ background: #1a73e8; color: white; }}
        tr:hover {{ background: #f1f1f1; }}
        </style></head><body>
        <h1 style='text-align:center'>📈 Stock Scanner (10% Range)</h1>
        <p style='text-align:center'>Found {len(results)} matches | Update: {pd.Timestamp.now()}</p>
        {df_res.to_html(escape=False, index=False)}
        </body></html>
        """
        with open("index.html", "w", encoding="utf-8") as f: f.write(html)
    else:
        with open("index.html", "w", encoding="utf-8") as f: 
            f.write(f"<html><body><h1>No matches even at 10% - Check logs. {pd.Timestamp.now()}</h1></body></html>")

if __name__ == "__main__": run_scanner()
