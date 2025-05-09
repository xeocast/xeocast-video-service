import boto3
import json
import logging
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.models.settings import settings

logger = logging.getLogger(__name__)

class R2Service:
    def __init__(self):
        self.s3_client = None
        if settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_ENDPOINT_URL:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    endpoint_url=settings.R2_ENDPOINT_URL,
                    region_name='auto' # R2 typically uses 'auto'
                )
                logger.info("R2 client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize R2 client: {e}")
        else:
            logger.warning("R2 client settings not fully configured. R2Service will not be functional.")

    def fetch_json_file(self, bucket_name: str, file_key: str) -> dict:
        if not self.s3_client:
            logger.error("R2 client not initialized. Cannot fetch file.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 service not configured."
            )
        try:
            response = self.s3_client.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')
            return json.loads(file_content)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.error(f"File not found in R2: {bucket_name}/{file_key}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Client secret file '{file_key}' not found."
                )
            logger.error(f"Error fetching file from R2 {bucket_name}/{file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not fetch client secret file from R2: {e.response['Error']['Message']}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from R2 file {file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Client secret file is not valid JSON."
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching or parsing R2 file {file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while retrieving the client secret."
            )

r2_service = R2Service() 