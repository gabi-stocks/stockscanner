import yfinance as yf
import pandas as pd
import time
import requests

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
    print("Fetching S&P 500 list from a reliable source...")
    try:
        # שימוש במקור חלופי ואמין יותר מוויקיפדיה עבור GitHub Actions
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df_sp = pd.read_csv(url)
        tickers = df_sp['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]
    except Exception as e:
        print(f"Failed to fetch from primary source: {e}")
        # ניסיון שני מוויקיפדיה אם הראשון נכשל
        try:
            table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
            tickers = table[0]['Symbol'].tolist()
            tickers = [t.replace('.', '-') for t in tickers]
        except:
            # אם הכל נכשל - רשימה מורחבת כגיבוי אחרון
            tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "AMD", "INTC", "NFLX", "DIS", "BA", "V", "MA"]

    results = []
    total = len(tickers)
    print(f"Starting scan for {total} stocks. This will take a few minutes...")
    
    for i, ticker in enumerate(tickers):
        try:
            if i % 50 == 0: print(f"Progress: {i}/{total} stocks scanned...")
            
            # הורדת נתונים (שנתיים אחורה)
            df = yf.download(ticker, period="2y", progress=False, interval="1d", timeout=10)
            
            if df.empty or len(df) < 151:
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # חישוב ממוצעים
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA150'] = df['Close'].rolling(window=150).mean()
            
            price = float(df['Close'].iloc[-1])
            ma50 = float(df['MA50'].iloc[-1])
            ma150 = float(df['MA150'].iloc[-1])
            
            # ווליום יחסי (RVOL)
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol != 0 else 0
            
            # ביצועים ל-6 חודשים (Recovery check)
            p_6m = float(df['Close'].iloc[-126])
            perf_6m = ((price - p_6m) / p_6m) * 100
            
            # תנאי סינון: מרחק של עד 5% מממוצע 50 או 150
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100
            
            if dist_50 < 5 or dist_150 < 5:
                news_btn, insider_info = get_detailed_info(ticker)
                results.append({
                    "Ticker": f"<b>{ticker}</b>",
                    "Price": f"{price:.2f}$",
                    "Status": "<span class='recovery'>💎 RECOVERY</span>" if perf_6m < -25 else "BULLISH",
                    "Condition": "Near MA50" if dist_50 < 5 else "Near MA150",
                    "RVOL": f"{rvol:.2f}",
                    "Insider Activity": insider_info,
                    "Market News": news_btn
                })
                # השהיה קלה למניעת חסימה
                time.sleep(0.1)
                
        except Exception as e:
            continue

    if results:
        df_final = pd.DataFrame(results)
        df_final = df_final.sort_values(by="RVOL", ascending=False)
        
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Advanced S&P 500 Scanner</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f0f2f5; color: #1c1e21; }}
                h1 {{ color: #1a73e8; text-align: center; font-size: 2.5em; }}
                .timestamp {{ text-align: center; color: #70757a; margin-bottom: 30px; font-style: italic; }}
                table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15); border-radius: 12px; overflow: hidden; }}
                th {{ background-color: #1a73e8; color: white; padding: 18px; text-align: left; font-size: 14px; letter-spacing: 1px; }}
                td {{ padding: 15px; border-bottom: 1px solid #e8eaed; vertical-align: middle; font-size: 15px; }}
                tr:hover {{ background-color: #f8f9fa; }}
                .recovery {{ color: #d93025; font-weight: bold; background: #fce8e6; padding: 4px 8px; border-radius: 4px; }}
                a {{ text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>📈 Smart Stock Scanner (S&P 500 Full)</h1>
            <p class="timestamp">Scan generated at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} (UTC)</p>
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
