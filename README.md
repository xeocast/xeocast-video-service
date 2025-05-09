# XeoCast Video Service

This API service provides functionality to generate and publish a video file taking as input a background image file and an audio file, or publish a video file from a pre-existing video file. It operates asynchronously using a task-based system.

## Features

This service provides a comprehensive suite of features for video manipulation and publishing:

-   **Video Generation & Publishing:**
    -   Generate videos by combining a background image URL and an audio URL.
    -   Publish pre-existing video URLs (e.g., for direct upload to other platforms or further processing).
-   **Asynchronous Task Management:**
    -   All video operations (generation, publishing) are processed as background tasks, ensuring the API remains responsive.
    -   An immediate task ID is returned upon request submission, allowing clients to track progress.
    -   The status of any task can be queried via a dedicated API endpoint.
    -   Upon task completion (whether success or error), the service sends a POST request with the results to a user-provided callback URL.
-   **Security & Access Control:**
    -   Mandatory API Key authentication (via the `X-API-Key` header) is enforced for all service endpoints to protect your resources.
    -   Generated video files are made accessible via a public static web server component.
    -   Access to these static video files is secured using signed URLs, which include a cryptographic signature and a configurable expiration time.
-   **YouTube Integration:**
    -   Seamlessly upload generated or pre-existing videos directly to specified YouTube channels using OAuth 2.0.
    -   (Future or advanced usage might include endpoints for managing YouTube videos and playlists, such as listing content for authenticated channels).
-   **Service Operations & Configuration:**
    -   Utilizes in-memory storage for task data. **Note:** Task history and details are volatile and will be lost if the server restarts.
    -   Includes an automated cleanup mechanism that periodically removes old generated video files from the static directory to manage storage space.
    -   Provides a standard health check endpoint (e.g., `/health`) for monitoring the operational status of the service.
    -   Offers a developer utility: a test callback endpoint (e.g., `/test-callback`) designed to help users verify and debug their callback integration.
    -   Service behavior is primarily configured through environment variables, with support for a `.env` file for ease of setup (see "Configure Environment Variables" section).

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd xeocast-video-service
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: MoviePy might have system dependencies (like ImageMagick or ffmpeg). Ensure ffmpeg is installed and accessible in your system's PATH.* 
    *Note: YouTube upload requires `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` which are included in `requirements.txt`.* 

4.  **Configure Environment Variables (Optional):**
    Create a `.env` file in the project root directory to override default settings:
    ```dotenv
    # Example .env file
    API_KEY="your_secret_api_key"
    SIGNATURE_SECRET_KEY="a_very_strong_secret_for_signing_urls"
    BASE_URL="http://your_public_server_address:port" # IMPORTANT: Set this to the public URL of the service
    # STATIC_DIR="custom_static"
    # SIGNATURE_EXPIRATION_SECONDS=3600 # 1 hour
    # CLEANUP_INTERVAL_HOURS=2
    # MAX_VIDEO_AGE_HOURS=72
    # HOST="127.0.0.1"
    # PORT=8080
    # LOG_LEVEL="debug"
    ```
    If `.env` is not present, default values in `app/models/settings.py` will be used.

## Running the Service

Use Uvicorn to run the FastAPI application:

```bash
python main.py
```

Alternatively, run directly with uvicorn for more options:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- `--host 0.0.0.0`: Makes the server accessible on your network.
- `--port 8000`: Specifies the port.
- `--reload`: Enables auto-reloading for development (server restarts on code changes).

Once running, the API documentation (Swagger UI) will be available at `http://<host>:<port>/docs` (e.g., `http://localhost:8000/docs`).

## API Usage

Refer to the API documentation (`/docs`) for detailed endpoint information, request/response formats, and authentication (`X-API-Key` header).

## Important Notes

- **MoviePy Dependencies:** Ensure `ffmpeg` is installed and accessible.
-   **YouTube Integration & OAuth 2.0 Setup:**
    -   The service is equipped to upload videos to YouTube. Modern YouTube API practices, especially for actions performed on behalf of a channel (like video uploads), mandate the use of OAuth 2.0 for authentication.
    -   All necessary Python libraries for implementing an OAuth 2.0 flow with Google services (`google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`) are included in the `requirements.txt` file.
    -   **To enable YouTube uploads for a specific channel, you must perform the following OAuth 2.0 setup:**
        1.  Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
        2.  Ensure you have a project with the YouTube Data API v3 enabled.
        3.  Create OAuth 2.0 credentials. For server-side applications like this service, you'd typically download a `client_secret.json` file. (Often, "Desktop app" or "Web application" credential types are used; ensure the redirect URIs are correctly configured if applicable to your specific OAuth flow setup within the service, although for client secrets file usage, the flow might facilitate offline access).
        4.  This downloaded `client_secret.json` file must be securely stored. This service expects it to be uploaded to a Cloudflare R2 bucket.
        5.  The target R2 bucket for these secrets is specified by the environment variable `R2_CLIENT_SECRETS_BUCKET_PROD` for your production environment, or `R2_CLIENT_SECRETS_BUCKET_DEV` for development. You can find the default bucket names (e.g., "video-service-files") or set your own in your `.env` file or by checking `app/models/settings.py`.
        6.  Within the designated R2 bucket, the `client_secret.json` file **must be named according to the YouTube Channel ID** it authorizes, using the format: `YOUR_YOUTUBE_CHANNEL_ID.json`. For instance, if a channel's ID is `UCuzL5QP8z5FONc4AMd1hIsQ`, the corresponding secrets file in R2 should be named `UCuzL5QP8z5FONc4AMd1hIsQ.json`.
    -   The video service (specifically modules like `app/services/youtube_service.py` and associated authentication handlers) will retrieve and use these stored `client_secret.json` files to obtain OAuth tokens and interact with the YouTube API on behalf of the authenticated channel.
    -   Ensure your Google Cloud project's OAuth consent screen is properly configured with the necessary scopes (e.g., `https://www.googleapis.com/auth/youtube.upload`). Depending on the scopes and application type, Google might require app verification.
- **In-Memory Storage:** Task data is lost if the server restarts.