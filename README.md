# Nord Pool Bot (FR + GER): Day-ahead, IDA1/2/3, Intraday VWAP

This repo runs a daily "agent mode" job in GitHub Actions to fetch:
- Day-ahead prices (Auction)
- IDA1 / IDA2 / IDA3 prices (Auction)
- Intraday continuous VWAP (using Intraday HourlyStatistics averagePrice)

## Output
Artifacts are uploaded in Actions runs:
- artifacts/raw/... (raw JSON per dataset/date)
- artifacts/tidy/auction_prices.csv
- artifacts/tidy/intraday_vwap.csv

## Schedules
GitHub Actions cron is UTC only. We run hourly and the script only executes at 12:00 Europe/Paris
(works across DST).

## Configuration (GitHub → Settings → Secrets and variables → Actions)
Variables (optional):
- AREAS: "FR,GER"
- CURRENCY: "EUR"
- START_DATE: "2026-03-01"
- AUCTION_MARKETS: "DayAhead,IntradayAuction1,IntradayAuction2,IntradayAuction3"

Secrets (optional):
- NORDPOOL_API_KEY: if your access requires it

## Manual backfill
Actions → "Nord Pool Bot" → Run workflow
Set input `backfill` to true to download from START_DATE up to yesterday.
