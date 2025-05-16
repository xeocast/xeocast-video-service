# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install system dependencies required by OpenCV and other libraries
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    # Add any other system dependencies your project might need
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the requirements file into the container at /app
COPY requirements.txt requirements.txt

# 4. Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
# Using --default-timeout to prevent timeouts on slow networks, adjust if needed
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Create a non-root user and group
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

# 5. Copy the rest of the application's code into the container at /app
# Ensure /app exists and set ownership before copying files if needed, though WORKDIR should create it.
# If specific ownership is needed for /app itself before copying, add RUN mkdir -p /app && chown appuser:appuser /app
# COPY . . will copy files owned by root. We'll chown after.
# If you have a specific app directory (e.g., ./app), you might want to copy that specifically:
# COPY ./app /app/app
# COPY ./models /app/models
# COPY ./views /app/views
# COPY ./controllers /app/controllers
# For now, let's assume your app is in the root or organized within subdirectories that can be copied all at once.
COPY . .

# Create directories for volumes if they weren't copied from the source context,
# ensuring they exist before the main chown operation.
# These paths correspond to named volumes: /app/tmp-auth
RUN mkdir -p /app/tmp-auth

# Change ownership of the entire /app directory and all its contents (including the dirs above) to the non-root user
RUN chown -R appuser:appuser /app

# 6. Make port 8000 available to the world outside this container
# This is informational; the actual port mapping is done in docker-compose.yml
EXPOSE 8000

# 7. Define the command to run your app using uvicorn
# Replace `app.main:app` with the actual path to your FastAPI app instance
# For example, if your main file is src/main.py and app instance is `my_api`, it would be `src.main:my_api`
# Using --host 0.0.0.0 to make it accessible from outside the container (e.g., by cloudflared service)
# The --port will be 8000 as exposed.
# Add --reload for development if you want uvicorn to auto-reload on code changes (not recommended for production images)
# Switch to the non-root user
USER appuser

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# Based on your project structure (MVC), it's likely your main app is in a subdirectory like 'app' or 'src'.
# Assuming your FastAPI app instance is named `app` in a file named `main.py` inside an `app` directory (i.e., `app/main.py`)
# If your main.py is in the root of your project (copied to /app/main.py), the command should be main:app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 