import argparse
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.storage.blob import BlobServiceClient
except ImportError:
    ResourceNotFoundError = None
    BlobServiceClient = None

load_dotenv()

CALFIRE_URL = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/GeoJsonList?inactive=false"
SEEN_FILE = Path("seen_fires.json")
SEEN_BLOB_CONTAINER = os.getenv("SEEN_FIRES_CONTAINER", "fire-alert-state")
SEEN_BLOB_NAME = os.getenv("SEEN_FIRES_BLOB", "seen_fires.json")

POWER_AUTOMATE_WEBHOOK_URL = os.getenv("POWER_AUTOMATE_WEBHOOK_URL")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")


def _parse_county_substrings() -> tuple[str, ...]:
    """Counties from MONITOR_COUNTIES (.env), comma-separated, lowercase substrings."""
    raw = os.getenv("MONITOR_COUNTIES", "san diego").strip()
    if not raw:
        return ()
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


# Lowercase substrings matched against County / Counties fields from CAL FIRE.
# Empty tuple = all active California incidents. Override via MONITOR_COUNTIES in .env.
TARGET_COUNTY_SUBSTRINGS = _parse_county_substrings()


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


def get_seen_storage_connection_string():
    connection_string = (
        os.getenv("SEEN_FIRES_STORAGE_CONNECTION_STRING")
        or os.getenv("AzureWebJobsStorage")
    )
    if not connection_string or connection_string == "UseDevelopmentStorage=true":
        return None
    return connection_string


def get_seen_blob_client():
    connection_string = get_seen_storage_connection_string()
    if not connection_string or BlobServiceClient is None:
        return None
    service = BlobServiceClient.from_connection_string(connection_string)
    container = service.get_container_client(SEEN_BLOB_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    return container.get_blob_client(SEEN_BLOB_NAME)


def load_seen_fires():
    blob = get_seen_blob_client()
    if blob:
        try:
            return set(json.loads(blob.download_blob().readall()))
        except ResourceNotFoundError:
            return set()

    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_fires(seen):
    payload = json.dumps(sorted(seen), indent=2)
    blob = get_seen_blob_client()
    if blob:
        blob.upload_blob(payload, overwrite=True)
        return

    with open(SEEN_FILE, "w") as f:
        f.write(payload)


def build_teams_message_payload(subject, body):
    """
    JSON shape required by Teams 'webhook alerts' Power Automate flows and
    incoming webhooks: type message + adaptive card attachments array.
    """
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
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


def send_power_automate_alert(subject, body, **_fields):
    """POST Teams adaptive-card JSON to a Power Automate webhook trigger."""
    if not POWER_AUTOMATE_WEBHOOK_URL:
        return False

    payload = build_teams_message_payload(subject, body)
    try:
        response = requests.post(
            POWER_AUTOMATE_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        print("Power Automate alert sent.")
        return True
    except requests.RequestException as e:
        print(f"ERROR: Could not reach Power Automate: {e}")
        if getattr(e, "response", None) is not None:
            print(f"  Response: {e.response.text[:500]}")
        return False


def send_teams_message(subject, body):
    """Send an alert to Microsoft Teams incoming webhook."""
    if not TEAMS_WEBHOOK_URL:
        return False

    try:
        response = requests.post(
            TEAMS_WEBHOOK_URL,
            json=build_teams_message_payload(subject, body),
            timeout=20,
        )
        response.raise_for_status()
        print("Teams message sent.")
        return True
    except requests.RequestException as e:
        print(f"ERROR: Could not send Teams message: {e}")
        return False


def send_alert(subject, body, **_fields):
    """Send via Power Automate (preferred), then Teams, else print to console."""
    if send_power_automate_alert(subject, body):
        return True
    if send_teams_message(subject, body):
        return True

    print("\n" + "=" * 50)
    print("NO WEBHOOK CONFIGURED - printing alert to console:")
    print("=" * 50)
    print(f"SUBJECT: {subject}")
    print(body)
    print("=" * 50 + "\n")
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
            "(The test still confirms your webhook + API access work.)\n"
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


def send_test_alert():
    """Send one test alert to verify webhooks and show current monitored incidents."""
    if not POWER_AUTOMATE_WEBHOOK_URL and not TEAMS_WEBHOOK_URL:
        print(
            "\nNo alert was sent - no webhook URL in .env.\n"
            "  • Set POWER_AUTOMATE_WEBHOOK_URL (Power Automate HTTP trigger URL), or\n"
            "  • Set TEAMS_WEBHOOK_URL (Teams incoming webhook).\n"
            "  • Then run: python3 fire_check.py --test\n"
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
    subject = f"[TEST] {region_label} fire alert"
    print(f"Sending test alert ({region_label} incidents in feed: {len(fires)})...")
    send_alert(
        subject,
        body,
        alertType="test",
        region=region_label,
        incidentCount=len(fires),
        totalCaliforniaIncidents=total,
    )


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
        if send_alert(
            subject,
            body,
            alertType="fire",
            fireName=name,
            latitude=latitude,
            longitude=longitude,
            county=county_text.title(),
            acres=acres,
            containment=containment,
            started=started,
            updated=updated,
            adminUnit=admin_unit,
            mapsUrl=maps_link,
        ):
            seen.add(fire_id)
            new_fires += 1

    save_seen_fires(seen)

    region = monitored_region_label()
    if new_fires == 0:
        print(f"No new {region} fires found.")
    else:
        print(f"Done. Sent {new_fires} new {region} alert(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CAL FIRE incident alerts (GeoJSON API) with Power Automate / Teams notifications",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send one test alert to verify webhook + API (no deduplication)",
    )
    parser.add_argument(
        "--test-teams",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.test or args.test_teams:
        send_test_alert()
    else:
        check_fires()
