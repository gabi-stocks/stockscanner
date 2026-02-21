import yfinance as yf
import pandas as pd

def get_detailed_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        # משיכת חדשות
        news = stock.news[:2]
        news_links = []
        for n in news:
            title = n.get('title', 'News')
            link = n.get('link', '#')
            news_links.append(f"• <a href='{link}' target='_blank'>{title}</a>")
        
        # משיכת אינסיידרים
        insider = stock.insider_transactions
        ins_val = "No Recent Data"
        if insider is not None and not insider.empty:
            ins_val = f"{insider.iloc[0].get('Text', 'Transaction Reported')}"
            
        return "<br>".join(news_links) if news_links else "No News", ins_val
    except:
        return "No News", "No Data"

def run_scanner():
    # רשימת מניות לסריקה (אפשר להוסיף עוד)
    tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "INTC", "PYPL", "DIS", "BA", "AVGO", "AMD", "META", "GOOGL", "AMZN", "NFLX"] 
    results = []
    
    print(f"Starting scan for {len(tickers)} stocks...")
    
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="2y", progress=False)
            if df.empty or len(df) < 151:
                continue
            
            # ניקוי כותרות (עבור yfinance החדש)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # חישוב ממוצעים ידני (במקום pandas_ta)
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA150'] = df['Close'].rolling(window=150).mean()
            
            price = float(df['Close'].iloc[-1])
            ma50 = float(df['MA50'].iloc[-1])
            ma150 = float(df['MA150'].iloc[-1])
            
            # חישוב ווליום יחסי (RVOL)
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol != 0 else 0
            
            # חישוב ירידה של חצי שנה (Recovery)
            p_6m = float(df['Close'].iloc[-126])
            drop_6m = ((price - p_6m) / p_6m) * 100
            
            # תנאי: מרחק עד 5% מ-MA50 או MA150
            d50 = abs((price - ma50) / ma50) * 100
            d150 = abs((price - ma150) / ma150) * 100
            
            if d50 < 5 or d150 < 5:
                news, insider = get_detailed_info(ticker)
                results.append({
                    "Ticker": ticker,
                    "Price": f"{price:.2f}$",
                    "Type": "💎 RECOVERY" if drop_6m < -30 else "Standard",
                    "Condition": "Near MA50" if d50 < 5 else "Near MA150",
                    "RVOL": f"{rvol:.2f}",
                    "Insider": insider,
                    "Latest News": news
                })
        except Exception as e:
            print(f"Error on {ticker}: {e}")
            continue

    # יצירת הקובץ index.html
    if results:
        df_final = pd.DataFrame(results)
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: sans-serif; margin: 40px; background-color: #f8f9fa; }}
                table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
                th {{ background-color: #007bff; color: white; padding: 15px; text-align: left; }}
                td {{ padding: 15px; border-bottom: 1px solid #dee2e6; vertical-align: top; }}
                tr:hover {{ background-color: #f1f3f5; }}
            </style>
        </head>
        <body>
            <h1>📈 Stock Scan Results</h1>
            <p>Last Run: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
            {df_final.to_html(escape=False, index=False)}
        </body>
        </html>
        """
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    else:
        with open("index.html", "w") as f:
            f.write("<html><body><h1>No matches today.</h1></body></html>")

if __name__ == "__main__":
    run_scanner()
