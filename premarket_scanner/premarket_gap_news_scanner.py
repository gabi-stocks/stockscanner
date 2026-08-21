#!/usr/bin/env python3
"""
Pre-market Gap + News Scanner
==============================
Scans NASDAQ-listed stocks for:
  1. Pre-market gap >= GAP_THRESHOLD_PCT
  2. Market cap >= MIN_MARKET_CAP
  3. Recent news matching one of the defined catalyst categories:
       - FDA approval / regulatory clearance
       - New signed contract
       - Technological breakthrough
       - Successful / significant research results

Sends a Hebrew RTL HTML email report via Gmail SMTP, matching the
existing onestockbreakup / stockscanner project conventions.

Required GitHub Secrets (same names as other scanners in this account):
  GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO

Data sources (all free tier):
  - Ticker universe: NASDAQ Trader symbol directory (public, no key)
  - Price / pre-market / market cap: yfinance
  - News: yfinance .news (falls back gracefully if empty)

KNOWN LIMITATIONS (read before relying on this in production):
  - yfinance pre-market fields are unofficial/scraped from Yahoo and can be
    missing, stale, or rate-limited for some tickers. This is the main
    reliability risk in the whole pipeline.
  - Scanning the full NASDAQ list (~4000+ tickers) against yfinance is slow
    and can get you rate-limited. UNIVERSE_LIMIT below caps it for safety -
    raise it once you've confirmed timing/rate-limit behavior.
  - News classification here is keyword-based (fast, free, no extra key).
    It will have false positives/negatives. See classify_news() to swap in
    an LLM-based classifier (e.g. Claude API) for higher precision later.
"""

import os
import re
import time
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("premarket_scanner")

# ----------------------------- CONFIG ---------------------------------

GAP_THRESHOLD_PCT = 50.0          # minimum pre-market gap %
MIN_MARKET_CAP = 100_000_000      # $100M

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"

# Safety cap on how many tickers to check per run (yfinance is not built for
# scanning thousands of tickers quickly). Raise gradually once you've timed
# a run and checked you're not getting rate-limited.
UNIVERSE_LIMIT = 800

# Keyword rules per catalyst category (case-insensitive, matched against
# news title + summary). Expand these lists as you see misses.
NEWS_CATEGORIES = {
    "FDA / רגולציה": [
        r"\bfda\b", r"approv(al|ed|es)", r"clearance", r"regulatory",
        r"breakthrough therapy designation", r"orphan drug designation",
        r"emergency use authorization", r"\beua\b", r"\bce mark\b",
    ],
    "חוזה חדש": [
        r"signs? (a |an )?(new |multi-year )?contract",
        r"signs? (a |an )?agreement", r"awarded (a |an )?contract",
        r"partnership with", r"strikes deal", r"secures? (a |an )?deal",
        r"purchase order",
    ],
    "פריצת דרך טכנולוגית": [
        r"breakthrough", r"first-in-(the-)?world", r"unveils?",
        r"patent (granted|issued)", r"proprietary technology",
        r"next-generation",
    ],
    "תוצאות מחקר מוצלחות": [
        r"positive (top-?line )?results", r"met (its |the )?primary endpoint",
        r"statistically significant", r"successful trial",
        r"phase (1|2|3|i|ii|iii).{0,30}(results|success|met)",
        r"study (shows|demonstrates)",
    ],
}

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MAIL_TO = os.environ.get("MAIL_TO")


# --------------------------- UNIVERSE -----------------------------------

def fetch_nasdaq_universe(limit=UNIVERSE_LIMIT):
    """Pull the official NASDAQ-listed symbol directory (free, no key)."""
    resp = requests.get(NASDAQ_LISTED_URL, timeout=20)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    tickers = []
    for line in lines[1:]:  # skip header
        parts = line.split("|")
        if len(parts) < 2:
            continue
        symbol, name = parts[0], parts[1]
        if not symbol or not re.match(r"^[A-Z]{1,5}$", symbol):
            continue
        tickers.append(symbol)
    log.info(f"NASDAQ universe: {len(tickers)} symbols (using first {limit})")
    return tickers[:limit]


# ------------------------------ SCAN -------------------------------------

def get_premarket_snapshot(ticker):
    """Return dict with pre-market price, prev close, gap %, market cap -
    or None if data unavailable/incomplete for this ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.get_info()
        pre_price = info.get("preMarketPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        market_cap = info.get("marketCap")

        if not pre_price or not prev_close or not market_cap:
            return None

        gap_pct = (pre_price - prev_close) / prev_close * 100
        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "pre_price": pre_price,
            "prev_close": prev_close,
            "gap_pct": gap_pct,
            "market_cap": market_cap,
        }
    except Exception as e:
        log.debug(f"{ticker}: skipped ({e})")
        return None


def classify_news(title, summary=""):
    """Keyword match against NEWS_CATEGORIES. Returns list of matched
    category names (can be more than one)."""
    text = f"{title} {summary}".lower()
    matched = []
    for category, patterns in NEWS_CATEGORIES.items():
        if any(re.search(p, text) for p in patterns):
            matched.append(category)
    return matched


def get_matching_news(ticker, max_items=10):
    """Pull recent news for a ticker and return items matching our
    catalyst categories."""
    try:
        news_items = yf.Ticker(ticker).news or []
    except Exception as e:
        log.debug(f"{ticker}: news fetch failed ({e})")
        return []

    matches = []
    for item in news_items[:max_items]:
        content = item.get("content", item)
        title = content.get("title", "")
        summary = content.get("summary", "")
        link = content.get("canonicalUrl", {}).get("url") if isinstance(
            content.get("canonicalUrl"), dict) else content.get("link", "")

        categories = classify_news(title, summary)
        if categories:
            matches.append({
                "title": title,
                "link": link,
                "categories": categories,
            })
    return matches


def scan():
    universe = fetch_nasdaq_universe()
    candidates = []

    for i, ticker in enumerate(universe):
        if i and i % 100 == 0:
            log.info(f"...checked {i}/{len(universe)}")

        snap = get_premarket_snapshot(ticker)
        if not snap:
            continue
        if snap["gap_pct"] < GAP_THRESHOLD_PCT:
            continue
        if snap["market_cap"] < MIN_MARKET_CAP:
            continue

        news_matches = get_matching_news(ticker)
        if not news_matches:
            continue

        snap["news"] = news_matches
        candidates.append(snap)
        log.info(f"MATCH: {ticker} gap={snap['gap_pct']:.1f}% cap=${snap['market_cap']/1e6:.0f}M "
                  f"categories={[c for m in news_matches for c in m['categories']]}")

        time.sleep(0.3)

    return candidates


# ------------------------------ EMAIL -------------------------------------

def build_html_report(candidates):
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    if not candidates:
        rows = "<p>לא נמצאו מניות שעומדות בקריטריונים הבוקר.</p>"
    else:
        rows = ""
        for c in candidates:
            news_html = "<ul>"
            for n in c["news"]:
                cats = ", ".join(n["categories"])
                news_html += (
                    f"<li><a href='{n['link']}'>{n['title']}</a> "
                    f"<b>[{cats}]</b></li>"
                )
            news_html += "</ul>"

            rows += f"""
            <div style='border:1px solid #ccc; border-radius:8px; padding:12px; margin-bottom:12px;'>
                <h3>{c['ticker']} — {c['name']}</h3>
                <p>קפיצה בטרום מסחר: <b>{c['gap_pct']:.1f}%</b>
                   (${c['prev_close']:.2f} → ${c['pre_price']:.2f})</p>
                <p>שווי שוק: <b>${c['market_cap']/1e6:,.0f}M</b></p>
                {news_html}
            </div>
            """

    return f"""
    <html dir="rtl" lang="he">
    <body style="font-family: Arial, sans-serif;">
        <h2>סריקת קפיצות טרום-מסחר — {now_str}</h2>
        <p>קריטריונים: gap ≥ {GAP_THRESHOLD_PCT}% | שווי שוק ≥ ${MIN_MARKET_CAP/1e6:.0f}M |
           חדשות: FDA/רגולציה, חוזה חדש, פריצת דרך טכנולוגית, תוצאות מחקר מוצלחות</p>
        {rows}
    </body>
    </html>
    """


def send_email(html_body, subject="סריקת קפיצות טרום-מסחר - NASDAQ"):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MAIL_TO):
        log.warning("Missing GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO — printing report instead of emailing.")
        print(html_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = MAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, MAIL_TO.split(","), msg.as_string())

    log.info("Email sent.")


# ------------------------------ MAIN ---------------------------------------

if __name__ == "__main__":
    log.info("Starting pre-market gap + news scan...")
    results = scan()
    html = build_html_report(results)
    send_email(html)
    log.info(f"Done. {len(results)} candidate(s) found.")
