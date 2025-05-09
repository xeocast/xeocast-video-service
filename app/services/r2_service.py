import boto3
import json
import logging
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from pathlib import Path

from app.models.settings import settings

logger = logging.getLogger(__name__)

class R2Service:
    def __init__(self):
        self.s3_ro_client = None
        self.s3_rw_client = None
        self.r2_endpoint_url = settings.R2_ENDPOINT_URL

        if not self.r2_endpoint_url:
            logger.warning("R2_ENDPOINT_URL not configured. R2Service will not be functional.")
            return

        # Initialize Read-Only Client
        if settings.R2_RO_ACCESS_KEY_ID and settings.R2_RO_SECRET_ACCESS_KEY:
            try:
                self.s3_ro_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.R2_RO_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_RO_SECRET_ACCESS_KEY,
                    endpoint_url=self.r2_endpoint_url,
                    region_name='auto'
                )
                logger.info("R2 Read-Only client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize R2 Read-Only client: {e}")
        else:
            logger.warning("R2 Read-Only client settings not fully configured.")

        # Initialize Read-Write Client
        if settings.R2_RW_ACCESS_KEY_ID and settings.R2_RW_SECRET_ACCESS_KEY:
            try:
                self.s3_rw_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.R2_RW_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_RW_SECRET_ACCESS_KEY,
                    endpoint_url=self.r2_endpoint_url,
                    region_name='auto'
                )
                logger.info("R2 Read-Write client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize R2 Read-Write client: {e}")
        else:
            logger.warning("R2 Read-Write client settings not fully configured.")

    def fetch_json_file(self, bucket_name: str, file_key: str) -> dict:
        if not self.s3_ro_client:
            logger.error("R2 Read-Only client not initialized. Cannot fetch JSON file.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 Read-Only service not configured."
            )
        try:
            response = self.s3_ro_client.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')
            return json.loads(file_content)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.error(f"File not found in R2: {bucket_name}/{file_key}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File '{file_key}' not found in bucket '{bucket_name}'."
                )
            logger.error(f"Error fetching file from R2 {bucket_name}/{file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not fetch file from R2: {e.response['Error']['Message']}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from R2 file {file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File '{file_key}' is not valid JSON."
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching or parsing R2 file {file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while retrieving the file."
            )

    def download_file_from_source_bucket(self, file_key: str, destination_path: Path) -> Path:
        if not self.s3_ro_client:
            logger.error("R2 Read-Only client not initialized. Cannot download source file.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 Read-Only service not configured."
            )
        bucket_name = settings.R2_VIDEO_SOURCE_BUCKET
        try:
            self.s3_ro_client.download_file(bucket_name, file_key, str(destination_path))
            logger.info(f"Successfully downloaded {file_key} from {bucket_name} to {destination_path}")
            return destination_path
        except ClientError as e:
            if e.response['Error']['Code'] == '404': # Note: S3/R2 might return 404 for NoSuchKey on download_file
                logger.error(f"File not found in R2 source bucket: {bucket_name}/{file_key}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Source file '{file_key}' not found in bucket '{bucket_name}'."
                )
            logger.error(f"Error downloading file from R2 source bucket {bucket_name}/{file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not download source file from R2: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error downloading R2 source file {file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while downloading the source file."
            )

    def download_file(self, bucket_name: str, file_key: str, destination_path: Path) -> Path:
        if not self.s3_ro_client:
            logger.error("R2 Read-Only client not initialized. Cannot download file.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 Read-Only service not configured."
            )
        try:
            self.s3_ro_client.download_file(bucket_name, file_key, str(destination_path))
            logger.info(f"Successfully downloaded {file_key} from {bucket_name} to {destination_path}")
            return destination_path
        except ClientError as e:
            # Check if the error is because the file was not found
            if e.response['Error']['Code'] == '404' or 'NoSuchKey' in str(e):
                logger.error(f"File not found in R2 bucket: {bucket_name}/{file_key}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File '{file_key}' not found in bucket '{bucket_name}'."
                )
            logger.error(f"Error downloading file from R2 bucket {bucket_name}/{file_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not download file from R2: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error downloading R2 file {file_key} from {bucket_name}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while downloading the file."
            )

    def upload_file_to_output_bucket(self, file_path: Path, object_key: str) -> str:
        if not self.s3_rw_client:
            logger.error("R2 Read-Write client not initialized. Cannot upload output file.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 Read-Write service not configured."
            )
        bucket_name = settings.R2_VIDEO_OUTPUT_BUCKET
        try:
            self.s3_rw_client.upload_file(str(file_path), bucket_name, object_key)
            logger.info(f"Successfully uploaded {file_path} to {bucket_name}/{object_key}")
            # Return the object key, presigned URL will be generated separately
            return object_key 
        except ClientError as e:
            logger.error(f"Error uploading file to R2 output bucket {bucket_name}/{object_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not upload output file to R2: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error uploading R2 output file {object_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while uploading the output file."
            )

    def generate_presigned_url_for_output_bucket(self, object_key: str, expiration: int = 3600) -> str:
        if not self.s3_ro_client: # Can use RO client if bucket policy allows GetObject for presigned URLs
                                  # Or use s3_rw_client if preferred for consistency with output bucket operations
            logger.error("R2 client for presigned URL not initialized.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="R2 service not configured for generating presigned URLs."
            )
        bucket_name = settings.R2_VIDEO_OUTPUT_BUCKET
        try:
            # Using s3_ro_client, assuming it has GetObject permission on the output bucket,
            # which is typical for generating read URLs. 
            # If write client (s3_rw_client) is preferred or strictly needed by permissions, switch here.
            client_to_use = self.s3_ro_client 
            # Alternatively, if you want to ensure the client associated with RW operations on this bucket generates the URL:
            # client_to_use = self.s3_rw_client 
            # if not client_to_use:
            #     logger.error("Appropriate R2 client for presigned URL (output bucket) not initialized.")
            #     raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="R2 client issue.")

            response = client_to_use.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_key},
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned URL for {bucket_name}/{object_key}")
            return response
        except ClientError as e:
            logger.error(f"Error generating presigned URL for R2 {bucket_name}/{object_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not generate presigned URL for R2 object: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL for {object_key}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while generating the presigned URL."
            )

r2_service = R2Service() 