import logging
from typing import Optional, Tuple

from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from fastapi import HTTPException, status

from app.models.settings import settings
from app.services.youtube_oauth_service import youtube_oauth_service # Assuming singleton instance
from app.models.youtube_playlist_models import (
    PlaylistCreateRequest,
    PlaylistUpdateRequest,
    PlaylistResponse,
    ListPlaylistsResponse,
)

logger = logging.getLogger(__name__)

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

class YouTubePlaylistService:
    def _get_youtube_service(self, youtube_channel_id: str) -> Resource:
        credentials = youtube_oauth_service.load_credentials(youtube_channel_id)
        if not credentials:
            logger.warning(f"No credentials found for YouTube channel ID: {youtube_channel_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication required. No credentials found for channel {youtube_channel_id}. Please authenticate first."
            )
        if credentials.expired and credentials.refresh_token:
            try:
                # The google-auth library handles the transport for refresh internally.
                # We might need to ensure httpx is installed if it's the default transport, or google-auth-httplib2.
                # For now, assume credentials.refresh() works with a default Request object if needed by the lib.
                from google.auth.transport.requests import Request as GoogleAuthRequest
                credentials.refresh(GoogleAuthRequest())
                youtube_oauth_service.save_credentials(youtube_channel_id, credentials) # Save refreshed credentials
                logger.info(f"Refreshed YouTube credentials for channel {youtube_channel_id}")
            except Exception as e:
                logger.error(f"Failed to refresh YouTube token for channel {youtube_channel_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token refresh failed for channel {youtube_channel_id}. Please re-authenticate. Error: {str(e)}"
                )
        
        try:
            service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)
            return service
        except HttpError as e:
            logger.error(f"HttpError building YouTube service for channel {youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            detail = f"Failed to build YouTube service: {e._get_reason()}"
            if e.resp.status == 401 or e.resp.status == 403:
                detail += " This may be due to expired or revoked credentials, or insufficient permissions. Please re-authenticate."
            raise HTTPException(status_code=e.resp.status, detail=detail)
        except Exception as e:
            logger.error(f"Unexpected error building YouTube service for channel {youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error initializing YouTube service: {str(e)}")

    def _format_playlist_response(self, yt_playlist: dict) -> PlaylistResponse:
        return PlaylistResponse(
            id=yt_playlist["id"],
            title=yt_playlist.get("snippet", {}).get("title", "N/A"),
            description=yt_playlist.get("snippet", {}).get("description"),
            privacy_status=yt_playlist.get("status", {}).get("privacyStatus", "unknown"),
            channel_id=yt_playlist.get("snippet", {}).get("channelId", "N/A"),
            item_count=yt_playlist.get("contentDetails", {}).get("itemCount"),
            published_at=yt_playlist.get("snippet", {}).get("publishedAt")
        )

    async def create_playlist(self, playlist_data: PlaylistCreateRequest) -> PlaylistResponse:
        service = self._get_youtube_service(playlist_data.youtube_channel_id)
        try:
            body = {
                "snippet": {
                    "title": playlist_data.title,
                    "description": playlist_data.description or "",
                    # "tags": [], # Optional: add if needed
                    # "defaultLanguage": "en" # Optional: add if needed
                },
                "status": {
                    "privacyStatus": playlist_data.privacy_status
                }
            }
            request = service.playlists().insert(
                part="snippet,status",
                body=body
            )
            response = request.execute()
            logger.info(f"Successfully created playlist '{response['id']}' for channel {playlist_data.youtube_channel_id}")
            return self._format_playlist_response(response)
        except HttpError as e:
            logger.error(f"HttpError creating playlist for channel {playlist_data.youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            raise HTTPException(status_code=e.resp.status, detail=f"YouTube API error: {e._get_reason()}")
        except Exception as e:
            logger.error(f"Error creating playlist for channel {playlist_data.youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create playlist: {str(e)}")

    async def get_playlist(self, youtube_channel_id: str, playlist_id: str) -> Optional[PlaylistResponse]:
        service = self._get_youtube_service(youtube_channel_id)
        try:
            request = service.playlists().list(
                part="snippet,status,contentDetails", # contentDetails for itemCount
                id=playlist_id,
                maxResults=1 # Expecting only one result for a specific ID
            )
            response = request.execute()
            if response.get("items"):
                playlist_item = response["items"][0]
                # Verify channel ownership before returning, though API should enforce this for non-public playlists.
                # For public playlists, anyone can fetch if they know the ID.
                # if playlist_item.get("snippet", {}).get("channelId") != youtube_channel_id:
                #     logger.warning(f"Playlist {playlist_id} does not belong to channel {youtube_channel_id}")
                #     # This check is tricky because a user might have access to view a playlist from another channel if it's public or shared.
                #     # The auth itself should restrict operations, but for reads, it's different.
                #     # For now, we assume the ID provided is intended for this user or is public.
                return self._format_playlist_response(playlist_item)
            else:
                logger.info(f"Playlist with ID '{playlist_id}' not found for channel {youtube_channel_id}.")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playlist with ID '{playlist_id}' not found.")
        except HttpError as e:
            logger.error(f"HttpError fetching playlist {playlist_id} for channel {youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            if e.resp.status == 404:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playlist '{playlist_id}' not found or access denied.")
            raise HTTPException(status_code=e.resp.status, detail=f"YouTube API error: {e._get_reason()}")
        except Exception as e:
            logger.error(f"Error fetching playlist {playlist_id} for channel {youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch playlist: {str(e)}")

    async def list_playlists(self, youtube_channel_id: str, page_token: Optional[str] = None, max_results: int = 25) -> ListPlaylistsResponse:
        service = self._get_youtube_service(youtube_channel_id)
        try:
            request = service.playlists().list(
                part="snippet,status,contentDetails",
                mine=True, # Fetches playlists owned by the authenticated user
                maxResults=min(max_results, 50), # API max is 50
                pageToken=page_token
            )
            response = request.execute()
            
            items = [self._format_playlist_response(item) for item in response.get("items", [])]
            
            return ListPlaylistsResponse(
                items=items,
                next_page_token=response.get("nextPageToken"),
                prev_page_token=response.get("prevPageToken"), # Note: prevPageToken is not always provided by YouTube API
                page_info=response.get("pageInfo")
            )
        except HttpError as e:
            logger.error(f"HttpError listing playlists for channel {youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            raise HTTPException(status_code=e.resp.status, detail=f"YouTube API error: {e._get_reason()}")
        except Exception as e:
            logger.error(f"Error listing playlists for channel {youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list playlists: {str(e)}")

    async def update_playlist(self, playlist_id: str, playlist_data: PlaylistUpdateRequest) -> PlaylistResponse:
        service = self._get_youtube_service(playlist_data.youtube_channel_id)
        try:
            # First, fetch the existing playlist to get its current snippet and status
            # This is necessary because the update API replaces the entire snippet or status object.
            # We must provide all fields for snippet and status that should be preserved.
            get_request = service.playlists().list(
                part="snippet,status", 
                id=playlist_id,
                maxResults=1
            )
            get_response = get_request.execute()
            if not get_response.get("items"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playlist with ID '{playlist_id}' not found.")
            
            current_playlist = get_response["items"][0]
            current_snippet = current_playlist.get("snippet", {})
            current_status = current_playlist.get("status", {})

            # Construct the update body
            body_snippet = {
                "title": playlist_data.title if playlist_data.title is not None else current_snippet.get("title"),
                "description": playlist_data.description if playlist_data.description is not None else current_snippet.get("description"),
                # Ensure other snippet fields like defaultLanguage, tags (if managed) are preserved
                # For simplicity, we are only managing title and description here.
                # If you need to manage more, ensure they are read and re-set.
                # "defaultLanguage": current_snippet.get("defaultLanguage"), 
                # "tags": current_snippet.get("tags", [])
            }
            if playlist_data.title is None and playlist_data.description is None and playlist_data.privacy_status is None:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update parameters provided. Please provide title, description, or privacy_status to update.")

            body_status = None
            if playlist_data.privacy_status:
                body_status = {"privacyStatus": playlist_data.privacy_status}
            
            update_payload = {"id": playlist_id}
            parts_to_update = []

            if playlist_data.title is not None or playlist_data.description is not None:
                update_payload["snippet"] = body_snippet
                parts_to_update.append("snippet")
            
            if body_status:
                update_payload["status"] = body_status
                parts_to_update.append("status")
            
            if not parts_to_update:
                 # This case should be caught by the check above, but as a safeguard:
                 logger.info(f"No fields to update for playlist {playlist_id}")
                 return self._format_playlist_response(current_playlist) # Return current state

            request = service.playlists().update(
                part=",".join(parts_to_update),
                body=update_payload
            )
            response = request.execute()
            logger.info(f"Successfully updated playlist '{response['id']}' for channel {playlist_data.youtube_channel_id}")
            return self._format_playlist_response(response)
        except HttpError as e:
            logger.error(f"HttpError updating playlist {playlist_id} for channel {playlist_data.youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            if e.resp.status == 404:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playlist '{playlist_id}' not found or you do not have permission to update it.")
            raise HTTPException(status_code=e.resp.status, detail=f"YouTube API error: {e._get_reason()}")
        except Exception as e:
            logger.error(f"Error updating playlist {playlist_id} for channel {playlist_data.youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update playlist: {str(e)}")

    async def delete_playlist(self, youtube_channel_id: str, playlist_id: str) -> None:
        service = self._get_youtube_service(youtube_channel_id)
        try:
            request = service.playlists().delete(id=playlist_id)
            request.execute() # Returns None on success (HTTP 204)
            logger.info(f"Successfully deleted playlist '{playlist_id}' for channel {youtube_channel_id}")
            return
        except HttpError as e:
            logger.error(f"HttpError deleting playlist {playlist_id} for channel {youtube_channel_id}: {e.resp.status} {e._get_reason()}")
            if e.resp.status == 404:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playlist '{playlist_id}' not found or you do not have permission to delete it.")
            raise HTTPException(status_code=e.resp.status, detail=f"YouTube API error: {e._get_reason()}")
        except Exception as e:
            logger.error(f"Error deleting playlist {playlist_id} for channel {youtube_channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete playlist: {str(e)}")

# Singleton instance of the service
youtube_playlist_service = YouTubePlaylistService() 