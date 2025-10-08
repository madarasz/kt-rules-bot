"""Discord-related utility functions."""

import random
from pathlib import Path

from src.lib.constants import ACKNOWLEDGEMENTS_FILE_PATH
from src.lib.logging import get_logger

logger = get_logger(__name__)


def get_random_acknowledgement() -> str:
    """Get a random acknowledgement message from the acknowledgements file.
    
    Returns:
        A random acknowledgement message string, or a fallback message if file cannot be read.
    """
    try:
        # Get the project root (assumes this file is in src/lib/)
        project_root = Path(__file__).parent.parent.parent
        file_path = project_root / ACKNOWLEDGEMENTS_FILE_PATH
        
        if not file_path.exists():
            logger.warning(f"Acknowledgements file not found at: {file_path}")
            return "Processing your query..."
            
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            
        if not lines:
            logger.warning("Acknowledgements file is empty")
            return "Processing your query..."
            
        return random.choice(lines)
        
    except Exception as e:
        logger.error(f"Error reading acknowledgements file: {e}")
        return "Processing your query..."