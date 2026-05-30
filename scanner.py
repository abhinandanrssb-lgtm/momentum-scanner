import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta
import os
import time
from io import StringIO

# ==========================================
# CREATE OUTPUT FOLDER
# ==========================================

os.makedirs("output", exist_ok=True)

# ==========================================
# DOWNLOAD ALL STOCK LISTS
# FIX: Added Nifty 500 + Midcap 150 + Smallcap 250
# ==========================================

INDEX_URLS = {
    "nifty500":    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "midcap150":   "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "smallcap250": "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "midcap100":   "https://archives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
    "smallcap100": "https://archives.nseindia.com/content/indices/ind_niftysmallcap100list.csv",
}

all_symbols = set()

headers_dl = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com"
}

for name, url in INDEX_URLS.items():
    try:
        resp = requests.get(url, headers=headers_dl, timeout=15)
        resp.raise_for_status()
        df_temp = pd.read_csv(StringIO(resp.text))
        col = [c for c in df_temp.columns if "Symbol" in c][0]
        syms = [s.strip() + ".NS" for s in df_temp[col].dropna()]
        all_symbols.update(syms)
        print(f"  {name}: loaded {len(syms)} symbols")
    except Exception as e:
        print(f"  WARNING: Could not load {name}: {e}")

stocks = list(all_symbols)
print(f"\nTotal unique stocks to scan: {len(stocks)}\n")

# ==========================================
# SECTOR INDICES
# ==========================================

sector_indices = {
    "Technology":         "^CNXIT",
    "Financial Services": "^NSEBANK",
    "Healthcare":         "^CNXPHARMA",
    "Automotive":         "^CNXAUTO",
    "Energy":             "^CNXENERGY",
    "Industrials":        "^CNXINFRA",
    "Consumer Defensive": "^CNXFMCG",
    "Basic Materials":    "^CNXMETAL"
}

# ==========================================
# FETCH SECTOR PERFORMANCE
# ==========================================

sector_performance = {}

print("Fetching sector performance...")

for sector, ticker in sector_indices.items():
    try:
        sector_data = yf.download(
            ticker,
            period="15d",
            interval="1d",
            progress=False
        )

        if isinstance(sector_data.columns, pd.MultiIndex):
            sector_data.columns = sector_data.columns.get_level_values(0)

        if sector_data.empty or len(sector_data) < 2:
            print(f"  Not enough data for sector: {sector}")
            sector_performance[sector] = 0.0
            continue

        latest    = float(sector_data["Close"].iloc[-1])
        lookback  = min(6, len(sector_data))
        prev_week = float(sector_data["Close"].iloc[-lookback])

        weekly_gain = ((latest - prev_week) / prev_week) * 100
        sector_performance[sector] = round(weekly_gain, 2)
        print(f"  {sector}: {sector_performance[sector]}%")

    except Exception as e:
        print(f"  Sector error {sector}: {e}")
        sector_performance[sector] = 0.0

# ==========================================
# NEWS: LAST 2 DAYS — ECONOMIC TIMES
# ==========================================

def get_et_news(company_name):
    """Fetch last 2 days of headlines from Economic Times."""
    headlines = []
    cutoff = datetime.now() - timedelta(days=2)

    try:
        search_query = company_name.strip().replace(" ", "-").lower()
        url = f"https://economictimes.indiatimes.com/topic/{search_query}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://economictimes.indiatimes.com"
        }

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")

        # Strategy 1: eachStory divs with date filtering
        story_blocks = soup.find_all("div", class_="eachStory")

        for block in story_blocks:
            date_tag = (
                block.find("time") or
                block.find("span", class_="date-format") or
                block.find("span", class_=lambda c: c and "date" in c.lower() if c else False)
            )

            article_date = None
            if date_tag:
                date_text = (date_tag.get("datetime") or date_tag.get_text(strip=True) or "")[:19]
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%d %b %Y", "%Y-%m-%d"]:
                    try:
                        article_date = datetime.strptime(date_text, fmt)
                        break
                    except Exception:
                        continue

            # Skip articles older than 2 days (only when date is parseable)
            if article_date and article_date < cutoff:
                continue

            headline_tag = block.find("h3") or block.find("a")
            if headline_tag:
                text = headline_tag.get_text(strip=True)
                if len(text) > 40:
                    headlines.append(text)

        # Strategy 2: fallback h3 tags
        if not headlines:
            for h3 in soup.find_all("h3"):
                text = h3.get_text(strip=True)
                if len(text) > 40:
                    headlines.append(text)

        return list(dict.fromkeys(headlines))[:5]

    except Exception as e:
        print(f"  ET news error for {company_name}: {e}")
        return []


# ==========================================
# NEWS: LAST 2 DAYS — YFINANCE (RELIABLE)
# ==========================================

def get_yf_news(symbol_ns):
    """Fetch last 2 days of news via yfinance (most reliable source)."""
    headlines = []
    cutoff = datetime.now() - timedelta(days=2)

    try:
        ticker_obj = yf.Ticker(symbol_ns)
        news_items = ticker_obj.news or []

        for item in news_items:
            pub_ts = item.get("providerPublishTime", 0)
            pub_dt = datetime.fromtimestamp(pub_ts) if pub_ts else None

            if pub_dt and pub_dt < cutoff:
                continue

            title = item.get("title", "").strip()
            if title and len(title) > 10:
                pub_str = pub_dt.strftime("%d %b %H:%M") if pub_dt else ""
                headlines.append(f"[{pub_str}] {title}" if pub_str else title)

        return headlines[:5]

    except Exception as e:
        print(f"  YF news error for {symbol_ns}: {e}")
        return []


# ==========================================
# MAIN SCANNER
# ==========================================

results = []

print(f"\nScanning {len(stocks)} stocks...\n")

for i, stock in enumerate(stocks, 1):

    try:
        print(f"[{i}/{len(stocks)}] {stock}")

        data = yf.download(
            stock,
            period="2mo",
            interval="1d",
            progress=False
        )

        # Flatten MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if data.empty or len(data) < 21:
            continue

        # FIX: Scalar extraction — avoids Series comparison bugs
        latest_close  = float(data["Close"].iloc[-1])
        prev_close    = float(data["Close"].iloc[-2])
        latest_volume = float(data["Volume"].iloc[-1])
        latest_date   = data.index[-1]

        # FIX: Daily gain
        daily_return = ((latest_close - prev_close) / prev_close) * 100

        # 20-day average volume
        avg_volume_20 = float(data["Volume"].tail(20).mean())

        if avg_volume_20 == 0:
            continue

        volume_spike = latest_volume / avg_volume_20

        # ---- FILTERS ----
        if daily_return < 5:
            continue
        if volume_spike < 1.5:
            continue

        # ---- EXTRA METRICS ----

        # Week gain
        lookback_w   = min(6, len(data))
        week_close   = float(data["Close"].iloc[-lookback_w])
        week_return  = ((latest_close - week_close) / week_close) * 100

        # 52-week high / low
        lookback_52  = min(252, len(data))
        high_52w     = float(data["Close"].tail(lookback_52).max())
        low_52w      = float(data["Close"].tail(lookback_52).min())
        dist_52w_high = ((latest_close - high_52w) / high_52w) * 100

        # RSI (14-day)
        delta  = data["Close"].diff()
        gain   = delta.clip(lower=0)
        loss   = -delta.clip(upper=0)
        avg_g  = gain.rolling(14).mean()
        avg_l  = loss.rolling(14).mean()
        rs     = avg_g / avg_l.replace(0, float("nan"))
        rsi_s  = 100 - (100 / (1 + rs))
        rsi    = round(float(rsi_s.iloc[-1]), 1) if not rsi_s.empty else 0.0

        # ---- STOCK INFO ----
        ticker_obj   = yf.Ticker(stock)
        info         = ticker_obj.info

        company_name = info.get("shortName", stock)
        sector       = info.get("sector", "Unknown")
        market_cap   = info.get("marketCap", 0)
        pe_ratio     = info.get("trailingPE", None)
        sector_gain  = sector_performance.get(sector, 0.0)

        # ---- NEWS: LAST 2 DAYS ----
        et_news  = get_et_news(company_name)
        yf_news  = get_yf_news(stock)

        # Merge, deduplicate
        all_news = list(dict.fromkeys(yf_news + et_news))[:6]

        results.append({
            "Date":                  str(latest_date.date()),
            "Stock":                 stock,
            "Company":               company_name,
            "Sector":                sector,
            "Close Price":           round(latest_close, 2),
            "Daily Gain %":          round(daily_return, 2),
            "Week Gain %":           round(week_return, 2),
            "Volume Spike (x avg)":  round(volume_spike, 2),
            "RSI (14d)":             rsi,
            "52W High":              round(high_52w, 2),
            "52W Low":               round(low_52w, 2),
            "Dist from 52W High %":  round(dist_52w_high, 2),
            "Sector Weekly Gain %":  sector_gain,
            "Market Cap":            market_cap,
            "P/E Ratio":             round(pe_ratio, 2) if pe_ratio else "N/A",
            "News (Last 2 Days)":    "\n".join(all_news) if all_news else "No recent news",
        })

        time.sleep(0.3)

    except Exception as e:
        print(f"  Error in {stock}: {e}")

# ==========================================
# FINAL OUTPUT
# ==========================================

df = pd.DataFrame(results)

if len(df) > 0:

    df = df.sort_values(by="Daily Gain %", ascending=False)

    print("\n" + "="*70)
    print("MOMENTUM STOCKS — FINAL RESULTS")
    print("="*70)
    print(df[[
        "Stock", "Company", "Daily Gain %",
        "Volume Spike (x avg)", "RSI (14d)", "Sector"
    ]].to_string(index=False))

    latest_path  = "output/latest_scan.csv"
    history_path = f"output/scan_{datetime.now().date()}.csv"

    df.to_csv(latest_path, index=False)
    df.to_csv(history_path, index=False)

    print(f"\nSaved {len(df)} stocks → {latest_path}")
    print(f"History → {history_path}")

else:
    print("\nNo momentum stocks found today.")
