"""Command registry for managing CLI commands."""

from argparse import ArgumentParser, _SubParsersAction
from typing import Dict, List, Type

from src.cli.core.command_base import CLICommand
from src.lib.logging import get_logger

logger = get_logger(__name__)


class CommandRegistry:
    """Registry for CLI commands.

    Follows the Registry Pattern for managing command instances.
    Provides a centralized place to register and retrieve commands.
    """

    def __init__(self):
        """Initialize empty command registry."""
        self._commands: Dict[str, CLICommand] = {}

    def register(self, command: CLICommand) -> None:
        """Register a command.

        Args:
            command: Command instance to register

        Raises:
            ValueError: If command name is already registered
        """
        if command.name in self._commands:
            raise ValueError(f"Command '{command.name}' is already registered")

        self._commands[command.name] = command
        logger.debug(f"Registered command: {command.name}")

    def get(self, name: str) -> CLICommand:
        """Get a registered command by name.

        Args:
            name: Command name

        Returns:
            Command instance

        Raises:
            KeyError: If command not found
        """
        if name not in self._commands:
            raise KeyError(f"Command '{name}' not found")

        return self._commands[name]

    def get_all(self) -> List[CLICommand]:
        """Get all registered commands.

        Returns:
            List of all registered commands
        """
        return list(self._commands.values())

    def configure_parser(self, parser: ArgumentParser) -> _SubParsersAction:
        """Configure argument parser with all registered commands.

        Args:
            parser: Main argument parser

        Returns:
            Subparsers action for adding commands
        """
        subparsers = parser.add_subparsers(
            dest="command",
            help="Available commands",
            required=True,
        )

        for command in self._commands.values():
            cmd_parser = subparsers.add_parser(
                command.name,
                help=command.help_text,
                description=command.description,
            )
            command.configure_parser(cmd_parser)

        return subparsers

    def has_command(self, name: str) -> bool:
        """Check if a command is registered.

        Args:
            name: Command name

        Returns:
            True if command is registered, False otherwise
        """
        return name in self._commands

    def __len__(self) -> int:
        """Get number of registered commands."""
        return len(self._commands)
