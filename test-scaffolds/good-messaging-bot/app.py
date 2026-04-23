"""Webex Messaging Bot — listens for messages and responds.

This scaffold demonstrates proper Webex SDK usage with the webexteamssdk
Python package. It should pass all ecosystem validation checks.
"""

import os

from webexteamssdk import WebexTeamsAPI


def create_bot():
    """Initialize the Webex bot with an access token from the environment."""
    access_token = os.environ.get("WEBEX_BOT_TOKEN")
    if not access_token:
        raise RuntimeError("WEBEX_BOT_TOKEN environment variable is required")

    api = WebexTeamsAPI(access_token=access_token)
    return api


def send_greeting(api, room_id: str) -> None:
    """Send a greeting message to a Webex room."""
    api.messages.create(roomId=room_id, text="Hello from the Playbook bot!")


def list_rooms(api):
    """List all rooms the bot is a member of."""
    rooms = api.rooms.list()
    for room in rooms:
        print(f"Room: {room.title} (ID: {room.id})")


def main():
    api = create_bot()
    bot_info = api.people.me()
    print(f"Bot started: {bot_info.displayName} ({bot_info.emails[0]})")

    rooms = list(api.rooms.list(max=5))
    if rooms:
        send_greeting(api, rooms[0].id)
        print(f"Sent greeting to: {rooms[0].title}")


if __name__ == "__main__":
    main()
