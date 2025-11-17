"""Discord-related utility functions."""

import random
from pathlib import Path

from src.lib.logging import get_logger
from src.lib.personality import get_acknowledgements_path, get_disclaimers_path

logger = get_logger(__name__)


def get_random_acknowledgement() -> str:
    """Get a random acknowledgement message from the acknowledgements file.

    Returns:
        A random acknowledgement message string, or a fallback message if file cannot be read.
    """
    try:
        # Get the project root (assumes this file is in src/lib/)
        project_root = Path(__file__).parent.parent.parent
        file_path = project_root / get_acknowledgements_path()

        if not file_path.exists():
            logger.warning(f"Acknowledgements file not found at: {file_path}")
            return "Processing your query..."

        with open(file_path, encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        if not lines:
            logger.warning("Acknowledgements file is empty")
            return "Processing your query..."

        return random.choice(lines)  # nosec B311 (not used for security/crypto)

    except Exception as e:
        logger.error(f"Error reading acknowledgements file: {e}")
        return "Processing your query..."


def get_random_disclaimer() -> str:
    """Get a random disclaimer message from the disclaimers file.

    Returns:
        A random disclaimer message string, or a fallback message if file cannot be read.
    """
    try:
        # Get the project root (assumes this file is in src/lib/)
        project_root = Path(__file__).parent.parent.parent
        file_path = project_root / get_disclaimers_path()

        if not file_path.exists():
            logger.warning(f"Disclaimers file not found at: {file_path}")
            return "This interpretation is auto-generated. Consult official rules for certainty."

        with open(file_path, encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        if not lines:
            logger.warning("Disclaimers file is empty")
            return "This interpretation is auto-generated. Consult official rules for certainty."

        return random.choice(lines)  # nosec B311 (not used for security/crypto)

    except Exception as e:
        logger.error(f"Error reading disclaimers file: {e}")
        return "This interpretation is auto-generated. Consult official rules for certainty."
