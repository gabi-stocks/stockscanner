#!/usr/bin/env python3
"""
MA150 Breakout Scanner  –  S&P 500 + NASDAQ (כל הבורסה)
--------------------------------------------------------
תנאים (ניתנים לכיוון ב-CONFIG):
 1. פריצה טרייה של ממוצע 150 יום: סגירה מעל MA150, ובתוך LOOKBACK_CROSS הימים
    האחרונים הייתה סגירה מתחת/על המ"מ (כלומר החצייה קרתה עכשיו, לא לפני חודשיים).
 2. ווליום גבוה: RVOL = ווליום היום / ממוצע 50 יום  >= RVOL_MIN.
 3. לא מתוח: מרחק מ-MA150 <= MAX_EXT_150, מרחק מ-MA20 <= MAX_EXT_20, RSI14 < RSI_MAX.
 4. מגמה בריאה: MA50 > MA150 או MA50 עולה; מחיר מעל MA20.
 5. נתונים טובים: צמיחת הכנסות > 0, שולי רווח > 0 או צמיחת רווחים > 0.
 6. תוצאות טובות: הפתעת רווח חיובית בדוח האחרון (אם יש נתון).
 7. פוטנציאל: יעד מחיר ממוצע של אנליסטים ≥ UPSIDE_MIN מעל המחיר (אם יש נתון).

שימוש:
  python ma150_breakout_scanner.py                # נכון לסשן המסחר האחרון
  python ma150_breakout_scanner.py --asof 2026-09-11
  python ma150_breakout_scanner.py --universe sp500      # sp500 / nasdaq100 / nasdaq / all
  python ma150_breakout_scanner.py --no-email
"""
import argparse, io, os, sys, time, smtplib, datetime as dt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import numpy as np
import pandas as pd
import requests
import yfinance as yf

CONFIG = dict(
    LOOKBACK_CROSS=7,     # החצייה מעל MA150 קרתה בתוך N ימי מסחר אחרונים
    RVOL_MIN=1.5,
    MAX_EXT_150=0.10,     # עד 10% מעל MA150
    MAX_EXT_20=0.06,      # עד 6% מעל MA20
    RSI_MAX=70,
    MIN_MCAP=300e6,       # שווי שוק מינימלי
    MIN_DOLLAR_VOL=2e6,   # מחזור דולרי ממוצע (50 יום)
    MIN_PRICE=3.0,
    UPSIDE_MIN=0.15,
    MAX_FUNDAMENTAL_LOOKUPS=150,   # כמה מניות שעברו טכנית לבדוק פונדמנטלית
)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------------------------------- universe
def sp500_tickers():
    html = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                        headers=HEADERS, timeout=30).text
    df = pd.read_html(io.StringIO(html))[0]
    return [t.replace(".", "-") for t in df["Symbol"].astype(str)]

def nasdaq100_tickers():
    html = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=HEADERS, timeout=30).text
    for t in pd.read_html(io.StringIO(html)):
        if "Ticker" in t.columns:
            return [x.replace(".", "-") for x in t["Ticker"].astype(str)]
    return []

def nasdaq_all_tickers():
    txt = requests.get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                       headers=HEADERS, timeout=30).text
    df = pd.read_csv(io.StringIO(txt), sep="|")
    df = df[df["Symbol"].notna()]
    df = df[(df["Test Issue"] == "N") & (df["ETF"] == "N")]
    syms = [s for s in df["Symbol"].astype(str) if s.isalpha() and len(s) <= 5]
    return [s for s in syms if not s.endswith(("W", "R", "U"))]  # warrants/rights/units (grossly)

def build_universe(name):
    if name == "sp500":     return sorted(set(sp500_tickers()))
    if name == "nasdaq100": return sorted(set(nasdaq100_tickers()))
    if name == "nasdaq":    return sorted(set(nasdaq_all_tickers()))
    return sorted(set(sp500_tickers()) | set(nasdaq_all_tickers()))

# ---------------------------------------------------------------- indicators
def rsi(series, n=14):
    d = series.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def technical_pass(px: pd.DataFrame, asof: pd.Timestamp | None):
    """px: OHLCV of one ticker. returns dict or None."""
    px = px.dropna(subset=["Close", "Volume"])
    if asof is not None:
        px = px[px.index <= asof]
    if len(px) < 170:
        return None
    c, v = px["Close"], px["Volume"]
    ma20, ma50, ma150 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(150).mean()
    avgvol50 = v.rolling(50).mean()
    last = c.iloc[-1]; date = px.index[-1]
    if last < CONFIG["MIN_PRICE"] or (avgvol50.iloc[-1] * last) < CONFIG["MIN_DOLLAR_VOL"]:
        return None

    above = c > ma150
    if not above.iloc[-1]:
        return None
    lb = CONFIG["LOOKBACK_CROSS"]
    # החצייה קרתה בתוך lb ימים: לפחות יום אחד בחלון האחרון היה מתחת/שווה ל-MA150
    if above.iloc[-lb-1:-1].all():
        return None
    # ולפני החלון היה מתחת (לא סתם "ריצוד" סביב הממוצע במשך חודשים) – רוב ה-30 יום הקודמים מתחת
    if above.iloc[-lb-31:-lb-1].mean() > 0.5:
        return None

    rvol = v.iloc[-1] / avgvol50.iloc[-1]
    if rvol < CONFIG["RVOL_MIN"]:
        return None
    ext150 = last / ma150.iloc[-1] - 1
    ext20  = last / ma20.iloc[-1] - 1
    if ext150 > CONFIG["MAX_EXT_150"] or ext20 > CONFIG["MAX_EXT_20"] or ext20 < 0:
        return None
    r = rsi(c).iloc[-1]
    if r >= CONFIG["RSI_MAX"]:
        return None
    ma50_up = ma50.iloc[-1] > ma50.iloc[-10]
    if not (ma50.iloc[-1] > ma150.iloc[-1] or ma50_up):
        return None
    hi52 = c.iloc[-252:].max() if len(c) >= 252 else c.max()
    return dict(
        date=date.date(), price=round(float(last), 2), rvol=round(float(rvol), 2),
        ext150=round(100*float(ext150), 1), ext20=round(100*float(ext20), 1),
        rsi=round(float(r), 1), from_52w_high=round(100*(float(last)/float(hi52)-1), 1),
        ma50_gt_ma150=bool(ma50.iloc[-1] > ma150.iloc[-1]),
    )

# ---------------------------------------------------------------- fundamentals
def fundamentals(ticker):
    out = dict(mcap=None, rev_growth=None, eps_growth=None, margin=None,
               surprise=None, target_upside=None, sector=None, name=None)
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        out["name"] = info.get("shortName"); out["sector"] = info.get("sector")
        out["mcap"] = info.get("marketCap")
        out["rev_growth"] = info.get("revenueGrowth")
        out["eps_growth"] = info.get("earningsGrowth")
        out["margin"] = info.get("profitMargins")
        tp, p = info.get("targetMeanPrice"), info.get("currentPrice") or info.get("regularMarketPrice")
        if tp and p:
            out["target_upside"] = tp / p - 1
        try:
            ed = t.get_earnings_dates(limit=8)
            if ed is not None and "Surprise(%)" in ed.columns:
                s = ed["Surprise(%)"].dropna()
                if len(s):
                    out["surprise"] = float(s.iloc[0])
        except Exception:
            pass
    except Exception as e:
        out["err"] = str(e)[:80]
    return out

def fundamental_pass(f):
    if f.get("mcap") is not None and f["mcap"] < CONFIG["MIN_MCAP"]:
        return False, "שווי שוק נמוך"
    if f.get("rev_growth") is not None and f["rev_growth"] <= 0:
        return False, "הכנסות בירידה"
    ok_profit = (f.get("margin") or 0) > 0 or (f.get("eps_growth") or 0) > 0
    if not ok_profit:
        return False, "ללא רווחיות/צמיחת רווח"
    if f.get("surprise") is not None and f["surprise"] < 0:
        return False, "פספוס בדוח האחרון"
    if f.get("target_upside") is not None and f["target_upside"] < CONFIG["UPSIDE_MIN"]:
        return False, "אפסייד אנליסטים נמוך"
    return True, "עבר"

def score(row):
    s = 0
    s += min(row["rvol"], 4) * 10                     # עד 40
    s += max(0, 10 - row["ext150"]) * 2               # קרוב ל-MA150 = טוב, עד 20
    s += (row.get("rev_growth") or 0) * 50            # 20% צמיחה = 10
    s += (row.get("target_upside") or 0) * 50         # 30% אפסייד = 15
    s += 5 if row.get("ma50_gt_ma150") else 0
    s += min(max(row.get("surprise") or 0, 0), 20) / 2
    return round(s, 1)

# ---------------------------------------------------------------- main
def run(universe, asof, send_email):
    tickers = build_universe(universe)
    print(f"universe={universe} tickers={len(tickers)}")
    asof_ts = pd.Timestamp(asof) if asof else None
    end = (asof_ts + pd.Timedelta(days=1)) if asof_ts else None

    tech = {}
    BATCH = 200
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i+BATCH]
        for attempt in range(3):
            try:
                data = yf.download(chunk, period="1y", end=end, group_by="ticker",
                                   auto_adjust=False, threads=True, progress=False)
                break
            except Exception as e:
                print("download retry", attempt, e); time.sleep(5)
        else:
            continue
        for tk in chunk:
            try:
                px = data[tk] if len(chunk) > 1 else data
                res = technical_pass(px, asof_ts)
                if res: tech[tk] = res
            except Exception:
                pass
        print(f"  {i+len(chunk)}/{len(tickers)}  technical passes so far: {len(tech)}")

    rows = []
    for n, (tk, tr) in enumerate(sorted(tech.items(), key=lambda kv: -kv[1]["rvol"])):
        if n >= CONFIG["MAX_FUNDAMENTAL_LOOKUPS"]:
            break
        f = fundamentals(tk)
        ok, reason = fundamental_pass(f)
        row = dict(ticker=tk, **tr, **f, fund_ok=ok, fund_reason=reason)
        row["score"] = score(row)
        rows.append(row)
        time.sleep(0.3)

    df = pd.DataFrame(rows)
    if df.empty:
        print("no candidates"); winners = df
    else:
        df = df.sort_values(["fund_ok", "score"], ascending=[False, False])
        winners = df[df.fund_ok]
    os.makedirs("results", exist_ok=True)
    stamp = (asof or str(dt.date.today()))
    df.to_csv(f"results/ma150_breakout_{stamp}_all.csv", index=False)
    winners.to_csv(f"results/ma150_breakout_{stamp}.csv", index=False)
    print(winners[["ticker","price","rvol","ext150","rsi","rev_growth","target_upside","score"]]
          .to_string(index=False) if not winners.empty else "אין מניות שעברו את כל הסינונים")
    if send_email:
        email_report(winners, df, stamp, universe)

def pct(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100*x:.0f}%"

def email_report(w, all_df, stamp, universe):
    user, pwd, to = os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD"), os.getenv("MAIL_TO")
    if not (user and pwd and to):
        print("email secrets missing – skipping"); return
    if w.empty:
        body = f"<p>לא נמצאו מניות שעברו את כל הסינונים ({len(all_df)} עברו טכנית בלבד).</p>"
    else:
        trs = "".join(
            f"<tr><td><b>{r.ticker}</b><br><small>{r.name or ''}</small></td><td>{r.price}</td>"
            f"<td>{r.rvol}</td><td>{r.ext150}%</td><td>{r.rsi}</td><td>{pct(r.rev_growth)}</td>"
            f"<td>{pct(r.margin)}</td><td>{'-' if r.surprise is None or np.isnan(r.surprise) else f'{r.surprise:.0f}%'}</td>"
            f"<td>{pct(r.target_upside)}</td><td>{r.score}</td></tr>"
            for r in w.itertuples())
        body = f"""<table border="1" cellpadding="6" style="border-collapse:collapse;direction:rtl;text-align:right">
<tr style="background:#eee"><th>מניה</th><th>מחיר</th><th>RVOL</th><th>מרחק מ-MA150</th><th>RSI</th>
<th>צמיחת הכנסות</th><th>שולי רווח</th><th>הפתעת דוח</th><th>אפסייד אנליסטים</th><th>ציון</th></tr>{trs}</table>"""
    html = f"""<html><body dir="rtl" style="font-family:Arial;direction:rtl;text-align:right">
<h2>פריצות MA150 – {universe} – נכון ל-{stamp}</h2>
<p>{len(all_df)} מניות עברו סינון טכני, {len(w)} עברו גם פונדמנטלי.</p>{body}
<p><small>תנאים: חצייה טרייה מעל MA150 (עד {CONFIG['LOOKBACK_CROSS']} ימים), RVOL≥{CONFIG['RVOL_MIN']},
עד {int(100*CONFIG['MAX_EXT_150'])}% מעל MA150, RSI<{CONFIG['RSI_MAX']}, צמיחת הכנסות חיובית, דוח אחרון ללא פספוס,
אפסייד אנליסטים ≥{int(100*CONFIG['UPSIDE_MIN'])}%.</small></p></body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[פריצות MA150] {len(w)} מועמדות – {stamp}"
    msg["From"], msg["To"] = user, to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd); s.sendmail(user, to.split(","), msg.as_string())
    print("email sent")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="all", choices=["sp500", "nasdaq100", "nasdaq", "all"])
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD (למשל 2026-09-11)")
    ap.add_argument("--no-email", action="store_true")
    a = ap.parse_args()
    run(a.universe, a.asof, not a.no_email)
