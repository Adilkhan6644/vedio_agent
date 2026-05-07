from __future__ import annotations

import argparse

from app.config import get_settings
from app.services.oauth_service import OAuthService



def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-time YouTube OAuth setup")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    settings = get_settings()
    oauth = OAuthService(
        client_secret_file=settings.youtube_client_secret_file,
        token_file=settings.youtube_token_file,
    )
    creds = oauth.run_interactive_oauth_setup(open_browser=not args.no_browser)

    print("OAuth setup completed.")
    print(f"Scopes: {creds.scopes}")
    print(f"Token file: {settings.youtube_token_file}")


if __name__ == "__main__":
    main()
