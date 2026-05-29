import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta
import os
import time

# ==========================================
# CREATE OUTPUT FOLDER
# ==========================================

os.makedirs("output", exist_ok=True)

# ==========================================
# DOWNLOAD MIDCAP + SMALLCAP LIST
# ==========================================

midcap_url = "https://archives.nseindia.com/content/indices/ind_niftymidcap100list.csv"
smallcap_url = "https://archives.nseindia.com/content/indices/ind_niftysmallcap100list.csv"

midcap_df = pd.read_csv(midcap_url)
smallcap_df = pd.read_csv(smallcap_url)

midcap = [x + ".NS" for x in midcap_df["Symbol"]]
smallcap = [x + ".NS" for x in smallcap_df["Symbol"]]

stocks = list(set(midcap + smallcap))

# ==========================================
# SECTOR INDICES
# ==========================================

sector_indices = {
    "Technology": "^CNXIT",
    "Financial Services": "^NSEBANK",
    "Healthcare": "^CNXPHARMA",
    "Automotive": "^CNXAUTO",
    "Energy": "^CNXENERGY",
    "Industrials": "^CNXINFRA",
    "Consumer Defensive": "^CNXFMCG",
    "Basic Materials": "^CNXMETAL"
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
            period="10d",
            interval="1d",
            progress=False
        )

        # FIX 1: Flatten MultiIndex columns from yfinance
        if isinstance(sector_data.columns, pd.MultiIndex):
            sector_data.columns = sector_data.columns.get_level_values(0)

        # FIX 2: Guard against empty or insufficient data
        if sector_data.empty or len(sector_data) < 2:
            print(f"Not enough data for sector: {sector}")
            sector_performance[sector] = 0
            continue

        latest = float(sector_data["Close"].iloc[-1])

        # FIX 3: Use min of available rows instead of hardcoded -6
        lookback = min(6, len(sector_data))
        prev_week = float(sector_data["Close"].iloc[-lookback])

        weekly_gain = ((latest - prev_week) / prev_week) * 100

        sector_performance[sector] = round(weekly_gain, 2)

    except Exception as e:

        print(f"Sector error {sector}: {e}")
        sector_performance[sector] = 0

print(sector_performance)

# ==========================================
# ECONOMIC TIMES NEWS
# ==========================================

def get_et_news(company_name):

    headlines = []

    try:

        # FIX 4: Target specific article elements instead of all <a> tags
        search_query = company_name.replace(" ", "-").lower()

        url = (
            f"https://economictimes.indiatimes.com/topic/"
            f"{search_query}"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(response.text, "lxml")

        # Target story containers specifically
        story_containers = soup.find_all("div", class_="eachStory")

        for story in story_containers:
            headline_tag = story.find("h3") or story.find("a")
            if headline_tag:
                text = headline_tag.get_text(strip=True)
                if len(text) > 40:
                    headlines.append(text)

        # Fallback: grab <h3> tags if eachStory not found
        if not headlines:
            for h3 in soup.find_all("h3"):
                text = h3.get_text(strip=True)
                if len(text) > 40:
                    headlines.append(text)

        headlines = list(dict.fromkeys(headlines))

        return headlines[:5]

    except Exception as e:

        print(f"News error for {company_name}: {e}")
        return []

# ==========================================
# MAIN SCANNER
# ==========================================

results = []

print(f"Scanning {len(stocks)} stocks...")

for stock in stocks:

    try:

        print(f"Checking {stock}")

        data = yf.download(
            stock,
            period="1mo",
            interval="1d",
            progress=False
        )

        # FIX 1: Flatten MultiIndex columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if len(data) < 21:
            continue

        # FIX 5: Extract scalars explicitly to avoid Series arithmetic issues
        latest_close = float(data["Close"].iloc[-1])
        prev_close = float(data["Close"].iloc[-2])
        latest_volume = float(data["Volume"].iloc[-1])

        daily_return = ((latest_close - prev_close) / prev_close) * 100

        avg_volume = float(data["Volume"].tail(20).mean())

        # FIX 2: Guard against zero volume
        if avg_volume == 0:
            continue

        volume_spike = latest_volume / avg_volume

        # FILTERS
        if daily_return < 7:
            continue

        if volume_spike < 2:
            continue

        # STOCK INFO
        ticker_obj = yf.Ticker(stock)
        info = ticker_obj.info

        company_name = info.get("shortName", stock)
        sector = info.get("sector", "Unknown")
        market_cap = info.get("marketCap", 0)

        sector_gain = sector_performance.get(sector, 0)

        # FETCH NEWS
        news = get_et_news(company_name)

        results.append({

            "Date": str(datetime.now()),

            "Stock": stock,

            "Company": company_name,

            "Daily Gain %": round(daily_return, 2),

            "Volume Spike": round(volume_spike, 2),

            "Sector": sector,

            "Sector Weekly Gain %": sector_gain,

            "Market Cap": market_cap,

            "Economic Times News": "\n".join(news)

        })

        # FIX 6: Reduced sleep to 0.3s for better performance
        time.sleep(0.3)

    except Exception as e:

        print(f"Error in {stock}: {e}")

# ==========================================
# FINAL OUTPUT
# ==========================================

df = pd.DataFrame(results)

if len(df) > 0:

    df = df.sort_values(by="Daily Gain %", ascending=False)

    print("\nFINAL RESULTS:\n")
    print(df)

    # SAVE LATEST CSV
    df.to_csv("output/latest_scan.csv", index=False)

    # SAVE HISTORY CSV
    history_file = f"output/scan_{datetime.now().date()}.csv"
    df.to_csv(history_file, index=False)

    print("\nCSV FILES SAVED.")

else:

    print("\nNo momentum stocks found.")
