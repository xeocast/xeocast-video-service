# FastAPI Service

This is a basic FastAPI service.

## Installation

First, create and activate a virtual environment:

```bash
# On macOS and Linux
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
.\\venv\\Scripts\\activate
```

Then, install the dependencies:

```bash
pip install -r requirements.txt
```

## Running the Service

```bash
uvicorn main:app --reload
```

The service will be available at http://127.0.0.1:8000.

To deactivate the virtual environment, run:

```bash
deactivate
```

## Endpoints

- `/`: Returns a welcome message.
- `/health`: Returns the health status (`{"status": "ok"}`).
- `/echo` (POST): Echoes back the message provided in the JSON request body (e.g., `{"message": "hello"}` results in `{"echo": "hello"}`).
