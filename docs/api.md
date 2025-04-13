# Pixeletica API Documentation

This document provides comprehensive documentation for the Pixeletica API, which allows you to convert images to Minecraft block art programmatically.

## Getting Started

### Installation

#### Standard Installation

1. Clone the repository:

    ```bash
    git clone <repository_url>
    cd pixeletica
    ```

2. Create a virtual environment:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    venv\Scripts\activate.bat  # On Windows
    ```

3. Install the dependencies:

    ```bash
    pip install -e .
    ```

#### Docker Installation

1. Install Docker and Docker Compose.

2. Clone the repository:

    ```bash
    git clone <repository_url>
    cd pixeletica
    ```

3. Build and start the containers:

    ```bash
    docker-compose up --build
    ```

### Starting the API Server

To start the API server, use the following command:

```bash
python -m pixeletica --mode api
```

Additional options:

- `--host` - Host to bind the server to (default: 0.0.0.0)
- `--port` - Port to bind the server to (default: 8000)
- `--log-level` - Logging level (debug, info, warning, error, critical)

Example:

```bash
python -m pixeletica --mode api --host 127.0.0.1 --port 9000 --log-level debug
```

### API Documentation

Once the server is running, the API documentation is available at:

- OpenAPI UI: `http://localhost:8000/docs`
- Root endpoint: `http://localhost:8000/`

## API Endpoints

The API provides the following main endpoints:

### Start a Conversion Task

**Endpoint**: `POST /api/conversion/start`

Starts a new image conversion task. This is an asynchronous operation: the API immediately returns a task ID, and the image processing takes place in the background.

**Request Body**:

```json
{
  "image": "base64-encoded-image-data",
  "filename": "example.png",
  "width": 100,
  "height": 80,
  "algorithm": "floyd_steinberg",
  "exportSettings": {
    "exportTypes": ["png"],
    "originX": 0,
    "originY": 0,
    "originZ": 0,
    "drawChunkLines": true,
    "chunkLineColor": "#FF0000",
    "drawBlockLines": true,
    "blockLineColor": "#000000",
    "splitCount": 1
  },
  "schematicSettings": {
    "generateSchematic": true,
    "author": "API User",
    "name": "My Schematic",
    "description": "Generated via API"
  }
}
```

Parameters:

- `image`: (required) Base64-encoded image data
- `filename`: (required) Original filename with extension
- `width`: (optional) Target width in pixels (maintaining aspect ratio if only one dimension provided)
- `height`: (optional) Target height in pixels
- `algorithm`: (optional) Dithering algorithm to use: "floyd_steinberg" (default), "ordered", or "random"
- `exportSettings`: (optional) Output file settings
- `schematicSettings`: (optional) Schematic generation settings

**Response**:

```json
{
  "taskId": "uuid-task-identifier",
  "status": "queued",
  "progress": 0,
  "timestamp": "2025-04-11T14:20:00Z"
}
```

### Get Quick Preview

**Endpoint**: `GET /api/conversion/preview`

Generates a quick preview of a converted image with specified dimensions and dithering algorithm. This endpoint creates a blank image of the specified size, applies the selected dithering algorithm, and returns the resulting image directly. The endpoint has a built-in timeout mechanism to prevent large images from consuming excessive resources.

**Query Parameters**:

- `width`: (required) Width of the preview image in pixels
- `height`: (required) Height of the preview image in pixels
- `algorithm`: (optional) Dithering algorithm to use: "floyd_steinberg" (default), "ordered", or "random"

**Response**: The converted image as a PNG file.

**Error Responses**:

- `400 Bad Request`: If the dimensions are too large or invalid
- `408 Request Timeout`: If the conversion process exceeds the timeout limit (large images)

**Example**:

```http
GET /api/conversion/preview?width=100&height=80&algorithm=floyd_steinberg
```

This will return a PNG image with the specified dimensions and dithering algorithm applied.

### Check Conversion Status

**Endpoint**: `GET /api/conversion/{taskId}`

Check the status of a conversion task.

**Response**:

```json
{
  "taskId": "uuid-task-identifier",
  "status": "processing|completed|failed",
  "progress": 75,
  "timestamp": "2025-04-11T14:20:00Z",
  "error": "Error message if failed"
}
```

Status values:

- `queued`: Task is waiting to be processed
- `processing`: Task is currently being processed
- `completed`: Task has been successfully completed
- `failed`: Task failed (error details provided)

### List Available Files

**Endpoint**: `GET /api/conversion/{taskId}/files`

Get a list of all generated files available for download.

**Query Parameters**:

- `category`: (optional) Filter files by category (dithered, rendered, schematic, web)

**Response**:

```json
{
  "taskId": "uuid-task-identifier",
  "files": [
    {
      "fileId": "1",
      "filename": "dithered_image.png",
      "type": "image/png",
      "size": 12345,
      "category": "dithered"
    },
    {
      "fileId": "2",
      "filename": "minecraft_render.png",
      "type": "image/png",
      "size": 23456,
      "category": "rendered"
    },
    {
      "fileId": "3",
      "filename": "schematic.litematic",
      "type": "application/octet-stream",
      "size": 34567,
      "category": "schematic"
    }
  ]
}
```

### Download Individual File

**Endpoint**: `GET /api/conversion/{taskId}/files/{fileId}`

Download a specific generated file.

**Response**: The requested file as a direct download with appropriate MIME type.

### Download All Files

**Endpoint**: `GET /api/conversion/{taskId}/download`

Download all generated files as a ZIP archive.

**Response**: ZIP file containing all generated files.

### Download Selected Files

**Endpoint**: `POST /api/conversion/{taskId}/download`

Download selected files as a ZIP archive.

**Request Body**:

```json
{
  "fileIds": ["1", "3"]
}
```

**Response**: ZIP file containing selected files.

### Delete Task

**Endpoint**: `DELETE /api/conversion/{taskId}`

Delete a conversion task and all associated files.

**Response**:

```json
{
  "message": "Task uuid-task-identifier deletion initiated",
  "success": true
}
```

## Client Integration Example

Here's a complete example of how to integrate with the API using Python:

```python
import requests
import base64
import time
import json

# API base URL
BASE_URL = "http://localhost:8000/api"

def encode_image(image_path):
    """Encode image to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def start_conversion(image_path, width=None, height=None):
    """Start a new conversion task."""
    # Prepare request data
    data = {
        "image": encode_image(image_path),
        "filename": image_path.split("/")[-1],
        "algorithm": "floyd_steinberg",
        "exportSettings": {
            "exportTypes": ["png", "html"],
            "drawChunkLines": True,
            "drawBlockLines": True
        },
        "schematicSettings": {
            "generateSchematic": True,
            "author": "API Client Example"
        }
    }
    
    # Add optional parameters if provided
    if width:
        data["width"] = width
    if height:
        data["height"] = height
        
    # Send the request
    response = requests.post(f"{BASE_URL}/conversion/start", json=data)
    response.raise_for_status()
    return response.json()

def poll_until_complete(task_id, interval=2, timeout=300):
    """Poll the API until the task is complete or fails."""
    start_time = time.time()
    while True:
        response = requests.get(f"{BASE_URL}/conversion/{task_id}")
        response.raise_for_status()
        status_data = response.json()
        
        status = status_data["status"]
        progress = status_data.get("progress", 0)
        
        print(f"Status: {status}, Progress: {progress}%")
        
        if status == "completed":
            return status_data
        elif status == "failed":
            raise Exception(f"Task failed: {status_data.get('error', 'Unknown error')}")
        
        # Check if we've exceeded the timeout
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Task processing timed out after {timeout} seconds")
            
        time.sleep(interval)

def download_files(task_id):
    """Download all files for a completed task."""
    # Get list of available files
    response = requests.get(f"{BASE_URL}/conversion/{task_id}/files")
    response.raise_for_status()
    files_data = response.json()
    
    # Print available files
    print(f"Available files ({len(files_data['files'])}):")
    for file in files_data["files"]:
        print(f" - {file['filename']} ({file['category']}, {file['size']} bytes)")
    
    # Download ZIP of all files
    print("Downloading ZIP of all files...")
    response = requests.get(f"{BASE_URL}/conversion/{task_id}/download")
    response.raise_for_status()
    
    # Save ZIP file
    zip_filename = f"pixeletica_task_{task_id}.zip"
    with open(zip_filename, "wb") as f:
        f.write(response.content)
    
    print(f"Files downloaded to: {zip_filename}")

# Main execution
if __name__ == "__main__":
    # Start a conversion task
    image_path = "example.png"  # Replace with your image path
    task_data = start_conversion(image_path, width=100)
    
    task_id = task_data["taskId"]
    print(f"Task started with ID: {task_id}")
    
    # Poll until the task completes
    result = poll_until_complete(task_id)
    print("Task completed successfully!")
    
    # Download the files
    download_files(task_id)
```

## Status Codes

The API uses standard HTTP status codes:

- `200 OK`: Request succeeded
- `202 Accepted`: Request accepted for processing (async tasks)
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server-side error

## Rate Limiting and Performance Considerations

- Large images may take longer to process
- The API is designed to handle multiple concurrent requests, but performance depends on server resources
- File storage is temporary; tasks and their associated files are automatically deleted after 7 days

## Rate Limiting

The API is rate-limited to 5 requests per minute. If you exceed this limit, you will receive a `429 Too Many Requests` error.

## Security and Authentication

This version of the API does not include built-in authentication. For production environments, it's recommended to:

1. Deploy the API behind a reverse proxy like Nginx or Apache
2. Implement API key authentication or OAuth2
3. Set up HTTPS for secure data transmission
