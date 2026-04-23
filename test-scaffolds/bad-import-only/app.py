"""Fake scaffold — imports Webex SDK but never actually uses it.

This should trigger the 'ecosystem-sdk-import-only' warning because
the SDK is imported but no methods are ever called.
"""

from webexteamssdk import WebexTeamsAPI

# The import above is never used — this is just placeholder code
print("This app does nothing with Webex")
x = 1 + 2
result = x * 3
print(f"Result: {result}")
