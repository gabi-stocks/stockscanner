import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import time

def get_detailed_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:2]
        news_links = [f"<a href='{n['link']}'>{n['title']}</a>" for n in news]
        insider = stock.insider_transactions
        insider_val = f"{insider.iloc[0]['Text']}" if insider is not None and not insider.empty else "No Recent Data"
        return "<br>".join(news_links), insider_val
    except: return "N/A", "N/A"

def run_scanner():
    # כאן אפשר להשתמש בפונקציית ה-S&P 500 המלאה שכתבנו קודם
    tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "INTC", "PYPL", "DIS", "BA"] 
    results = []
    
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="18mo", progress=False)
            if df.empty: continue
            df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
            
            price = df['Close'].iloc[-1]
            ma50 = ta.sma(df['Close'], length=50).iloc[-1]
            ma150 = ta.sma(df['Close'], length=150).iloc[-1]
            
            # בדיקת תנאי OR (מרחק < 5%)
            d50 = abs((price - ma50) / ma50) * 100
            d150 = abs((price - ma150) / ma150) * 100
            
            if d50 < 5 or d150 < 5:
                news, insider = get_detailed_info(ticker)
                results.append({
                    "Ticker": ticker, "Price": f"{price:.2f}$",
                    "Condition": "MA50" if d50 < 5 else "MA150",
                    "Insider": insider, "News": news
                })
        except: continue

    if results:
        df_final = pd.DataFrame(results)
        df_final.to_html("index.html", escape=False, index=False)
        print("✅ Report generated: index.html")

if __name__ == "__main__":
    run_scanner()
