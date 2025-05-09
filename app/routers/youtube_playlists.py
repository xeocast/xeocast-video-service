import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Body, Path as FastAPIPath, Query

from app.models.api_models import ErrorResponse
from app.models.youtube_playlist_models import (
    PlaylistCreateRequest,
    PlaylistUpdateRequest,
    PlaylistResponse,
    ListPlaylistsResponse
)
from app.services.youtube_playlist_service import youtube_playlist_service, YouTubePlaylistService
# Placeholder for API Key dependency, if you have one globally defined
# from app.dependencies import get_api_key # Assuming you have an API key dependency

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/youtube/playlists",
    tags=["YouTube Playlists"],
    # dependencies=[Depends(get_api_key)], # Uncomment if API key auth is needed for these routes
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        401: {"model": ErrorResponse, "description": "Unauthorized - Credentials missing, invalid, or expired"},
        403: {"model": ErrorResponse, "description": "Forbidden - Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Not Found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

# Helper function to get the service dependency
def get_playlist_service() -> YouTubePlaylistService:
    return youtube_playlist_service

@router.post(
    "/", 
    response_model=PlaylistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a YouTube Playlist",
    description="Creates a new playlist for the authenticated YouTube channel."
)
async def create_playlist(
    payload: PlaylistCreateRequest = Body(...),
    service: YouTubePlaylistService = Depends(get_playlist_service)
):
    """
    Create a new YouTube playlist.

    - **youtube_channel_id**: Your YouTube channel ID (used to retrieve stored OAuth tokens).
    - **title**: The title of the playlist.
    - **description**: Optional description for the playlist.
    - **privacy_status**: `private`, `public`, or `unlisted`.
    """
    try:
        playlist = await service.create_playlist(payload)
        return playlist
    except HTTPException as e:
        raise e # Re-raise HTTPException from the service layer
    except Exception as e:
        logger.error(f"Error in create_playlist endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/", 
    response_model=ListPlaylistsResponse,
    summary="List YouTube Playlists for a Channel",
    description="Retrieves a list of playlists for the authenticated YouTube channel."
)
async def list_playlists(
    youtube_channel_id: str = Query(..., description="The YouTube channel ID for which to list playlists."),
    page_token: Optional[str] = Query(None, description="Token for the next page of results."),
    max_results: int = Query(25, ge=1, le=50, description="Maximum number of results to return."),
    service: YouTubePlaylistService = Depends(get_playlist_service)
):
    """
    List playlists for the specified YouTube channel.

    - **youtube_channel_id**: The YouTube channel ID associated with the OAuth credentials.
    - **page_token**: Optional. Token for fetching a specific page of results.
    - **max_results**: Optional. Number of playlists to retrieve (1-50).
    """
    try:
        playlists = await service.list_playlists(youtube_channel_id, page_token, max_results)
        return playlists
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in list_playlists endpoint for channel {youtube_channel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{playlist_id}", 
    response_model=PlaylistResponse,
    summary="Get a Specific YouTube Playlist",
    description="Retrieves details for a specific playlist by its ID."
)
async def get_playlist(
    youtube_channel_id: str = Query(..., description="The YouTube channel ID to authenticate the request."),
    playlist_id: str = FastAPIPath(..., description="The ID of the YouTube playlist to retrieve."),
    service: YouTubePlaylistService = Depends(get_playlist_service)
):
    """
    Get a specific YouTube playlist by its ID.

    - **youtube_channel_id**: Your YouTube channel ID (used to retrieve stored OAuth tokens).
    - **playlist_id**: The ID of the playlist to retrieve.
    """
    try:
        playlist = await service.get_playlist(youtube_channel_id, playlist_id)
        if not playlist:
            # This case should ideally be handled by the service raising HTTPException(404)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
        return playlist
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in get_playlist endpoint for ID {playlist_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{playlist_id}", 
    response_model=PlaylistResponse,
    summary="Update a YouTube Playlist",
    description="Updates details of an existing YouTube playlist."
)
async def update_playlist(
    playlist_id: str = FastAPIPath(..., description="The ID of the YouTube playlist to update."),
    payload: PlaylistUpdateRequest = Body(...),
    service: YouTubePlaylistService = Depends(get_playlist_service)
):
    """
    Update an existing YouTube playlist. At least one field (title, description, or privacy_status) must be provided for an update.

    - **playlist_id**: The ID of the playlist to update.
    - **youtube_channel_id**: Your YouTube channel ID (required in the request body).
    - **title**: Optional. New title for the playlist.
    - **description**: Optional. New description for the playlist.
    - **privacy_status**: Optional. New privacy status (`private`, `public`, or `unlisted`).
    """
    if payload.title is None and payload.description is None and payload.privacy_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="At least one field (title, description, or privacy_status) must be provided for an update."
        )
    try:
        updated_playlist = await service.update_playlist(playlist_id, payload)
        return updated_playlist
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in update_playlist endpoint for ID {playlist_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{playlist_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a YouTube Playlist",
    description="Deletes a specific playlist by its ID."
)
async def delete_playlist(
    youtube_channel_id: str = Query(..., description="The YouTube channel ID to authenticate the request."),
    playlist_id: str = FastAPIPath(..., description="The ID of the YouTube playlist to delete."),
    service: YouTubePlaylistService = Depends(get_playlist_service)
):
    """
    Delete a YouTube playlist.
    
    - **youtube_channel_id**: Your YouTube channel ID (used to retrieve stored OAuth tokens).
    - **playlist_id**: The ID of the playlist to delete.
    """
    try:
        await service.delete_playlist(youtube_channel_id, playlist_id)
        return # Returns 204 No Content on success
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in delete_playlist endpoint for ID {playlist_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) 