import httpx
import logging
from typing import Optional

from pydantic import BaseModel
from app.models.api_models import TaskStatus

logger = logging.getLogger(__name__)

class CallbackService:
    async def send_callback(self, url: str, payload: BaseModel):
        """Sends a POST request with the payload to the specified callback URL."""
        try:
            async with httpx.AsyncClient() as client:
                # Use mode='json' to ensure HttpUrl and other Pydantic types are serialized to strings
                request_body = payload.model_dump(mode='json', by_alias=True)
                logger.info(f"Sending callback request body: {request_body}")
                response = await client.post(url, json=request_body, timeout=30.0) # Use by_alias for taskId
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