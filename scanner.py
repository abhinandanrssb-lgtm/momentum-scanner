import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime
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

        latest = sector_data["Close"].iloc[-1]
        prev_week = sector_data["Close"].iloc[-6]

        weekly_gain = ((latest - prev_week) / prev_week) * 100

        sector_performance[sector] = round(
            float(weekly_gain),
            2
        )

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

        search_query = company_name.replace(" ", "-")

        url = (
            f"https://economictimes.indiatimes.com/topic/"
            f"{search_query}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        articles = soup.find_all("a")

        for article in articles:

            text = article.get_text(strip=True)

            if len(text) > 40:
                headlines.append(text)

        headlines = list(dict.fromkeys(headlines))

        return headlines[:5]

    except Exception as e:

        print(f"News error: {e}")

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

        if len(data) < 21:
            continue

        latest = data.iloc[-1]
        prev = data.iloc[-2]

        daily_return = (
            (latest["Close"] - prev["Close"])
            / prev["Close"]
        ) * 100

        avg_volume = (
            data["Volume"]
            .tail(20)
            .mean()
        )

        volume_spike = (
            latest["Volume"]
            / avg_volume
        )

        # FILTERS

        if daily_return < 7:
            continue

        if volume_spike < 2:
            continue

        # STOCK INFO

        ticker = yf.Ticker(stock)

        info = ticker.info

        company_name = info.get(
            "shortName",
            stock
        )

        sector = info.get(
            "sector",
            "Unknown"
        )

        market_cap = info.get(
            "marketCap",
            0
        )

        sector_gain = sector_performance.get(
            sector,
            0
        )

        # FETCH NEWS

        news = get_et_news(company_name)

        results.append({

            "Date": str(datetime.now()),

            "Stock": stock,

            "Company": company_name,

            "Daily Gain %": round(
                float(daily_return),
                2
            ),

            "Volume Spike": round(
                float(volume_spike),
                2
            ),

            "Sector": sector,

            "Sector Weekly Gain %": sector_gain,

            "Market Cap": market_cap,

            "Economic Times News":
                "\n".join(news)

        })

        time.sleep(1)

    except Exception as e:

        print(f"Error in {stock}: {e}")

# ==========================================
# FINAL OUTPUT
# ==========================================

df = pd.DataFrame(results)

if len(df) > 0:

    df = df.sort_values(
        by="Daily Gain %",
        ascending=False
    )

    print("\nFINAL RESULTS:\n")

    print(df)

    # SAVE LATEST CSV

    df.to_csv(
        "output/latest_scan.csv",
        index=False
    )

    # SAVE HISTORY CSV

    history_file = (
        f"output/scan_"
        f"{datetime.now().date()}.csv"
    )

    df.to_csv(
        history_file,
        index=False
    )

    print("\nCSV FILES SAVED.")

else:

    print("\nNo momentum stocks found.")
