"""
Utility functions for parsing form data in FastAPI routes.
"""

import json
from typing import List
from fastapi import Form, HTTPException, status
from src.pixeletica.api.models import LineVisibilityOption


async def parse_line_visibilities(
    line_visibilities: str = Form(default=None),
) -> List[LineVisibilityOption]:
    """
    Parse line_visibilities parameter from form data.
    Expects a JSON string array like '["no_lines","block_grid_only"]'

    Returns:
        List of LineVisibilityOption enum values
    """
    if not line_visibilities:
        # Return default value
        return [LineVisibilityOption.CHUNK_LINES_ONLY]

    try:
        # Parse the JSON string array
        values = json.loads(line_visibilities)

        # Validate each value is a valid enum option
        result = []
        for val in values:
            try:
                result.append(LineVisibilityOption(val))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid line visibility option: {val}. Expected one of: {[v.value for v in LineVisibilityOption]}",
                )

        return result
    except json.JSONDecodeError:
        # Try to handle a single value case
        try:
            return [LineVisibilityOption(line_visibilities)]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid line_visibilities format. Expected JSON array or single value. Got: {line_visibilities}",
            )
