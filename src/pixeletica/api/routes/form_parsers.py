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
    Expects a JSON-encoded list of enum values like '["no_lines", "chunk_lines_only"]'.

    Returns:
        A list of LineVisibilityOption enum values
    """
    if not line_visibilities:
        # Return default value
        return [LineVisibilityOption.CHUNK_LINES_ONLY]

    try:
        parsed_value = json.loads(line_visibilities)

        if isinstance(parsed_value, list):
            return [LineVisibilityOption(v) for v in parsed_value]

        elif isinstance(parsed_value, str):
            # Backwards compatibility: single string -> wrap in list
            return [LineVisibilityOption(parsed_value)]

        else:
            raise ValueError()

    except (json.JSONDecodeError, ValueError):
        valid_options = [v.value for v in LineVisibilityOption]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid line visibility option(s): {line_visibilities}. Expected one or more of: {valid_options}",
        )
