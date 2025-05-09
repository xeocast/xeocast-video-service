import logging
import json
from pathlib import Path
from typing import Tuple, Optional

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from fastapi import HTTPException, status

from app.models.settings import settings
from app.services.r2_service import r2_service

logger = logging.getLogger(__name__)

STATE_SEPARATOR = "|::|" # unlikely to be in channel_id or filename

class YouTubeOAuthService:
    def _get_client_config(self, client_secret_filename: str) -> dict:
        try:
            client_config = r2_service.fetch_json_file(
                bucket_name=settings.R2_CLIENT_SECRETS_BUCKET,
                file_key=client_secret_filename
            )
            # The flow typically expects a structure like {"web": {...}} or {"installed": {...}} or {"device": {...}}
            if not (client_config.get("web") or client_config.get("installed") or client_config.get("device") ):
                logger.error(f"Client secret file '{client_secret_filename}' has invalid format.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Client secret file format is invalid."
                )
            return client_config
        except HTTPException:
            raise # Re-raise HTTPException from r2_service
        except Exception as e:
            logger.error(f"Unexpected error processing client secret file '{client_secret_filename}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not process client secret file."
            )

    def generate_auth_url(self, youtube_channel_id: str) -> str:
        client_secret_filename = f"{youtube_channel_id}.json"
        client_config = self._get_client_config(client_secret_filename)
        try:
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=settings.YOUTUBE_SCOPES,
                redirect_uri=settings.YOUTUBE_REDIRECT_URI
            )
            # Create a state that includes both channel_id and client_secret_filename
            state_payload = f"{youtube_channel_id}{STATE_SEPARATOR}{client_secret_filename}"
            authorization_url, _ = flow.authorization_url(
                access_type='offline', # Request refresh token
                prompt='consent',      # Ensure user sees consent screen
                state=state_payload
            )
            logger.info(f"Generated auth URL for channel {youtube_channel_id}")
            return authorization_url
        except GoogleAuthError as e:
            logger.error(f"Google Auth error during auth URL generation for {youtube_channel_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Google Auth error: {e}")
        except Exception as e:
            logger.error(f"Error generating auth URL for {youtube_channel_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate authorization URL.")

    def exchange_code_for_token(self, auth_code: str, state: str) -> Tuple[str, str]:
        try:
            youtube_channel_id, client_secret_filename = self.parse_state(state)
            if not youtube_channel_id or not client_secret_filename:
                raise ValueError("Invalid state received")
        except ValueError as e:
            logger.error(f"Invalid state received in OAuth callback: {state}. Error: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid state: {e}")

        client_config = self._get_client_config(client_secret_filename)
        try:
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=settings.YOUTUBE_SCOPES,
                redirect_uri=settings.YOUTUBE_REDIRECT_URI
            )
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            self.save_credentials(youtube_channel_id, credentials)
            logger.info(f"Successfully fetched and saved token for channel {youtube_channel_id}")
            return youtube_channel_id, client_secret_filename # For logging or confirmation
        except GoogleAuthError as e:
            logger.error(f"Google Auth error during token exchange for {youtube_channel_id}: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google Auth error: {e}")
        except Exception as e:
            logger.error(f"Error exchanging code for token for {youtube_channel_id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not exchange code for token.")

    def save_credentials(self, youtube_channel_id: str, credentials: Credentials):
        if not settings.TMP_AUTH_DIR.exists():
            settings.TMP_AUTH_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created temporary auth directory: {settings.TMP_AUTH_DIR}")
        
        file_path = settings.TMP_AUTH_DIR / f"{youtube_channel_id}.json"
        try:
            with open(file_path, 'w') as token_file:
                token_file.write(credentials.to_json())
            logger.info(f"Saved credentials for channel {youtube_channel_id} to {file_path}")
        except IOError as e:
            logger.error(f"Error saving credentials for {youtube_channel_id} to {file_path}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save credentials.")

    def parse_state(self, state: str) -> Tuple[Optional[str], Optional[str]]:
        parts = state.split(STATE_SEPARATOR)
        if len(parts) == 2:
            return parts[0], parts[1]
        logger.warning(f"Could not parse state: {state}")
        return None, None

    def load_credentials(self, youtube_channel_id: str) -> Optional[Credentials]:
        file_path = settings.TMP_AUTH_DIR / f"{youtube_channel_id}.json"
        if file_path.exists():
            try:
                return Credentials.from_authorized_user_file(str(file_path), settings.YOUTUBE_SCOPES)
            except Exception as e:
                logger.error(f"Error loading credentials for {youtube_channel_id} from {file_path}: {e}")
                return None
        return None

youtube_oauth_service = YouTubeOAuthService() 