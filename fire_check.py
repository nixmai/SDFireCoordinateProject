import argparse
import os
import json
import smtplib
import requests
from pathlib import Path
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

CALFIRE_URL = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/GeoJsonList?inactive=false"
SEEN_FILE = Path("seen_fires.json")

FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_PASSWORD = os.getenv("FROM_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

# Lowercase substrings matched against County / Counties fields from CAL FIRE.
TARGET_COUNTY_SUBSTRINGS = ("san diego", "los angeles", "orange")


def county_in_target_regions(county_text: str) -> bool:
    return any(s in county_text for s in TARGET_COUNTY_SUBSTRINGS)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FireAlertBot/1.0)",
    "Accept": "application/json",
}


def load_seen_fires():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_fires(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)


def send_email(subject, body):
    """Send alert email. Falls back to console print if .env is not configured."""
    if not FROM_EMAIL or not FROM_PASSWORD or not TO_EMAIL:
        print("\n" + "="*50)
        print("EMAIL NOT CONFIGURED — printing alert to console:")
        print("="*50)
        print(f"SUBJECT: {subject}")
        print(body)
        print("="*50 + "\n")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(FROM_EMAIL, FROM_PASSWORD)
            server.send_message(msg)
        print(f"Email sent to {TO_EMAIL}")
    except smtplib.SMTPAuthenticationError:
        print("\nERROR: Gmail login failed.")
        print("FROM_PASSWORD must be a Gmail App Password, not your regular password.")
        print("Generate one at: https://myaccount.google.com/apppasswords\n")
    except Exception as e:
        print(f"ERROR: Could not send email: {e}")


def get_fire_id(props, name, latitude, longitude):
    return (
        props.get("UniqueId")
        or props.get("Id")
        or props.get("IncidentId")
        or f"{name}-{latitude}-{longitude}"
    )


def get_county_text(props):
    fields = [props.get("County"), props.get("Counties"), props.get("CountiesList")]
    return " ".join(str(x) for x in fields if x).lower()


def fetch_incidents():
    print("Fetching CAL FIRE data...")
    response = requests.get(CALFIRE_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def collect_region_fires(data):
    """Return list of dicts for active, non-final incidents in target counties (with coordinates)."""
    out = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        county_text = get_county_text(props)
        if not county_in_target_regions(county_text):
            continue
        if props.get("Final") is True:
            continue
        coordinates = geometry.get("coordinates")
        if not coordinates or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        name = props.get("Name", "Unknown Fire")
        out.append(
            {
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "county_text": county_text,
                "acres": props.get("Acres", "Unknown"),
                "containment": props.get("PercentContained", "Unknown"),
                "started": props.get("Started", "Unknown"),
                "updated": props.get("Updated", "Unknown"),
                "admin_unit": props.get("AdminUnit", "Unknown"),
            }
        )
    return out


def format_fire_lines(fires):
    if not fires:
        return (
            "No active San Diego, Los Angeles, or Orange County incidents in the CAL FIRE feed right now.\n"
            "(The test still confirms your email + API access work.)\n"
        )
    lines = []
    for f in fires:
        maps_link = f"https://www.google.com/maps?q={f['latitude']},{f['longitude']}"
        lines.append(
            f"- {f['name']}\n"
            f"  County: {f['county_text'].title()}\n"
            f"  Latitude: {f['latitude']}, Longitude: {f['longitude']}\n"
            f"  Acres: {f['acres']}, Containment: {f['containment']}%\n"
            f"  Maps: {maps_link}\n"
        )
    return "\n".join(lines)


def send_test_email():
    """Send a single email to verify SMTP and show current SD / LA / OC incidents (if any)."""
    if not (FROM_EMAIL and FROM_PASSWORD and TO_EMAIL):
        print(
            "\nNo email was sent — Gmail settings are not loaded.\n"
            "  • In this project folder, create a file named `.env` (copy from `.env.example`).\n"
            "  • Set FROM_EMAIL, FROM_PASSWORD, and TO_EMAIL.\n"
            "  • FROM_PASSWORD must be a Gmail App Password (16 characters), not your normal password:\n"
            "    https://myaccount.google.com/apppasswords\n"
            "  • Save `.env`, then run: python fire_check.py --test-email\n"
        )
        return

    try:
        data = fetch_incidents()
    except requests.RequestException as e:
        print(f"ERROR: Could not reach CAL FIRE API: {e}")
        return

    total = len(data.get("features", []))
    fires = collect_region_fires(data)
    body = f"""This is a one-time test from your San Diego / Los Angeles / Orange County fire alert script.

CAL FIRE active incidents (all CA): {total}
San Diego + Los Angeles + Orange County matches (active, not final, with coordinates): {len(fires)}

{format_fire_lines(fires)}
---
Source: CAL FIRE public GeoJSON API (no API key, free)
"""
    subject = "[TEST] SD / LA / OC fire alert — email check"
    print(f"Sending test email (SD+LA+OC incidents in feed: {len(fires)})...")
    send_email(subject, body)


def check_fires():
    seen = load_seen_fires()

    try:
        data = fetch_incidents()
    except requests.RequestException as e:
        print(f"ERROR: Could not reach CAL FIRE API: {e}")
        return

    features = data.get("features", [])
    print(f"Total active CA incidents: {len(features)}")

    new_fires = 0

    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        name = props.get("Name", "Unknown Fire")
        county_text = get_county_text(props)

        if not county_in_target_regions(county_text):
            continue

        if props.get("Final") is True:
            continue

        coordinates = geometry.get("coordinates")
        if not coordinates or len(coordinates) < 2:
            print(f"  WARNING: No coordinates for '{name}', skipping.")
            continue

        # GeoJSON order is [longitude, latitude]
        longitude = coordinates[0]
        latitude = coordinates[1]

        fire_id = get_fire_id(props, name, latitude, longitude)

        if fire_id in seen:
            print(f"  Already alerted on '{name}', skipping.")
            continue

        acres = props.get("Acres", "Unknown")
        containment = props.get("PercentContained", "Unknown")
        started = props.get("Started", "Unknown")
        updated = props.get("Updated", "Unknown")
        admin_unit = props.get("AdminUnit", "Unknown")
        maps_link = f"https://www.google.com/maps?q={latitude},{longitude}"

        county_label = county_text.title()
        subject = f"Fire Alert: {name} — {county_label}"
        body = f"""New active fire detected in monitored counties (San Diego, Los Angeles, Orange).

Fire Name:   {name}
Latitude:    {latitude}
Longitude:   {longitude}
County:      {county_text.title()}
Acres:       {acres}
Containment: {containment}%
Started:     {started}
Updated:     {updated}
Admin Unit:  {admin_unit}

Google Maps: {maps_link}

Source: CAL FIRE public incident API
"""
        print(f"  NEW FIRE: {name} at ({latitude}, {longitude})")
        send_email(subject, body)
        seen.add(fire_id)
        new_fires += 1

    save_seen_fires(seen)

    if new_fires == 0:
        print("No new San Diego / Los Angeles / Orange fires found.")
    else:
        print(f"Done. Sent {new_fires} alert(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="San Diego + Los Angeles + Orange County fire alerts from CAL FIRE public API"
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="Send one email to verify SMTP + API (no deduplication, no schedule)",
    )
    args = parser.parse_args()
    if args.test_email:
        send_test_email()
    else:
        check_fires()