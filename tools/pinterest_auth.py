"""
Pinterest OAuth 2.0 Authentication
Handles initial auth flow and token refresh.
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "pins:read,pins:write,boards:read,boards:write,user_accounts:read"
AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle the OAuth callback from Pinterest."""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentifizierung erfolgreich!</h2>"
                b"<p>Du kannst dieses Fenster schliessen.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = params.get("error", ["unknown"])[0]
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs


def start_oauth_flow():
    """Start the full OAuth flow: open browser, wait for callback, exchange code."""
    app_id = os.getenv("PINTEREST_APP_ID")
    app_secret = os.getenv("PINTEREST_APP_SECRET")

    if not app_id or not app_secret:
        print("[ERROR] PINTEREST_APP_ID and PINTEREST_APP_SECRET must be set in .env")
        print("\nSetup steps:")
        print("1. Go to https://developers.pinterest.com/")
        print("2. Create an app")
        print("3. Add redirect URI: http://localhost:8080/callback")
        print("4. Copy App ID and App Secret to .env")
        sys.exit(1)

    # Build authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": "snabbacash",
    })
    auth_url = f"{AUTH_URL}?{auth_params}"

    print("Opening browser for Pinterest authorization...")
    print(f"If the browser doesn't open, visit:\n{auth_url}\n")

    # Start local server to catch callback
    server = http.server.HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()

    # Open browser
    webbrowser.open(auth_url)

    # Wait for callback
    print("Waiting for authorization...")
    server_thread.join(timeout=120)
    server.server_close()

    if not OAuthCallbackHandler.auth_code:
        print("[ERROR] No authorization code received (timeout or user denied)")
        sys.exit(1)

    print("Authorization code received! Exchanging for tokens...")

    # Exchange code for tokens
    token_data = {
        "grant_type": "authorization_code",
        "code": OAuthCallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
    }

    resp = requests.post(
        TOKEN_URL,
        data=token_data,
        auth=(app_id, app_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code != 200:
        print(f"[ERROR] Token exchange failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    tokens = resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")

    # Save tokens to .env
    set_key(str(ENV_PATH), "PINTEREST_ACCESS_TOKEN", access_token)
    set_key(str(ENV_PATH), "PINTEREST_REFRESH_TOKEN", refresh_token)

    print("Tokens saved to .env!")
    print(f"Access token expires in: {tokens.get('expires_in', 'unknown')} seconds")

    return access_token


def refresh_access_token():
    """Refresh the access token using the refresh token."""
    app_id = os.getenv("PINTEREST_APP_ID")
    app_secret = os.getenv("PINTEREST_APP_SECRET")
    refresh_token = os.getenv("PINTEREST_REFRESH_TOKEN")

    if not refresh_token:
        print("[WARN] No refresh token available — starting fresh OAuth flow")
        return start_oauth_flow()

    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    resp = requests.post(
        TOKEN_URL,
        data=token_data,
        auth=(app_id, app_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code != 200:
        print(f"[WARN] Token refresh failed ({resp.status_code}) — starting fresh OAuth flow")
        return start_oauth_flow()

    tokens = resp.json()
    access_token = tokens["access_token"]
    new_refresh = tokens.get("refresh_token", refresh_token)

    set_key(str(ENV_PATH), "PINTEREST_ACCESS_TOKEN", access_token)
    set_key(str(ENV_PATH), "PINTEREST_REFRESH_TOKEN", new_refresh)

    print("Access token refreshed successfully!")
    return access_token


def get_valid_token():
    """Get a valid Pinterest access token. Refreshes or re-authenticates if needed."""
    load_dotenv(ENV_PATH, override=True)  # Reload in case tokens were updated
    token = os.getenv("PINTEREST_ACCESS_TOKEN")

    if not token:
        print("No access token found — starting OAuth flow...")
        return start_oauth_flow()

    # Test the token
    resp = requests.get(
        "https://api.pinterest.com/v5/user_account",
        headers={"Authorization": f"Bearer {token}"},
    )

    if resp.status_code == 200:
        user = resp.json()
        print(f"Authenticated as: {user.get('username', 'unknown')}")
        return token
    elif resp.status_code == 401:
        print("Access token expired — refreshing...")
        return refresh_access_token()
    else:
        print(f"[WARN] Unexpected status {resp.status_code} — refreshing token...")
        return refresh_access_token()


if __name__ == "__main__":
    token = get_valid_token()
    if token:
        print(f"\nToken ready (first 10 chars): {token[:10]}...")
