# Fire Alert Test (CAL FIRE)

This project checks the public CAL FIRE incident feed and sends Microsoft Teams alerts with fire details, including latitude/longitude, for selected counties.

Current monitored region in the script:
- California statewide

No paid API is required.

## What this script does

- Pulls active incidents from CAL FIRE public GeoJSON
- Filters to monitored counties
- Extracts coordinates from each incident
- Sends a Microsoft Teams message
- In normal mode, avoids duplicate alerts using `seen_fires.json`

## Step-by-step setup (for a new person)

### 1) Clone the repo

```bash
git clone <your-repo-url>
cd SDFireCoordinateProject
```

### 2) Create and activate a virtual environment (recommended)

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Create a local `.env` file

Copy the template:

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
TEAMS_WEBHOOK_URL=https://example.webhook.office.com/webhookb2/...
```

Notes:
- `TEAMS_WEBHOOK_URL` should be a Microsoft Teams incoming webhook URL for the channel where alerts should appear.
- Keep the webhook URL private. Anyone with the URL may be able to post to that channel.

### 5) Send one test Teams message now

```bash
python3 fire_check.py --test-teams
```

This sends one Teams message immediately and confirms:
- CAL FIRE feed access
- Teams webhook delivery

### 6) Run normal alert mode

```bash
python3 fire_check.py
```

This mode alerts only on new incidents (deduplicated by `seen_fires.json`).

## Run automatically with GitHub Actions

This repo includes a GitHub Actions workflow that checks CAL FIRE every 5 minutes.

To enable it:

1. Go to your GitHub repo.
2. Open **Settings** > **Secrets and variables** > **Actions**.
3. Click **New repository secret**.
4. Name it `TEAMS_WEBHOOK_URL`.
5. Paste your Microsoft Teams webhook URL as the secret value.
6. Open the **Actions** tab.
7. Select **Fire Alert Check**.
8. Click **Run workflow** once to test it.

The workflow runs `python fire_check.py`, posts new alerts to Teams, and commits `seen_fires.json` back to the repo so the next scheduled run does not send duplicates.

GitHub schedules can be delayed, so "every 5 minutes" may not be exact to the second.

## Change where alerts go

Update `TEAMS_WEBHOOK_URL` in `.env`, then run:

```bash
python3 fire_check.py --test-teams
```

## Change monitored region

Edit `TARGET_COUNTY_SUBSTRINGS` in `fire_check.py`.

To monitor all active California incidents:

```python
TARGET_COUNTY_SUBSTRINGS = ()
```

To monitor specific counties:

Example:

```python
TARGET_COUNTY_SUBSTRINGS = ("san diego", "los angeles", "orange")
```

Use lowercase county substrings.

## Troubleshooting

- **No Teams message received**
  - Confirm `.env` exists (not just `.env.example`)
  - Verify `TEAMS_WEBHOOK_URL` is copied exactly
  - Confirm the Teams channel allows incoming webhook messages
- **0 county matches in Teams**
  - This can be normal if CAL FIRE currently has no active incidents in monitored counties

## Security

- Never commit `.env`
- `.env` is ignored by `.gitignore`
- Keep `.env.example` as placeholders only
- Treat your Teams webhook URL like a password
