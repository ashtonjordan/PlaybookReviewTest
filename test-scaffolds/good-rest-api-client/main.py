"""Webex REST API Client — sends messages and manages rooms via REST.

This scaffold demonstrates direct REST API usage with the webexapis.com
endpoints. It should pass Tier 1 (REST URL detected) and Tier 2
(endpoints are documented in the catalog).
"""

import os

import requests


WEBEX_BASE_URL = "https://webexapis.com/v1"


def get_headers():
    """Build authorization headers from environment variable."""
    token = os.environ.get("WEBEX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("WEBEX_ACCESS_TOKEN environment variable is required")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def list_rooms():
    """List all rooms the authenticated user belongs to."""
    url = f"{WEBEX_BASE_URL}/rooms"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("items", [])


def send_message(room_id: str, text: str):
    """Send a text message to a Webex room."""
    url = f"{WEBEX_BASE_URL}/messages"
    payload = {"roomId": room_id, "text": text}
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def get_my_details():
    """Get the authenticated user's profile."""
    url = f"{WEBEX_BASE_URL}/people/me"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()


def main():
    me = get_my_details()
    print(f"Authenticated as: {me['displayName']}")

    rooms = list_rooms()
    print(f"Found {len(rooms)} rooms")

    if rooms:
        result = send_message(rooms[0]["id"], "Hello from the REST client!")
        print(f"Message sent: {result['id']}")


if __name__ == "__main__":
    main()
