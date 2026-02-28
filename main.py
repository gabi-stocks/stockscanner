import yfinance as yf
import pandas as pd
import datetime
import requests

def get_detailed_info(ticker):
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
    print("Fetching tickers with User-Agent...")
    tickers = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # ניסיון 1: S&P 500
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        response = requests.get(url, headers=headers)
        sp500 = pd.read_html(response.text)[0]['Symbol'].tolist()
        tickers.extend(sp500)
        print(f"Successfully fetched {len(sp500)} S&P 500 tickers")
    except Exception as e:
        print(f"S&P 500 fetch failed: {e}")

    # ניסיון 2: Nasdaq 100
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        response = requests.get(url, headers=headers)
        nasdaq = pd.read_html(response.text)[4]['Ticker'].tolist()
        tickers.extend(nasdaq)
        print(f"Successfully fetched {len(nasdaq)} Nasdaq tickers")
    except Exception as e:
        print(f"Nasdaq fetch failed: {e}")

    tickers = list(set([str(t).replace('.', '-') for t in tickers]))
    
    if len(tickers) < 20:
        print("CRITICAL: Falling back to backup list")
        tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN"]

    results = []
    print(f"Scanning {len(tickers)} stocks...")

    # כאן המשך הקוד של הסריקה כפי שהיה קודם...
    # (משיכת הנתונים מ-yfinance וסינון ה-5%)
    for i, ticker in enumerate(tickers):
        try:
            if i % 50 == 0: print(f"Progress: {i}/{len(tickers)}")
            df = yf.download(ticker, period="1y", interval="1d", progress=False, timeout=8)
            if df.empty or len(df) < 130: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

            price = float(df['Close'].iloc[-1])
            ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            ma150 = df['Close'].rolling(window=150).mean().iloc[-1]
            
            price_6m_ago = float(df['Close'].iloc[-126])
            perf_6m = ((price - price_6m_ago) / price_6m_ago) * 100
            
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            rvol = float(df['Volume'].iloc[-1] / avg_vol) if avg_vol > 0 else 0
            
            dist_50 = abs((price - ma50) / ma50) * 100
            dist_150 = abs((price - ma150) / ma150) * 100

            if dist_50 < 5 or dist_150 < 5:
                news, insider = get_detailed_info(ticker)
                rvol_str = f"{rvol:.2f}"
                if rvol > 1.5: rvol_str = f"<b style='color:#27ae60;'>{rvol:.2f} 🔥</b>"

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
                    "News": news
                })
        except: continue

    # יצירת הקובץ הסופי
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        html_table = res_df.sort_values(by="RVOL", ascending=False).to_html(escape=False, index=False)
    else:
        html_table = "<h3>No matches found in 5% range.</h3>"

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body><h1>Full Scan Result</h1>{html_table}</body></html>")
    print("Done!")

if __name__ == "__main__":
    run_scanner()
