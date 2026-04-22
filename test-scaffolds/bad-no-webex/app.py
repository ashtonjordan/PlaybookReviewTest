"""Fake scaffold — claims to be a Webex integration but just opens a browser.

This should trigger the 'ecosystem-no-webex-integration' error because
there are no SDK imports, no REST API URLs, no widget manifests, and no
BYOVA patterns. The developer.webex.com URL is informational, not an API.
"""

import webbrowser


def main():
    """Open the Webex developer documentation in a browser."""
    print("Welcome to our Webex integration!")
    print("Opening Webex developer docs...")
    webbrowser.open("https://developer.webex.com/docs")
    print("Please follow the instructions on the website.")


if __name__ == "__main__":
    main()
