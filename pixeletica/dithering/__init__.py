"""
Dithering algorithm implementations.
"""

from pixeletica.dithering.no_dither import apply_no_dithering
from pixeletica.dithering.floyd_steinberg import apply_floyd_steinberg_dithering
from pixeletica.dithering.ordered_dither import apply_ordered_dithering
from pixeletica.dithering.random_dither import apply_random_dithering

__all__ = [
    "apply_floyd_steinberg_dithering",
    "apply_ordered_dithering",
    "apply_random_dithering",
    "get_algorithm_by_name",
]

# Dictionary of available dithering algorithms
ALGORITHMS = {
    "floyd_steinberg": {
        "name": "Floyd-Steinberg",
        "function": apply_floyd_steinberg_dithering,
        "id": "Floyd_Steinberg",
    },
    "ordered": {
        "name": "Ordered Dithering",
        "function": apply_ordered_dithering,
        "id": "Ordered",
    },
    "random": {
        "name": "Random Dithering",
        "function": apply_random_dithering,
        "id": "Random",
    },
}


def get_algorithm_by_name(algorithm_name):
    """
    Get a dithering algorithm by its name.

    Args:
        algorithm_name: Name/key of the algorithm

    Returns:
        Tuple of (algorithm_function, algorithm_id) or (None, None) if not found
    """
    algorithm = ALGORITHMS.get(algorithm_name)
    if algorithm:
        return algorithm["function"], algorithm["id"]
    return None, None
