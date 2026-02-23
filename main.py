import yfinance as yf
import pandas as pd
import time

def get_detailed_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:3] # נמשוך 3 כתבות כדי להגדיל סיכוי לקישור טוב
        news_links = []
        for n in news:
            title = n.get('title', 'News')
            link = n.get('link', '')
            # בדיקה שהקישור הוא באמת קישור חיצוני
            if link.startswith('http'):
                news_links.append(f"• <a href='{link}' target='_blank' rel='noopener noreferrer'>{title}</a>")
        
        insider = stock.insider_transactions
        ins_val = "No Recent Data"
        if insider is not None and not insider.empty:
            ins_val = f"{insider.iloc[0].get('Text', 'Transaction Reported')}"
            
        return "<br>".join(news_links) if news_links else "No News", ins_val
    except:
        return "No News", "No Data"
        

def run_scanner():
    print("Fetching S&P 500 list from Wikipedia...")
    try:
        # משיכת רשימת ה-S&P 500 המלאה
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers] # התאמה ל-yfinance
    except Exception as e:
        print(f"Failed to fetch list: {e}")
        tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META"]

    results = []
    total = len(tickers)
    print(f"Starting scan for {total} stocks. This may take a few minutes...")
    
    for i, ticker in enumerate(tickers):
        try:
            # הדפסת התקדמות בלוגים של GitHub
            if i % 50 == 0: print(f"Progress: {i}/{total} stocks scanned...")
            
            # הורדת נתונים (שנתיים אחורה)
            df = yf.download(ticker, period="2y", progress=False, interval="1d")
            
            if df.empty or len(df) < 151:
                continue
            
            # ניקוי כותרות (MultiIndex fix)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # חישוב ממוצעים נעים (MA)
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA150'] = df['Close'].rolling(window=150).mean()
            
            # נתונים אחרונים
            price = float(df['Close'].iloc[-1])
            ma50 = float(df['MA50'].iloc[-1])
            ma150 = float(df['MA150'].iloc[-1])
            
            # חישוב ווליום יחסי (RVOL) - ממוצע של 20 יום
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol != 0 else 0
            
            # חישוב ביצועים ל-6 חודשים (נר 126 ימי מסחר אחורה)
            p_6m = float(df['Close'].iloc[-126])
            perf_6m = ((price - p_6m) / p_6m) * 100
            
            # סינון: מרחק של עד 5% מממוצע 50 או 150
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100
            
            if dist_50 < 5 or dist_150 < 5:
                news, insider = get_detailed_info(ticker)
                results.append({
                    "Ticker": ticker,
                    "Price": f"{price:.2f}$",
                    "Status": "💎 RECOVERY" if perf_6m < -25 else "BULLISH",
                    "Condition": "Near MA50" if dist_50 < 5 else "Near MA150",
                    "RVOL": f"{rvol:.2f}",
                    "Insider Activity": insider,
                    "Latest News": news
                })
                # השהיה קלה כדי לא להיחסם ע"י Yahoo Finance
                time.sleep(0.2)
                
        except Exception as e:
            continue

    # יצירת ה-HTML הסופי
    if results:
        df_final = pd.DataFrame(results)
        # מיון לפי ווליום יחסי (הגבוה ביותר למעלה)
        df_final = df_final.sort_values(by="RVOL", ascending=False)
        
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Stock Scanner Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f4f7f6; color: #333; }}
                h1 {{ color: #2c3e50; text-align: center; }}
                .timestamp {{ text-align: center; color: #7f8c8d; margin-bottom: 20px; }}
                table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 5px 15px rgba(0,0,0,0.1); border-radius: 10px; overflow: hidden; }}
                th {{ background-color: #3498db; color: white; padding: 15px; text-align: left; text-transform: uppercase; font-size: 14px; }}
                td {{ padding: 12px 15px; border-bottom: 1px solid #eee; vertical-align: top; font-size: 14px; }}
                tr:hover {{ background-color: #f9f9f9; }}
                .recovery {{ color: #e74c3c; font-weight: bold; }}
                a {{ color: #3498db; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>📈 S&P 500 Scanner: Near Key Moving Averages</h1>
            <p class="timestamp">Last Updated (UTC): {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
            {df_final.to_html(escape=False, index=False)}
        </body>
        </html>
        """
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
    else:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write("<html><body style='font-family:sans-serif; text-align:center; padding-top:50px;'><h1>No stocks currently meet the criteria.</h1></body></html>")

if __name__ == "__main__":
    run_scanner()
