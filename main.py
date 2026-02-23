import yfinance as yf
import pandas as pd
import time

def get_detailed_info(ticker):
    """מושך חדשות מגוגל ונתוני אינסיידרים עם צבעים"""
    try:
        stock = yf.Ticker(ticker)
        google_news_link = f"https://www.google.com/search?q={ticker}+stock+news&tbm=nws"
        news_html = f"<a href='{google_news_link}' target='_blank' style='color: #3498db; font-weight: bold;'>🔍 Search Google News</a>"
        
        insider = stock.insider_transactions
        ins_val = "No Recent Data"
        
        if insider is not None and not insider.empty:
            first_row = insider.iloc[0]
            text = first_row.get('Text', 'Transaction Reported')
            # צביעת טקסט: ירוק לקנייה, אדום למכירה
            if "Purchase" in text or "Buy" in text:
                ins_val = f"<span style='color: #27ae60; font-weight: bold;'>🟢 {text}</span>"
            elif "Sale" in text or "Sell" in text:
                ins_val = f"<span style='color: #e74c3c;'>🔴 {text}</span>"
            else:
                ins_val = text
            
        return news_html, ins_val
    except:
        return "No News", "No Data"

def run_scanner():
    print("Fetching tickers from S&P 500, Nasdaq 100, and Dow Jones...")
    all_tickers = set()

    # משיכת רשימות המדדים
    try:
        sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]['Symbol'].tolist()
        all_tickers.update(sp500)
    except: print("Failed to fetch S&P 500")

    try:
        nasdaq100 = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]['Ticker'].tolist()
        all_tickers.update(nasdaq100)
    except: print("Failed to fetch Nasdaq 100")

    try:
        dow = pd.read_html('https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average')[1]['Symbol'].tolist()
        all_tickers.update(dow)
    except: print("Failed to fetch Dow Jones")

    final_list = sorted([str(t).replace('.', '-') for t in all_tickers])
    total_to_scan = len(final_list)
    
    results = []
    for i, ticker in enumerate(final_list):
        try:
            if i % 50 == 0: print(f"Progress: {i}/{total_to_scan} stocks scanned...")
            
            df = yf.download(ticker, period="2y", progress=False, interval="1d", timeout=10)
            if df.empty or len(df) < 151: continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA150'] = df['Close'].rolling(window=150).mean()
            
            price = float(df['Close'].iloc[-1])
            ma50 = float(df['MA50'].iloc[-1])
            ma150 = float(df['MA150'].iloc[-1])
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol != 0 else 0
            
            p_6m = float(df['Close'].iloc[-126])
            perf_6m = ((price - p_6m) / p_6m) * 100
            
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100
            
            if dist_50 < 5 or dist_150 < 5:
                news_btn, insider_info = get_detailed_info(ticker)
                
                # צביעת RVOL אם הוא גבוה מ-1.5
                rvol_display = f"{rvol:.2f}"
                if rvol > 1.5:
                    rvol_display = f"<span style='color: #27ae60; font-weight: bold; background: #eafaf1; padding: 2px 5px; border-radius: 3px;'>{rvol:.2f} 🔥</span>"

                results.append({
                    "Ticker": f"<b>{ticker}</b>",
                    "Price": f"{price:.2f}$",
                    "Status": "<span class='recovery'>💎 RECOVERY</span>" if perf_6m < -25 else "BULLISH",
                    "Condition": "Near MA50" if dist_50 < 5 else "Near MA150",
                    "RVOL": rvol_display,
                    "Insider Activity": insider_info,
                    "Market News": news_btn
                })
                time.sleep(0.05)
                
        except Exception: continue

    if results:
        df_final = pd.DataFrame(results)
        # המרה זמנית למספר לצורך מיון, ואז הצגת ה-HTML
        df_final['rvol_num'] = df_final['RVOL'].str.extract('(\d+\.\d+)').astype(float)
        df_final = df_final.sort_values(by="rvol_num", ascending=False).drop(columns=['rvol_num'])
        
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Master Stock Scanner</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f0f2f5; }}
                h1 {{ color: #1a73e8; text-align: center; }}
                .stats {{ text-align: center; color: #5f6368; font-weight: bold; margin-bottom: 20px; }}
                table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15); border-radius: 12px; overflow: hidden; }}
                th {{ background-color: #1a73e8; color: white; padding: 18px; text-align: left; }}
                td {{ padding: 15px; border-bottom: 1px solid #e8eaed; vertical-align: middle; }}
                tr:hover {{ background-color: #f8f9fa; }}
                .recovery {{ color: #d93025; font-weight: bold; background: #fce8e6; padding: 4px 8px; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <h1>📈 Master Scanner (S&P 500, Nasdaq 100, Dow Jones)</h1>
            <p class="stats">Scanned {total_to_scan} unique stocks | Found {len(results)} matches</p>
            <p style="text-align: center;">Last Update: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} UTC</p>
            {df_final.to_html(escape=False, index=False)}
        </body>
        </html>
        """
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    else:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write("<html><body style='text-align:center; padding:50px;'><h1>No matches found.</h1></body></html>")

if __name__ == "__main__":
    run_scanner()
