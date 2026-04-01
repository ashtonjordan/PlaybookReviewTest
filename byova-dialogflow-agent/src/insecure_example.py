"""Example connector with intentional security issues for testing CodeGuard rules."""

import os
import sqlite3
import pickle
import hashlib
import logging
import subprocess

# Hardcoded credentials (codeguard-1-hardcoded-credentials)
AWS_ACCESS_KEY = "my-aws-access-key-do-not-commit"
AWS_SECRET_KEY = "my-aws-secret-key-do-not-commit-this-value"
DATABASE_PASSWORD = "admin123"
API_TOKEN = "my-github-personal-access-token-here"
WEBEX_BOT_TOKEN = "my-webex-bot-token-value-here"

# HTTP instead of HTTPS (codeguard-0-api-web-services)
WEBEX_API_URL = "http://webexapis.com/v1/messages"
DIALOGFLOW_ENDPOINT = "http://dialogflow.googleapis.com/v2/projects"


class InsecureConnector:
    """A connector with multiple security anti-patterns."""

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        # Logging secrets (codeguard-0-logging)
        self.logger.info(f"Connecting with token: {API_TOKEN}")
        self.logger.info(f"Using password: {DATABASE_PASSWORD}")

    def query_database(self, user_input):
        """SQL injection vulnerability (codeguard-0-input-validation-injection)."""
        conn = sqlite3.connect("app.db")
        cursor = conn.cursor()
        # Direct string concatenation with user input
        query = f"SELECT * FROM users WHERE name = '{user_input}'"
        cursor.execute(query)
        return cursor.fetchall()

    def run_command(self, user_input):
        """OS command injection (codeguard-0-input-validation-injection)."""
        # Unsanitized user input in shell command
        result = subprocess.run(f"echo {user_input}", shell=True, capture_output=True)
        return result.stdout

    def hash_password(self, password):
        """Weak cryptography (codeguard-0-additional-cryptography)."""
        # MD5 is broken for password hashing
        return hashlib.md5(password.encode()).hexdigest()

    def load_user_data(self, data_bytes):
        """Unsafe deserialization (codeguard-0-xml-and-serialization)."""
        # pickle.loads on untrusted input is a remote code execution risk
        return pickle.loads(data_bytes)

    def send_webex_message(self, room_id, message):
        """HTTP transport instead of HTTPS (codeguard-0-api-web-services)."""
        import urllib.request

        url = f"http://webexapis.com/v1/messages"
        data = f'{{"roomId": "{room_id}", "text": "{message}"}}'.encode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", f"Bearer {WEBEX_BOT_TOKEN}")
        return urllib.request.urlopen(req)

    def process_file_upload(self, filename, content):
        """Path traversal vulnerability (codeguard-0-file-handling-and-uploads)."""
        # No validation on filename — allows ../../../etc/passwd
        with open(f"/uploads/{filename}", "wb") as f:
            f.write(content)

    def get_user_token(self):
        """Hardcoded JWT (codeguard-1-hardcoded-credentials)."""
        return "my-jwt-token-value-do-not-hardcode-this"

    def connect_to_db(self):
        """Hardcoded connection string with password."""
        conn_str = (
            "postgresql://admin:supersecretpassword@db.example.com:5432/production"
        )
        return sqlite3.connect(conn_str)
