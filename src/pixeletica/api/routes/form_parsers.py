"""
Utility functions for parsing form data in FastAPI routes.
"""

import json
from fastapi import Form, HTTPException, status
from src.pixeletica.api.models import LineVisibilityOption


async def parse_line_visibilities(
    line_visibilities: str = Form(default=None),
) -> LineVisibilityOption:
    """
    Parse line_visibilities parameter from form data.
    Expects a string enum value like 'no_lines' or 'chunk_lines_only'

    Returns:
        A LineVisibilityOption enum value
    """
    if not line_visibilities:
        # Return default value
        return LineVisibilityOption.CHUNK_LINES_ONLY

    try:
        # Try to parse as a JSON string first (for backwards compatibility)
        try:
            parsed_value = json.loads(line_visibilities)

            # If it's a JSON array, take the first value (backwards compatibility)
            if isinstance(parsed_value, list) and len(parsed_value) > 0:
                value = parsed_value[0]
            # If it's a string directly, use it
            elif isinstance(parsed_value, str):
                value = parsed_value
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid line visibility format: {line_visibilities}. Expected a string enum value.",
                )

            return LineVisibilityOption(value)

        except json.JSONDecodeError:
            # Not JSON, treat as raw string value
            return LineVisibilityOption(line_visibilities)

    except ValueError:
        valid_options = [v.value for v in LineVisibilityOption]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid line visibility option: {line_visibilities}. Expected one of: {valid_options}",
        )
