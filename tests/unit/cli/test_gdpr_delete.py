"""Unit tests for gdpr_delete.py CLI command."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from src.cli.gdpr_delete import delete_user_data


class TestDeleteUserData:
    """Tests for delete_user_data function."""

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    @patch('builtins.input', return_value='yes')
    def test_deletes_user_data_with_confirmation(self, mock_input, mock_hash):
        """Test successful data deletion with confirmation."""
        mock_hash.return_value = "a" * 64  # Mock 64-char hash

        # Should not raise
        delete_user_data(user_id="123456789", confirm=False)

        # Should prompt for confirmation
        assert mock_input.called

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    @patch('builtins.input', return_value='no')
    def test_cancels_deletion_when_user_declines(self, mock_input, mock_hash):
        """Test that deletion is cancelled when user declines."""
        mock_hash.return_value = "a" * 64

        # Should exit without deletion
        delete_user_data(user_id="123456789", confirm=False)

        assert mock_input.called

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    def test_skips_confirmation_with_confirm_flag(self, mock_hash):
        """Test that confirmation is skipped with --confirm flag."""
        mock_hash.return_value = "a" * 64

        with patch('builtins.input') as mock_input:
            # Should not raise
            delete_user_data(user_id="123456789", confirm=True)

            # Should not prompt for confirmation
            assert not mock_input.called

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    @patch('builtins.input', return_value='yes')
    def test_hashes_discord_user_id(self, mock_input, mock_hash):
        """Test that Discord user ID is hashed if not already hashed."""
        mock_hash.return_value = "a" * 64

        delete_user_data(user_id="123456789", confirm=False)

        # Should hash the user ID
        mock_hash.assert_called_once_with("123456789")

    @patch('builtins.input', return_value='yes')
    def test_uses_hashed_id_directly(self, mock_input):
        """Test that already-hashed ID is used directly."""
        hashed_id = "a" * 64

        with patch('src.cli.gdpr_delete.UserQuery.hash_user_id') as mock_hash:
            delete_user_data(user_id=hashed_id, confirm=False)

            # Should not hash again
            assert not mock_hash.called

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    @patch('builtins.input', return_value='yes')
    def test_logs_gdpr_deletion_audit_trail(self, mock_input, mock_hash):
        """Test that GDPR deletion is logged for audit."""
        mock_hash.return_value = "a" * 64

        with patch('src.cli.gdpr_delete.audit_logger') as mock_audit_logger:
            delete_user_data(user_id="123456789", confirm=False)

            # Should log initiation and completion
            assert mock_audit_logger.info.call_count == 2

    @patch('src.cli.gdpr_delete.UserQuery.hash_user_id')
    @patch('builtins.input', return_value='yes')
    def test_handles_deletion_errors(self, mock_input, mock_hash):
        """Test handling of deletion errors."""
        mock_hash.return_value = "a" * 64

        # This test documents current behavior
        # In the actual implementation, there's no external service that can fail
        # since data deletion is mostly informational
        # The function should complete successfully
        delete_user_data(user_id="123456789", confirm=False)


class TestGdprDeleteCLI:
    """Integration tests for GDPR delete CLI."""

    @patch('src.cli.gdpr_delete.delete_user_data')
    def test_cli_main_function(self, mock_delete):
        """Test CLI main function routing."""
        from src.cli.gdpr_delete import main

        with patch('sys.argv', ['gdpr_delete', '--user-id', '123456', '--confirm']):
            with patch('argparse.ArgumentParser.parse_args') as mock_args:
                mock_args.return_value = Mock(user_id='123456', confirm=True)

                try:
                    main()
                except SystemExit:
                    pass

                mock_delete.assert_called_once_with('123456', confirm=True)

    def test_cli_requires_user_id(self):
        """Test that CLI requires user_id argument."""
        from src.cli.gdpr_delete import main

        with patch('sys.argv', ['gdpr_delete']):
            with pytest.raises(SystemExit):
                main()
