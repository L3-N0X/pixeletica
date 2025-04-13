# Pixeletica Backend Implementation Checklist

## Phase 1: Core Image Processing Engine

- [X] Implement base image processing functionality
  - [X] Image loading and validation
  - [X] Image resizing with aspect ratio preservation
  - [X] Color mapping algorithms
- [X] Implement all dithering algorithms
  - [X] No dithering (simple color mapping to nearest color)
  - [X] Floyd-Steinberg dithering
  - [X] Ordered dithering with Bayer matrices
  - [X] Random dithering with noise
- [X] Create result storage system
  - [X] Define directory structure for task outputs
  - [X] Implement file naming conventions

## Phase 2: Export Generation

- [X] Implement dithered image export
  - [X] PNG output with configurable size
  - [X] Color-accurate representation
- [X] Create Minecraft texture rendering
  - [X] Load and stitch together textures from Minecraft assets
  - [X] Generate a single image from multiple textures
- [X] Implement schematic generation
  - [X] Create Litematica schematic files
  - [X] Include metadata (author, name, description)
  - [X] Support configurable X, Z and Y-axis orientation
  - [X] Ensure that the Y coordinate is used as the height, offset is X and Z
- [X] Develop web optimization
  - [X] Generate 512×512 tiles for web viewing
  - [X] Generate JSON metadata for tile information
- [X] Create split export functionality
  - [X] Divide images into configurable parts
  - [X] Preserve coordinates across split parts
  - [X] Generate overview showing the division

## Phase 3: Grid and Visualization Options

- [X] Implement chunk line system
  - [X] Calculate chunk boundaries from world coordinates
  - [X] Add customizable chunk line colors
  - [X] Support alpha channel for transparency
  - [X] Make sure the chunk lines are calculated correctly, as now 1 pixel = 16 pixels because of the 16×16 texture size, so one chunk is 256×256 pixels
- [X] Create block grid system
  - [X] Generate block boundaries for individual blocks
  - [X] Support customizable block line colors
  - [X] Add option to toggle block grid visibility
  - [X] Make sure the block grid is calculated correctly, as now 1 pixel = 16 pixels because of the 16×16 texture size
- [X] Implement coordinate system
  - [X] Support specific world coordinates (X,Y,Z) where Y is the height
  - [X] Calculate correct chunk positions
  - [X] Generate block position information
- [X] Create block information system
  - [X] Map each pixel to a specific Minecraft block
  - [X] Store detailed block data (name, ID, coordinates)

## Phase 4: API Implementation

- [X] Create FastAPI application structure
  - [X] Define API routes based on OpenAPI specification
  - [X] Implement request validation
  - [X] Set up CORS handling
- [X] Implement conversion endpoints
  - [X] POST `/api/conversion/start` for new conversions
  - [X] GET `/api/conversion/{taskId}` for status checks
  - [X] DELETE `/api/conversion/{taskId}` for task deletion
- [X] Create file handling endpoints
  - [X] GET `/api/conversion/{taskId}/files` for file listing
  - [X] GET `/api/conversion/{taskId}/files/{fileId}` for single file download
  - [X] GET `/api/conversion/{taskId}/download` for batch download
  - [X] POST `/api/conversion/{taskId}/download` for selective download
- [X] Implement map viewer endpoints
  - [X] GET `/api/map/{mapId}/metadata.json` for map information
  - [X] GET `/api/map/{mapId}/tiles/{zoom}/{x}/{y}.png` for tile serving
  - [X] GET `/api/maps.json` for listing available maps (all previously exported maps)

## Phase 5: Task Management System

- [X] Implement background task processing
  - [X] Set up Celery for task queue
  - [X] Configure Redis as message broker
  - [X] Create worker processes for image conversion
- [X] Develop task tracking system
  - [X] Track task status (queued, processing, completed, failed)
  - [X] Calculate and update progress percentage
  - [X] Store task history and metadata
- [X] Create error handling system
  - [X] Implement detailed error logging
  - [X] Generate user-friendly error messages
  - [X] Add retry logic for recoverable errors
- [X] Implement logging system
  - [X] Set up logging for API requests and responses
  - [X] Log errors and exceptions for debugging
  - [X] Ensure logs are stored securely and efficiently

## Phase 6: File Management

- [X] Implement file storage system
  - [X] Create directory structure for task files
  - [X] Generate unique filenames to prevent collisions
  - [X] Old files can be deleted if the user deletes the Map with the API
- [X] Add file metadata tracking
  - [X] Store file sizes and types
  - [X] Categorize files (dithered, rendered, schematic, web)
- [X] Create ZIP archive generation if needed to send to the frontend for download
  - [X] Package all files for batch download
  - [X] Support selective file inclusion
  - [X] Add metadata files to archives
  - [X] Ensure proper error handling during ZIP creation

## Phase 7: Docker and Deployment

- [X] Create Docker configuration
  - [X] Set up multi-container architecture (API, Worker, Redis)
  - [X] Configure volume mappings for data persistence
  - [X] Create networking between containers
- [X] Implement environment configuration
  - [X] Support environment variables for configuration
  - [X] Create sensible defaults for all settings
  - [X] Document all configuration options
- [X] Add health checks and monitoring
  - [X] Create health check endpoints
  - [X] Implement container readiness checks
  - [X] Add basic monitoring capabilities
- [X] Configure scaling options
  - [X] Support multiple worker processes
  - [X] Ensure thread safety for shared resources
  - [X] Implement proper locking mechanisms

## Phase 8: Security and Performance

- [X] Implement security measures
  - [X] Add request validation and sanitization
  - [X] Configure file size limits and rate limiting
  - [X] Implement basic protection against abuse
- [X] Optimize performance
  - [X] Add caching for frequently accessed files
  - [X] Add tile caching for map viewer

## Phase 9: Documentation and Testing

- [X] Create user and developer documentation
  - [X] Installation guides (standard and Docker)
  - [X] API usage examples
  - [X] Explanation of algorithms and options
  - [X] Troubleshooting guides
