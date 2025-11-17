"""Error handling utilities for CLI commands."""

import sys
from typing import Optional, Callable, Any

from src.lib.logging import get_logger

logger = get_logger(__name__)


class CLIError(Exception):
    """Base exception for CLI errors.

    Attributes:
        message: Error message
        exit_code: Exit code to use when this error occurs
    """

    def __init__(self, message: str, exit_code: int = 1):
        """Initialize CLI error.

        Args:
            message: Error message
            exit_code: Exit code (default: 1)
        """
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class CLIErrorHandler:
    """Centralized error handling for CLI commands.

    Provides consistent error handling and logging across all commands.
    """

    @staticmethod
    def handle_error(error: Exception, command_name: str = "cli") -> int:
        """Handle an error and return appropriate exit code.

        Args:
            error: Exception that occurred
            command_name: Name of command that raised the error

        Returns:
            Exit code
        """
        if isinstance(error, CLIError):
            # Custom CLI error with explicit exit code
            logger.error(f"{command_name} failed: {error.message}")
            print(f"❌ Error: {error.message}", file=sys.stderr)
            return error.exit_code

        elif isinstance(error, KeyboardInterrupt):
            # User interrupted
            logger.info(f"{command_name} interrupted by user")
            print("\n\nInterrupted by user")
            return 130

        elif isinstance(error, FileNotFoundError):
            # File not found
            logger.error(f"{command_name} failed: {error}", exc_info=True)
            print(f"❌ File not found: {error}", file=sys.stderr)
            return 1

        elif isinstance(error, ValueError):
            # Invalid value/argument
            logger.error(f"{command_name} failed: {error}", exc_info=True)
            print(f"❌ Invalid value: {error}", file=sys.stderr)
            return 1

        else:
            # Unexpected error
            logger.error(f"{command_name} failed with unexpected error: {error}", exc_info=True)
            print(f"❌ Unexpected error: {error}", file=sys.stderr)
            return 1

    @staticmethod
    def wrap_command(func: Callable, command_name: str = "cli") -> Callable:
        """Wrap a command function with error handling.

        Args:
            func: Command function to wrap
            command_name: Name of command (for logging)

        Returns:
            Wrapped function that handles errors
        """
        def wrapper(*args, **kwargs) -> int:
            try:
                result = func(*args, **kwargs)
                # If function returns None, assume success
                return result if isinstance(result, int) else 0
            except Exception as e:
                return CLIErrorHandler.handle_error(e, command_name)

        return wrapper

    @staticmethod
    def validate_file_exists(file_path: str, file_type: str = "file") -> None:
        """Validate that a file exists.

        Args:
            file_path: Path to file
            file_type: Type of file (for error message)

        Raises:
            CLIError: If file does not exist
        """
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            raise CLIError(f"{file_type.capitalize()} not found: {file_path}")

        if not path.is_file():
            raise CLIError(f"Path is not a file: {file_path}")

    @staticmethod
    def validate_dir_exists(dir_path: str, dir_type: str = "directory") -> None:
        """Validate that a directory exists.

        Args:
            dir_path: Path to directory
            dir_type: Type of directory (for error message)

        Raises:
            CLIError: If directory does not exist
        """
        from pathlib import Path

        path = Path(dir_path)
        if not path.exists():
            raise CLIError(f"{dir_type.capitalize()} not found: {dir_path}")

        if not path.is_dir():
            raise CLIError(f"Path is not a directory: {dir_path}")

    @staticmethod
    def confirm_action(message: str, default: bool = False) -> bool:
        """Prompt user to confirm an action.

        Args:
            message: Confirmation message
            default: Default value if user presses enter

        Returns:
            True if user confirms, False otherwise
        """
        suffix = " [Y/n]" if default else " [y/N]"
        response = input(message + suffix + " ").strip().lower()

        if not response:
            return default

        return response in ['y', 'yes']
