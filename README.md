# flight-monitor

An agent that watches flight prices for a multi-leg trip and pings you on
Telegram when something gets cheaper.

Built for a **Milan → San Francisco → Anchorage** August trip: it prices the
two round trips that make up the journey and tracks the combined total.
Everything is driven by `config.yml`, so it works for any trip.

## What it does

Once a day (GitHub Actions cron):

1. Reads the **segments** from `config.yml`. Each segment is a round trip with
   one or more candidate date pairs:
   - `MXP ⇄ SFO` (long-haul, visit cousin near SF)
   - `SFO ⇄ ANC` (Alaska hop)
   - `MXP ⇄ ANC` direct — baseline only, not part of the total
2. Prices every date option via the **SerpAPI Google Flights** engine (real
   Google Flights data, no scraping, no CAPTCHA).
3. Keeps the cheapest option per segment and sums the segments flagged
   `in_total` → the **trip total**.
4. Diffs everything against the previous snapshot in `state/prices.json`.
5. Sends a Telegram message if:
   - any tracked option (or the trip total) dropped ≥ `alert_drop_pct`, or
   - a new date option is ≥ `alert_new_route_pct` cheaper than the prior
     cheapest in its segment.
6. Commits the updated snapshot back to the repo.

## Setup

### 1. Get a SerpAPI key

1. Sign up free at https://serpapi.com (100 searches/month on the free plan).
2. Dashboard → copy **Your Private API Key**.

### 2. Get a Telegram bot

1. On Telegram, message `@BotFather` → `/newbot` → copy the token.
2. Send your new bot any message (so it can see your chat).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and find
   `"chat":{"id":123456789}` — that's your `TELEGRAM_CHAT_ID`.

### 3. Local install

```bash
cd flight-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in the three values, then:
set -a; source .env; set +a
```

### 4. First run — seed the baseline

```bash
python -m src.main --seed
```

Snapshots current prices and exits. No Telegram message.

### 5. Test the diff path

```bash
python -m src.main --dry-run
```

Runs a normal check, prints any alerts to stdout, updates state. No Telegram.

### 6. Live run

```bash
python -m src.main
```

Sends a Telegram message if there are alerts.

## Deploy to GitHub Actions

1. Push this folder to a GitHub repo.
2. Settings → Secrets and variables → Actions → add:
   - `SERPAPI_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. The workflow runs daily at 07:00 UTC and on the "Run workflow" button.

The workflow commits the updated `state/prices.json` so the diff persists
between runs.

## Tuning

Everything lives in `config.yml`:

| Knob | Effect |
|------|--------|
| `segments` | The round trips to track (departure, arrival, date options) |
| `date_options` | Candidate `{outbound, return}` pairs per segment |
| `in_total` | Whether a segment counts toward the trip total (set `false` for baselines) |
| `travel_class` | 1=economy, 2=premium, 3=business, 4=first |
| `adults` / `currency` | Passenger count and currency |
| `alert_drop_pct` | % drop on a tracked option (or total) that triggers an alert |
| `alert_new_route_pct` | How much cheaper a new date option must be vs the prior cheapest in its segment |

## API budget

```
3 segments × ~2 date options = ~5 SerpAPI calls per run
```

- **SerpAPI** free plan = 100 searches/month. A daily run uses ~150/month,
  slightly over free — either run every other day (change the cron), trim
  date options, or upgrade the SerpAPI plan.
- **GitHub Actions**: free for public repos.
- **Telegram bot**: free.

## What this does NOT do

- It doesn't book anything. Alerts link to Google Flights; you book there.
- It treats each segment as an independent round trip (two tickets). It does
  not search a single multi-city ticket. For Italy→SF→Alaska, two round trips
  is the natural structure since you bookend the trip in San Francisco.
- Prices are base fares from Google Flights — no baggage/seat add-ons.
