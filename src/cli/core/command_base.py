"""Base class for CLI commands following SOLID principles."""

from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from typing import Optional


class CLICommand(ABC):
    """Abstract base class for CLI commands.

    Follows the Command Pattern and Single Responsibility Principle.
    Each command is responsible for:
    1. Defining its own arguments
    2. Executing its specific functionality
    3. Handling its own validation
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (e.g., 'run', 'ingest', 'query')."""
        pass

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Short help text shown in command list."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description shown in --help."""
        pass

    @abstractmethod
    def configure_parser(self, parser: ArgumentParser) -> None:
        """Configure argument parser for this command.

        Args:
            parser: Argument parser to configure
        """
        pass

    @abstractmethod
    def execute(self, args: Namespace) -> int:
        """Execute the command.

        Args:
            args: Parsed command-line arguments

        Returns:
            Exit code (0 = success, non-zero = error)
        """
        pass

    def validate_args(self, args: Namespace) -> Optional[str]:
        """Validate command arguments.

        Args:
            args: Parsed arguments

        Returns:
            Error message if validation fails, None if valid
        """
        return None
