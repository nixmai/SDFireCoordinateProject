# Fire Alert Test

Free test version using the **CAL FIRE public incident API** (no API key). Optional Gmail SMTP for alerts (also free with an [App Password](https://myaccount.google.com/apppasswords)).

## One-shot email test (no cron)

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `FROM_EMAIL`, `FROM_PASSWORD` (Gmail app password), `TO_EMAIL`.
3. Run:

```bash
python fire_check.py --test-email
```

You should get **one** email with either San Diego fire coordinates (if any are active) or a message that the feed has no SD incidents right now (still proves email + API work).

## Normal mode (only *new* fires, deduped)

```bash
python fire_check.py
```

Uses `seen_fires.json` so you are not re-alerted on the same incident.

## Setup

Install dependencies:

```bash
pip install -r requirements.txt