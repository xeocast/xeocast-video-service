# XeoCast Video Service

This API service provides functionality to generate and publish a video file taking as input a background image file and an audio file, or publish a video file from a pre-existing video file. It operates asynchronously using a task-based system.

## Features

- Generate video from image and audio URLs.
- Publish existing video URL (primarily for YouTube upload).
- Asynchronous task processing with callback notifications.
- In-memory task storage.
- Signed URLs for accessing generated videos.
- Scheduled cleanup of old video files.
- API Key authentication.
- YouTube integration (placeholder).

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
- **YouTube Integration:** Basic YouTube upload functionality using an API key is implemented (as specified in the design). However, video uploads typically require OAuth 2.0 for authentication. If you encounter issues, you may need to adapt the service (`app/services/youtube_service.py`) to use an OAuth 2.0 flow. The required libraries are included in `requirements.txt`.
- **In-Memory Storage:** Task data is lost if the server restarts.
- **Signed URL Base URL:** The base URL for signed URLs is now configurable via the `BASE_URL` environment variable (or the default in `app/models/settings.py`). Ensure this is set correctly to the public-facing URL of your service in your deployment environment (e.g., in the `.env` file or system environment variables).
- **Signed URL Base URL:** The base URL used for signing static file URLs in `app/utils/background_tasks.py` (`