import yfinance as yf
import pandas as pd
import datetime

def run_scanner():
    # רשימה מצומצמת ומהירה לבדיקה ראשונית
    tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "AMD", "NFLX", "DIS", "PYPL", "INTC"]
    
    # ניסיון למשוך את ה-S&P 500
    try:
        sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]['Symbol'].tolist()
        tickers = list(set(tickers + sp500))
    except:
        print("Using basic ticker list")

    results = []
    print(f"Scanning {len(tickers)} stocks...")

    for ticker in tickers:
        try:
            ticker = ticker.replace('.', '-')
            df = yf.download(ticker, period="1y", interval="1d", progress=False, timeout=5)
            
            if df.empty or len(df) < 150: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

            price = float(df['Close'].iloc[-1])
            ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            
            # בדיקה רחבה מאוד (20%) כדי לוודא שמשהו עולה
            dist = abs((price - ma50) / ma50) * 100
            
            if dist < 20:
                results.append({
                    "Ticker": ticker,
                    "Price": f"{price:.2f}$",
                    "Dist_MA50": f"{dist:.1f}%",
                    "Time": datetime.datetime.now().strftime("%H:%M:%S")
                })
        except: continue

    # יצירת ה-HTML
    if results:
        df_res = pd.DataFrame(results)
        html_content = f"<html><body><h1>Scanner Update: {datetime.datetime.now()}</h1>{df_res.to_html()}</body></html>"
    else:
        html_content = f"<html><body><h1>No matches found at {datetime.datetime.now()}</h1></body></html>"

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("File index.html updated successfully.")

if __name__ == "__main__":
    run_scanner()
