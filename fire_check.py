import argparse
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CALFIRE_URL = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/GeoJsonList?inactive=false"
SEEN_FILE = Path("seen_fires.json")

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

# Lowercase substrings matched against County / Counties fields from CAL FIRE.
# Use an empty tuple to monitor all active California incidents.
TARGET_COUNTY_SUBSTRINGS = ()


def monitored_region_label():
    if not TARGET_COUNTY_SUBSTRINGS:
        return "California"
    return " / ".join(s.title() for s in TARGET_COUNTY_SUBSTRINGS)


def county_in_target_regions(county_text: str) -> bool:
    if not TARGET_COUNTY_SUBSTRINGS:
        return True
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


def send_teams_message(subject, body):
    """Send an alert to Microsoft Teams. Falls back to console print if not configured."""
    if not TEAMS_WEBHOOK_URL:
        print("\n" + "="*50)
        print("TEAMS WEBHOOK NOT CONFIGURED - printing alert to console:")
        print("="*50)
        print(f"SUBJECT: {subject}")
        print(body)
        print("="*50 + "\n")
        return False

    try:
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.2",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": subject,
                                "weight": "Bolder",
                                "size": "Medium",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": body,
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }
        response = requests.post(
            TEAMS_WEBHOOK_URL,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        print("Teams message sent.")
        return True
    except requests.RequestException as e:
        print(f"ERROR: Could not send Teams message: {e}")
        return False


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
            f"No active {monitored_region_label()} incidents in the CAL FIRE feed right now.\n"
            "(The test still confirms your Teams webhook + API access work.)\n"
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


def send_test_teams_message():
    """Send a single Teams message to verify the webhook and show current monitored incidents."""
    if not TEAMS_WEBHOOK_URL:
        print(
            "\nNo Teams message was sent - TEAMS_WEBHOOK_URL is not loaded.\n"
            "  • In this project folder, create a file named `.env` (copy from `.env.example`).\n"
            "  • Set TEAMS_WEBHOOK_URL to your Microsoft Teams incoming webhook URL.\n"
            "  • Save `.env`, then run: python fire_check.py --test-teams\n"
        )
        return

    try:
        data = fetch_incidents()
    except requests.RequestException as e:
        print(f"ERROR: Could not reach CAL FIRE API: {e}")
        return

    total = len(data.get("features", []))
    fires = collect_region_fires(data)
    region_label = monitored_region_label()
    body = f"""This is a one-time test from your {region_label} fire alert script.

CAL FIRE active incidents (all CA): {total}
{region_label} matches (active, not final, with coordinates): {len(fires)}

{format_fire_lines(fires)}
---
Source: CAL FIRE public GeoJSON API (no API key, free)
"""
    subject = f"[TEST] {region_label} fire alert - Teams check"
    print(f"Sending test Teams message ({region_label} incidents in feed: {len(fires)})...")
    send_teams_message(subject, body)


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
        subject = f"Fire Alert: {name} - {county_label}"
        body = f"""New active fire detected in monitored region ({monitored_region_label()}).

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
        if send_teams_message(subject, body):
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
        "--test-teams",
        action="store_true",
        help="Send one Teams message to verify webhook + API (no deduplication, no schedule)",
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.test_teams or args.test_email:
        send_test_teams_message()
    else:
        check_fires()
