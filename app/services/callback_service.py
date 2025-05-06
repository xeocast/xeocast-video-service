import httpx
import logging
from typing import Optional

from app.models.api_models import CallbackPayload, TaskStatus

logger = logging.getLogger(__name__)

class CallbackService:
    async def send_callback(self, url: str, payload: CallbackPayload):
        """Sends a POST request with the payload to the specified callback URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={"data": payload.model_dump(by_alias=True)}, timeout=30.0) # Use by_alias for taskId
                response.raise_for_status() # Raise exception for non-2xx responses
                logger.info(f"Callback sent successfully to {url}. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Error sending callback to {url}: Request failed - {e}")
            # Optionally: Implement retry logic here
        except httpx.HTTPStatusError as e:
            logger.error(f"Error sending callback to {url}: Received status {e.response.status_code}")
            # Optionally: Implement retry logic here
        except Exception as e:
            logger.error(f"Unexpected error sending callback to {url}: {e}", exc_info=True)

# Singleton instance
callback_service = CallbackService() 