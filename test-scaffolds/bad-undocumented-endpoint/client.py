"""Scaffold that calls an undocumented Webex REST API endpoint.

This should pass Tier 1 (REST URL detected) but get a warning from
Tier 2 because /v1/secret-internal-api is not in the ecosystem catalog.
"""

import os

import requests


def call_undocumented_api():
    """Call an endpoint that doesn't exist in the Webex API catalog."""
    token = os.environ.get("WEBEX_ACCESS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}

    # This endpoint is not documented in the Postman collection
    response = requests.get(
        "https://webexapis.com/v1/secret-internal-api",
        headers=headers,
    )
    return response.json()


def main():
    result = call_undocumented_api()
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
