# Pixeletica API: Image Conversion Endpoint

This document describes the `/conversion/start` endpoint for the Pixeletica API which follows REST standards for multipart/form-data requests.

## REST-Standard Approach

The endpoint follows the recommended REST approach for file uploads:
- One field for the binary file data (`image_file`) 
- One field for JSON metadata (`metadata`) containing all other parameters

This approach is cleaner and more maintainable than using many individual form fields.

## API Endpoint

```
POST /conversion/start
```

## Request Format

The request must use `multipart/form-data` content type with two fields:

| Field | Type | Description |
|-------|------|-------------|
| `image_file` | File | The image to convert |
| `metadata` | String | JSON string containing all configuration parameters |

### Metadata JSON Schema

The `metadata` field must contain a valid JSON string with the following structure:

```json
{
  "width": 128,
  "height": 128, 
  "dithering_algorithm": "floyd_steinberg",
  "color_palette": "minecraft",
  "origin_x": 0,
  "origin_y": 100,
  "origin_z": 0,
  "chunk_line_color": "#FF0000FF", 
  "block_line_color": "#000000FF",
  "line_visibilities": ["no_lines", "block_grid_only", "chunk_lines_only", "both"],
  "image_division": 2,
  "generate_schematic": true,
  "schematic_name": "my_schematic",
  "schematic_author": "Pixeletica API",
  "schematic_description": "An awesome schematic",
  "generate_web_files": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `width` | Integer | Yes | - | Target width in pixels |
| `height` | Integer | Yes | - | Target height in pixels |
| `dithering_algorithm` | String | No | "floyd_steinberg" | Algorithm to use: "floyd_steinberg", "ordered", or "random" |
| `color_palette` | String | No | "minecraft" | Color palette for block mapping |
| `origin_x` | Integer | No | 0 | X-coordinate origin in Minecraft |
| `origin_y` | Integer | No | 100 | Y-coordinate (height) origin |
| `origin_z` | Integer | No | 0 | Z-coordinate origin in Minecraft |
| `chunk_line_color` | String | No | "#FF0000FF" | Hex color for chunk lines (RGBA) |
| `block_line_color` | String | No | "#000000FF" | Hex color for block grid lines (RGBA) |
| `line_visibilities` | Array | No | ["chunk_lines_only"] | Line visibility options |
| `image_division` | Integer | No | 1 | Number of parts to split the image into |
| `generate_schematic` | Boolean | No | false | Whether to generate schematic |
| `schematic_name` | String | No | null | Name of schematic file |
| `schematic_author` | String | No | "Pixeletica API" | Author of schematic |
| `schematic_description` | String | No | null | Description of schematic |
| `generate_web_files` | Boolean | No | true | Generate web viewer files |

## Examples

### cURL Example

```bash
curl -X POST "http://localhost:8000/conversion/start" \
  -H "accept: application/json" \
  -F "image_file=@/path/to/your/image.png" \
  -F 'metadata={
    "width": 128,
    "height": 128,
    "dithering_algorithm": "floyd_steinberg",
    "line_visibilities": ["no_lines", "block_grid_only", "chunk_lines_only", "both"],
    "image_division": 2,
    "generate_schematic": true
  }'
```

### JavaScript (Fetch API) Example

```javascript
// Create FormData object
const formData = new FormData();

// Add image file (from a file input or other source)
formData.append('image_file', imageFile);

// Create metadata JSON
const metadata = {
  width: 128,
  height: 128,
  dithering_algorithm: "floyd_steinberg",
  color_palette: "minecraft",
  line_visibilities: ["no_lines", "block_grid_only", "chunk_lines_only", "both"],
  image_division: 2,
  generate_schematic: true,
  schematic_name: "my_awesome_build",
  schematic_author: "Pixeletica API",
  schematic_description: "An awesome build created with Pixeletica"
};

// Add metadata as a JSON string
formData.append('metadata', JSON.stringify(metadata));

// Send the request
fetch('http://localhost:8000/conversion/start', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => {
  console.log('Success:', data);
  // data contains taskId, status, etc.
})
.catch(error => {
  console.error('Error:', error);
});
```

## Response Format

Upon successful submission, the API returns a response with status code 202 (Accepted) and a JSON body:

```json
{
  "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "status": "queued",
  "progress": 0,
  "timestamp": "2024-04-13T21:30:00.000Z",
  "error": null
}
```

You can use the returned `taskId` to check the task status using the `/conversion/{taskId}` endpoint.

## Error Handling

Common error responses:

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid JSON metadata format |
| 413 | Request Entity Too Large - Image exceeds size limit |
| 500 | Internal Server Error |

Example error response:

```json
{
  "detail": "Invalid JSON metadata format. Must be a valid JSON string."
}
```
