# XeoCast Video Service API Design

## General Description

This API service provides functionality to generate and publish a video file taking as input a background image file and an audio file, or publish a video file from a pre-existing video file. It operates asynchronously using a task-based system. When a generate process is initiated, a task ID is returned immediately. The final results (or any errors) are delivered via a POST request to a user-provided callback URL once the task completes.

The project architecture follows the Model-View-Controller (MVC) pattern.

The tasks storage is just in memory.

The generated videos are shared in a public static web server protected by a signature.

The service should delete the background image and the audio file after the video is generated.

The service should delete the generated video 24 hours after the callback is sent, or videos older than 48 hours if the in memory tasks storage is flushed, for example during a restart.

## Authentication

Most endpoints require API key authentication. The key must be provided in the `X-API-Key` HTTP header.

The API key is an environment variable that is set in the deployment environment.

- **Required Header:** `X-API-Key: YOUR_API_KEY`

Endpoints Exempt from Authentication:
- `GET /health`
- `POST /test-callback`

## Endpoints

### Health Check

- **Endpoint:** `GET /health`
- **Description:** Checks the operational status of the API service. Useful for monitoring.
- **Authentication:** None required.
- **Input:** None.
- **Output (Success - 200 OK):**
  ```json
  {
    "status": "healthy"
  }
  ```

### Video Generation

- **Endpoint:** `POST /generate-video`
- **Description:** Initiates an asynchronous task to generate a video from a background image and an audio file.
- **Authentication:** Required (`X-API-Key` header).
- **Input (Query Parameters):**
  - `background_image_url` (string, required): The full URL of the background image file. Must be a valid URL.
  - `audio_file_url` (string, required): The full URL of the audio file. Must be a valid URL.
  - `callback_url` (string, required): The URL where the service will send a POST request with the results upon task completion. Must be a valid URL.
  - `youtube_api_key` (string, required): The API key for the YouTube API.
  - `youtube_video_title` (string, required): The title of the video.
  - `youtube_video_description` (string, required): The description of the video.
  - `youtube_video_tags` (string, required): The tags of the video.
  - `youtube_video_thumbnail_url` (string, required): The URL of the thumbnail of the video.
  - `youtube_video_playlist_id` (string, required): The ID of the playlist where the video will be added.

- **Output (Success - 202 Accepted):**
  ```json
  {
    "task_id": "<unique_task_identifier>",
    "status": "pending",
    "message": "Task created successfully. Results will be sent to the callback URL when ready."
  }
  ```
- **Output (Error):**
  - `400 Bad Request`: If `background_image_url` or `audio_file_url` or `callback_url` are missing or invalid.
  ```json
  {
    "error": "Valid URL is required"
  }
  ```
  or
  ```json
  {
    "error": "Valid callback_url is required"
  }
  ```
  - `500 Internal Server Error`: If the task could not be initiated.
  ```json
  {
    "error": "Failed to initiate task",
    "message": "<server_error_details>"
  }
  ```
- **Callback:**
  - **Method:** `POST`
  - **Target:** The `callback_url` provided in the initial request.
  - **Body (JSON):**
    ```json
    {
      "taskId": "<unique_task_identifier>",
      "status": "completed" | "error",
      "video_url": "<url_of_the_generated_video>" | null, // null if status is 'error'
      "video_signature": "<signature_of_the_generated_video>" | null, // null if status is 'error'
      "error": "<error_message>" | null // null if status is 'completed'
    }
    ```

If a `youtube_api_key` is not provided, the video will not be published to YouTube and the other YouTube related parameters are ignored.

### Video Publishing to YouTube via API

- **Endpoint:** `POST /publish-video`
- **Description:** Publishes a video to YouTube via API.
- **Authentication:** Required (`X-API-Key` header).
- **Input (Query Parameters):**
  - `video_url` (string, required): The full URL of the video file. Must be a valid URL.  
  - `callback_url` (string, required): The URL where the service will send a POST request with the results upon task completion. Must be a valid URL.
  - `youtube_api_key` (string, required): The API key for the YouTube API.
  - `youtube_video_title` (string, required): The title of the video.
  - `youtube_video_description` (string, required): The description of the video.
  - `youtube_video_tags` (string, required): The tags of the video.
  - `youtube_video_thumbnail_url` (string, required): The URL of the thumbnail of the video.
  - `youtube_video_playlist_id` (string, required): The ID of the playlist where the video will be added.
- **Output (Success - 202 Accepted):**
  ```json
  {
    "task_id": "<unique_task_identifier>",
    "status": "pending",
    "message": "Task created successfully. Results will be sent to the callback URL when ready."
  }
  ```
- **Output (Error):**
  - `400 Bad Request`: If `video_url` or `callback_url` or `youtube_api_key` are missing or invalid.
  ```json
  {
    "error": "Valid URL is required"
  }
  ```
  or
  ```json
  {
    "error": "Valid callback_url is required"
  }
  ```

### Task Management

#### Get All Tasks

- **Endpoint:** `GET /tasks`
- **Description:** Retrieves metadata for all tasks known to the service. Does not return full results or errors.
- **Authentication:** Required (`X-API-Key` header).
- **Input:** None.
- **Output (Success - 200 OK):** An array of task metadata objects.
  ```json
  [
    {
      "id": "<task_id_1>",
      "status": "completed", // "pending" | "processing" | "completed" | "error"
      "type": "generateVideo", // "generateVideo" | "publishVideo"
      "details": {
        "background_image_url": "https://example.com/background_image1",
        "audio_file_url": "https://example.com/audio_file1",
        "callback_url": "https://example.com/callback1",
      },
      "created_at": "2023-10-27T10:00:00.000Z", // ISO 8601 Timestamp
      "updated_at": "2023-10-27T10:05:00.000Z" // ISO 8601 Timestamp
    },
    {
      "id": "<task_id_2>",
      "status": "pending",
      "type": "publishVideo",
      "details": {
        "video_url": "https://example.com/video1",
      },
      "created_at": "2023-10-27T11:00:00.000Z",
      "updated_at": "2023-10-27T11:00:00.000Z"
    }
    // ... other tasks
  ]
  ```

#### Get Task Status

- **Endpoint:** `GET /tasks/:id`
- **Description:** Retrieves metadata for a specific task using its unique ID. Does not return full results or errors.
- **Authentication:** Required (`X-API-Key` header).
- **Input (Path Parameter):**
  - `id` (string, required): The unique identifier of the task.
- **Output (Success - 200 OK):** Task metadata object.
  ```json
  {
    "id": "<task_id>",
    "status": "processing", // "pending" | "processing" | "completed" | "error"
    "type": "generateVideo", // "generateVideo" | "publishVideo"
    "details": {
      "background_image_url": "https://example.com/background_image1",
      "audio_file_url": "https://example.com/audio_file1",
      "callback_url": "https://example.com/callback1",
    },
    "created_at": "2023-10-27T12:00:00.000Z",
    "updated_at": "2023-10-27T12:02:00.000Z"
  }
  ```
- **Output (Error):**
  - `400 Bad Request`: If the `id` path parameter is missing (though route structure usually prevents this).
  - `404 Not Found`: If no task exists with the provided `id`.
  ```json
  {
    "error": "Task not found"
  }
  ```

### Test Callback Endpoint

- **Endpoint:** `POST /test-callback`
- **Description:** A utility endpoint primarily for development and testing. It accepts any JSON payload via a POST request and logs the received data to the server console. It can be used to manually test callback handling or inspect the structure of payloads sent by the service.
- **Authentication:** None required.
- **Input (Body):** Any valid JSON payload. Typically used with payloads mimicking the actual task callbacks.
- **Output (Success - 200 OK):**
  ```json
  {
    "received": true
  }
  ```
- **Output (Error - 500 Internal Server Error):** If there's an issue processing the request body.
  ```json
  {
    "received": false,
    "error": "<error_message>"
  }
  ```
