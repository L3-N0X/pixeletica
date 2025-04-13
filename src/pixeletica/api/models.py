"""
Pydantic models for the Pixeletica API.

These models define the data structures used for API requests and responses.
"""

from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DitherAlgorithm(str, Enum):
    """Supported dithering algorithms."""

    FLOYD_STEINBERG = "floyd_steinberg"
    ORDERED = "ordered"
    RANDOM = "random"

    @classmethod
    def get_default(cls) -> "DitherAlgorithm":
        """Return the default dithering algorithm."""
        return cls.FLOYD_STEINBERG


class TaskStatus(str, Enum):
    """Possible states of a conversion task."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportSettings(BaseModel):
    """Settings for exporting the converted image."""

    exportTypes: List[Literal["png"]] = Field(
        default=["png"], description="Output file formats to generate"
    )
    originX: int = Field(
        default=0, description="X-coordinate origin in Minecraft world"
    )
    originY: int = Field(
        default=0, description="Y-coordinate origin in Minecraft world"
    )
    originZ: int = Field(
        default=0, description="Z-coordinate origin in Minecraft world"
    )
    drawChunkLines: bool = Field(default=True, description="Draw chunk boundary lines")
    chunkLineColor: str = Field(default="#FF0000", description="Color for chunk lines")
    drawBlockLines: bool = Field(default=True, description="Draw block boundary lines")
    blockLineColor: str = Field(default="#000000", description="Color for block lines")
    splitCount: int = Field(
        default=1, description="Number of segments to split the image into"
    )
    versionOptions: Dict = Field(
        default={}, description="Additional version-specific options"
    )


class SchematicSettings(BaseModel):
    """Settings for Litematica schematic generation."""

    generateSchematic: bool = Field(
        default=False, description="Whether to generate a schematic"
    )
    author: Optional[str] = Field(
        default="Pixeletica API", description="Schematic author name"
    )
    name: Optional[str] = Field(default=None, description="Schematic name")
    description: Optional[str] = Field(
        default=None, description="Schematic description"
    )


class ConversionRequest(BaseModel):
    """Request model for starting a conversion task."""

    image: str = Field(..., description="Base64-encoded image data")
    filename: str = Field(..., description="Original filename with extension")
    width: Optional[int] = Field(default=None, description="Target width (pixels)")
    height: Optional[int] = Field(default=None, description="Target height (pixels)")
    algorithm: DitherAlgorithm = Field(
        default=DitherAlgorithm.FLOYD_STEINBERG,
        description="Dithering algorithm to use",
    )
    exportSettings: ExportSettings = Field(
        default_factory=ExportSettings, description="Output file settings"
    )
    schematicSettings: SchematicSettings = Field(
        default_factory=SchematicSettings, description="Schematic generation settings"
    )


class TaskResponse(BaseModel):
    """Response model for a task status check."""

    taskId: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    progress: Optional[int] = Field(
        default=None, description="Progress percentage (0-100)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Last status update time"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if task failed"
    )


class FileInfo(BaseModel):
    """Information about a generated file."""

    fileId: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    type: str = Field(..., description="MIME type")
    size: int = Field(..., description="File size in bytes")
    category: str = Field(
        ..., description="File category (dithered, rendered, schematic, etc.)"
    )


class FileListResponse(BaseModel):
    """Response model listing available files for a task."""

    taskId: str = Field(..., description="Task identifier")
    files: List[FileInfo] = Field(default_factory=list, description="Available files")


class SelectiveDownloadRequest(BaseModel):
    """Request model for downloading selected files."""

    fileIds: List[str] = Field(..., description="IDs of files to include in download")


class MapInfo(BaseModel):
    """Information about an available map."""

    id: str = Field(..., description="Map identifier (task ID)")
    name: str = Field(..., description="Human-readable map name")
    created: datetime = Field(..., description="Creation timestamp")
    thumbnail: str = Field(..., description="URL to thumbnail image")
    description: Optional[str] = Field(default=None, description="Map description")


class MapListResponse(BaseModel):
    """Response model for the maps list endpoint."""

    maps: List[MapInfo] = Field(default_factory=list, description="Available maps")


class MapMetadata(BaseModel):
    """Detailed metadata about a map."""

    id: str = Field(..., description="Map identifier (task ID)")
    name: str = Field(..., description="Map name")
    width: int = Field(..., description="Map width in blocks")
    height: int = Field(..., description="Map height in blocks")
    origin_x: int = Field(..., description="X-coordinate origin")
    origin_z: int = Field(..., description="Z-coordinate origin")
    created: datetime = Field(..., description="Creation timestamp")
    tileSize: int = Field(..., description="Size of each tile in pixels")
    maxZoom: int = Field(..., description="Maximum available zoom level")
    minZoom: int = Field(..., description="Minimum available zoom level")
    tileFormat: str = Field(default="png", description="Format of the tiles")
    description: Optional[str] = Field(default=None, description="Map description")
    extraMeta: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional metadata"
    )
