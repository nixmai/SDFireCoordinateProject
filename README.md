# Fire Alert Test (CAL FIRE)

This project checks the public CAL FIRE incident feed and emails fire details (including latitude/longitude) for selected counties.

Current monitored counties in the script:
- San Diego
- Los Angeles
- Orange

No paid API is required.

## What this script does

- Pulls active incidents from CAL FIRE public GeoJSON
- Filters to monitored counties
- Extracts coordinates from each incident
- Sends an email alert
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
FROM_EMAIL=your_gmail@gmail.com
FROM_PASSWORD=your_16_char_gmail_app_password
TO_EMAIL=any_email_you_want_to_receive_alerts_at
```

Notes:
- `FROM_PASSWORD` must be a Gmail **App Password** (not your normal Gmail password)
- Create one here: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- `TO_EMAIL` can be any destination inbox (same as sender or different)

### 5) Send one test email now

```bash
python3 fire_check.py --test-email
```

This sends one email immediately and confirms:
- CAL FIRE feed access
- Email credentials
- Delivery to your chosen inbox

### 6) Run normal alert mode

```bash
python3 fire_check.py
```

This mode alerts only on new incidents (deduplicated by `seen_fires.json`).

## Change who receives alerts

Update `TO_EMAIL` in `.env`, then run:

```bash
python3 fire_check.py --test-email
```

## Change monitored counties

Edit `TARGET_COUNTY_SUBSTRINGS` in `fire_check.py`.

Example:

```python
TARGET_COUNTY_SUBSTRINGS = ("san diego", "los angeles", "orange")
```

Use lowercase county substrings.

## Troubleshooting

- **No email received**
  - Check spam/promotions folders
  - Confirm `.env` exists (not just `.env.example`)
  - Verify Gmail App Password is correct
- **Authentication error**
  - Recreate Gmail App Password and update `.env`
- **0 county matches in email**
  - This can be normal if CAL FIRE currently has no active incidents in monitored counties

## Security

- Never commit `.env`
- `.env` is ignored by `.gitignore`
- Keep `.env.example` as placeholders only