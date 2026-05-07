from __future__ import annotations

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class OAuthService:
    def __init__(self, client_secret_file: Path, token_file: Path):
        self.client_secret_file = client_secret_file
        self.token_file = token_file

    def get_credentials(self) -> Credentials:
        creds: Credentials | None = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), [YOUTUBE_UPLOAD_SCOPE])

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._save_token(creds)
            else:
                raise RuntimeError(
                    "No valid OAuth token found. Run: python -m app.utils.oauth_setup"
                )

        return creds

    def run_interactive_oauth_setup(self, open_browser: bool = True) -> Credentials:
        if not self.client_secret_file.exists():
            raise FileNotFoundError(
                f"Google OAuth client secrets missing: {self.client_secret_file}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secret_file),
            scopes=[YOUTUBE_UPLOAD_SCOPE],
        )

        creds = flow.run_local_server(port=0, open_browser=open_browser)
        self._save_token(creds)
        return creds

    def _save_token(self, creds: Credentials) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        token_payload = json.loads(creds.to_json())
        with open(self.token_file, "w", encoding="utf-8") as file_obj:
            json.dump(token_payload, file_obj, indent=2)
