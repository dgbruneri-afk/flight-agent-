# flight-monitor

An agent that watches flight prices for your routes and pings you on Telegram
when something gets cheaper.

Built for the Italy → Anchorage Aug 6–20 trip, but the route grid is just a
YAML file — change `config.yml` for any other trip.

## What it does

Every 6 hours (GitHub Actions cron):

1. Builds a search grid from `config.yml`:
   - 4 Italian origins (MXP, LIN, BGY, FCO)
   - 2 destinations (ANC primary, FAI for open-jaw)
   - Outbound Aug 6 ± 2 days, return Aug 20 ± 2 days
   - Three routing flavors: direct round-trip, open-jaw, and multi-city via
     a US hub (SFO / SEA / LAX, rotated per query so all hubs get covered)
2. Calls Amadeus Flight Offers Search for each permutation.
3. Diffs against the previous snapshot stored in `state/prices.json`.
4. If a known route dropped ≥10%, OR a newly-seen route is ≥15% cheaper than
   the current cheapest, sends a Telegram message with the route, price,
   carriers, and a Google Flights link.
5. Commits the updated snapshot back to the repo.

## Setup

### 1. Get an Amadeus API key

1. Sign up at https://developers.amadeus.com (free).
2. Create a new "Self-Service" app.
3. Copy the **API Key** and **API Secret**.
4. The "test" environment returns fake data — fine for first wiring it up.
   Switch `AMADEUS_HOSTNAME=production` once you want real prices. Production
   is also free under the Self-Service quota (2k calls/month, plenty here).

### 2. Get a Telegram bot

1. On Telegram, message `@BotFather` → `/newbot` → follow prompts → copy the
   token it gives you.
2. Send your new bot any message (just "hi" is fine — it needs to be the one
   to initiate so the bot can see your chat).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. Find
   `"chat":{"id":123456789}` — that's your `TELEGRAM_CHAT_ID`.

### 3. Local install

```bash
cd flight-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in the four values, then:
set -a; source .env; set +a
```

### 4. First run — seed the baseline

The first run must populate `state/prices.json` without alerting on
everything as "new":

```bash
python -m src.main --seed
```

This snapshots current prices and exits. No Telegram message.

### 5. Test the diff path

```bash
python -m src.main --dry-run
```

This runs a normal check, prints any alerts to stdout, and updates state.
No Telegram message.

### 6. Live run

```bash
python -m src.main
```

If there are alerts, you'll get a Telegram message.

## Deploy to GitHub Actions

1. Push this folder to a GitHub repo.
2. In repo Settings → Secrets and variables → Actions, add:
   - `AMADEUS_API_KEY`
   - `AMADEUS_API_SECRET`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. (Optional) Add a repository **variable** `AMADEUS_HOSTNAME` set to `test`
   while validating; remove it (or set to `production`) for real data.
4. Push. The workflow runs every 6 hours and on the "Run workflow" button.

The workflow commits the updated `state/prices.json` back to the repo so the
diff persists between runs.

## Tuning

Everything tunable lives in `config.yml`:

| Knob | Effect |
|------|--------|
| `origins` / `destinations` | The set of airports the grid covers |
| `outbound_target` / `return_target` / `date_flex_days` | Date window |
| `include_direct_roundtrip` / `include_open_jaw` / `include_stopover_multicity` | Toggle which routing flavors to search |
| `stopover_hubs` | Which US hubs are tried for the multi-city flavor |
| `alert_drop_pct` | % drop on a known route that triggers an alert |
| `alert_new_route_pct` | How much cheaper a new route must be vs current cheapest to alert |
| `max_results_per_query` | Top N cheapest kept per permutation |
| `nonstop_only` | Force nonstop (often no nonstop exists Italy↔ANC, leave false) |

## What this does NOT do

- It doesn't book anything. Telegram alerts include a Google Flights link;
  you click through to book.
- It doesn't model two-separate-tickets stitching (e.g. buy MXP→SFO on one
  airline + SFO→ANC on another as two PNRs). The multi-city flavor uses
  Amadeus multi-city, which is a single ticket through one carrier alliance.
  In practice for Italy↔Alaska that often *is* the cheaper option, but if
  you want to compare two-PNR stitching, that's a v2.
- It doesn't handle baggage fees, seat selection costs, etc. — prices are
  base fares as Amadeus returns them.

## Cost / API budget

Full default grid is heavier than I first quoted you. Per run:

```
origins (4) × outbound dates (5) × return dates (5) × routing variants
  = 4 × 5 × 5 × (1 direct/dest + open-jaw + 1 stopover)
  ≈ 4 × 25 × 5 = ~500 Amadeus calls per run
```

- **Amadeus Self-Service** free quota is ~2,000 calls/month. The default
  workflow runs once daily, so a full grid = ~15,000/month → you'll hit
  pay-as-you-go (check current Amadeus pricing — it's per-call but small).
- To stay within free tier:
  - Drop `date_flex_days` from 2 to 1 → ~180 calls/run.
  - Or trim `origins` to the 2 you actually fly from → ~250 calls/run.
  - Or set the workflow cron to weekly.
- **GitHub Actions**: free for public repos, 2000 min/mo for private.
- **Telegram bot**: free.

Recommendation: start with `date_flex_days: 1` and just MXP + FCO until you
confirm the pipeline works end-to-end, then widen.
