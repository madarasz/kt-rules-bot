"""Unit tests for CLI main entry point (__main__.py)."""

import sys
from unittest.mock import Mock, patch

import pytest

from src.cli.__main__ import create_parser, main


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_has_version(self):
        """Test that parser includes version flag."""
        parser = create_parser()

        # Version should be accessible
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(['--version'])

        assert exc_info.value.code == 0

    def test_parser_requires_command(self):
        """Test that parser requires a command."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_run_command_parser(self):
        """Test run command argument parsing."""
        parser = create_parser()

        # Test with default mode
        args = parser.parse_args(['run'])
        assert args.command == 'run'
        assert args.mode == 'production'

        # Test with dev mode
        args = parser.parse_args(['run', '--mode', 'dev'])
        assert args.mode == 'dev'

    def test_ingest_command_parser(self):
        """Test ingest command argument parsing."""
        parser = create_parser()

        # Test with source dir
        args = parser.parse_args(['ingest', '/path/to/rules'])
        assert args.command == 'ingest'
        assert args.source_dir == '/path/to/rules'
        assert args.force is False

        # Test with force flag
        args = parser.parse_args(['ingest', '/path/to/rules', '--force'])
        assert args.force is True

    def test_query_command_parser(self):
        """Test query command argument parsing."""
        parser = create_parser()

        # Test basic query
        args = parser.parse_args(['query', 'test question'])
        assert args.command == 'query'
        assert args.query == 'test question'
        assert args.max_chunks == 5
        assert args.rag_only is False

        # Test with all options
        args = parser.parse_args([
            'query', 'test',
            '--model', 'claude-4.5-sonnet',
            '--max-chunks', '10',
            '--rag-only',
            '--max-hops', '2'
        ])
        assert args.model == 'claude-4.5-sonnet'
        assert args.max_chunks == 10
        assert args.rag_only is True
        assert args.max_hops == 2

    def test_health_command_parser(self):
        """Test health command argument parsing."""
        parser = create_parser()

        # Test basic health check
        args = parser.parse_args(['health'])
        assert args.command == 'health'
        assert args.verbose is False
        assert args.wait_for_discord is False

        # Test with flags
        args = parser.parse_args(['health', '-v', '--wait-for-discord'])
        assert args.verbose is True
        assert args.wait_for_discord is True

    def test_gdpr_delete_command_parser(self):
        """Test gdpr-delete command argument parsing."""
        parser = create_parser()

        args = parser.parse_args(['gdpr-delete', '123456'])
        assert args.command == 'gdpr-delete'
        assert args.user_id == '123456'
        assert args.confirm is False

        # Test with confirm flag
        args = parser.parse_args(['gdpr-delete', '123456', '--confirm'])
        assert args.confirm is True

    def test_quality_test_command_parser(self):
        """Test quality-test command argument parsing."""
        parser = create_parser()

        # Test basic
        args = parser.parse_args(['quality-test'])
        assert args.command == 'quality-test'
        assert args.test is None
        assert args.model is None
        assert args.all_models is False
        assert args.runs == 1

        # Test with all options
        args = parser.parse_args([
            'quality-test',
            '--test', 'test-id',
            '--model', 'gpt-4.1',
            '--all-models',
            '--judge-model', 'claude-4.5-sonnet',
            '--yes',
            '--runs', '3',
            '--max-hops', '1',
            '--no-eval'
        ])
        assert args.test == 'test-id'
        assert args.model == 'gpt-4.1'
        assert args.all_models is True
        assert args.yes is True
        assert args.runs == 3
        assert args.max_hops == 1
        assert args.no_eval is True

    def test_rag_test_command_parser(self):
        """Test rag-test command argument parsing."""
        parser = create_parser()

        args = parser.parse_args(['rag-test'])
        assert args.command == 'rag-test'

        # Test with options
        args = parser.parse_args([
            'rag-test',
            '--test', 'test-id',
            '--runs', '5',
            '--max-chunks', '20',
            '--min-relevance', '0.5'
        ])
        assert args.test == 'test-id'
        assert args.runs == 5
        assert args.max_chunks == 20
        assert args.min_relevance == 0.5

    def test_rag_test_sweep_command_parser(self):
        """Test rag-test-sweep command argument parsing."""
        parser = create_parser()

        # Test parameter mode
        args = parser.parse_args([
            'rag-test-sweep',
            '--param', 'rrf_k',
            '--values', '40,60,80'
        ])
        assert args.command == 'rag-test-sweep'
        assert args.param == 'rrf_k'
        assert args.values == '40,60,80'

        # Test grid mode
        args = parser.parse_args([
            'rag-test-sweep',
            '--grid',
            '--max-chunks', '10,20',
            '--min-relevance', '0.4,0.5'
        ])
        assert args.grid is True
        assert args.max_chunks == '10,20'
        assert args.min_relevance == '0.4,0.5'

    def test_download_team_command_parser(self):
        """Test download-team command argument parsing."""
        parser = create_parser()

        args = parser.parse_args(['download-team', 'https://example.com/team.pdf'])
        assert args.command == 'download-team'
        assert args.url == 'https://example.com/team.pdf'

        # Test with options
        args = parser.parse_args([
            'download-team',
            'https://example.com/team.pdf',
            '--model', 'gemini-2.5-pro',
            '--team-name', 'pathfinders',
            '--update-date', '2024-01-01'
        ])
        assert args.model == 'gemini-2.5-pro'
        assert args.team_name == 'pathfinders'
        assert args.update_date == '2024-01-01'

    def test_download_all_teams_command_parser(self):
        """Test download-all-teams command argument parsing."""
        parser = create_parser()

        args = parser.parse_args(['download-all-teams'])
        assert args.command == 'download-all-teams'
        assert args.dry_run is False
        assert args.force is False

        # Test with flags
        args = parser.parse_args(['download-all-teams', '--dry-run', '--force'])
        assert args.dry_run is True
        assert args.force is True


class TestMainRouting:
    """Tests for main() command routing."""

    @patch('src.cli.__main__.run_bot')
    def test_routes_run_command(self, mock_run_bot):
        """Test that main routes run command correctly."""
        with patch('sys.argv', ['cli', 'run', '--mode', 'dev']):
            try:
                main()
            except SystemExit:
                pass

            mock_run_bot.assert_called_once_with(mode='dev')

    @patch('src.cli.__main__.ingest_rules')
    def test_routes_ingest_command(self, mock_ingest):
        """Test that main routes ingest command correctly."""
        with patch('sys.argv', ['cli', 'ingest', './rules', '--force']):
            try:
                main()
            except SystemExit:
                pass

            mock_ingest.assert_called_once_with(source_dir='./rules', force=True)

    @patch('src.cli.__main__.test_query')
    def test_routes_query_command(self, mock_query):
        """Test that main routes query command correctly."""
        with patch('sys.argv', [
            'cli', 'query', 'test question',
            '--model', 'claude-4.5-sonnet',
            '--max-chunks', '10',
            '--rag-only',
            '--max-hops', '1'
        ]):
            try:
                main()
            except SystemExit:
                pass

            mock_query.assert_called_once_with(
                query='test question',
                model='claude-4.5-sonnet',
                max_chunks=10,
                rag_only=True,
                max_hops=1
            )

    @patch('src.cli.__main__.health_check')
    def test_routes_health_command(self, mock_health):
        """Test that main routes health command correctly."""
        with patch('sys.argv', ['cli', 'health', '-v', '--wait-for-discord']):
            try:
                main()
            except SystemExit:
                pass

            mock_health.assert_called_once_with(
                verbose=True,
                wait_for_discord=True
            )

    @patch('src.cli.__main__.delete_user_data')
    def test_routes_gdpr_delete_command(self, mock_delete):
        """Test that main routes gdpr-delete command correctly."""
        with patch('sys.argv', ['cli', 'gdpr-delete', '123456', '--confirm']):
            try:
                main()
            except SystemExit:
                pass

            mock_delete.assert_called_once_with(user_id='123456', confirm=True)

    @patch('src.cli.__main__.quality_test')
    def test_routes_quality_test_command(self, mock_quality):
        """Test that main routes quality-test command correctly."""
        with patch('sys.argv', [
            'cli', 'quality-test',
            '--test', 'test-id',
            '--model', 'gpt-4.1',
            '--all-models',
            '--judge-model', 'claude-4.5-sonnet',
            '--yes',
            '--runs', '3',
            '--max-hops', '1',
            '--no-eval'
        ]):
            try:
                main()
            except SystemExit:
                pass

            mock_quality.assert_called_once_with(
                test_id='test-id',
                model='gpt-4.1',
                all_models=True,
                judge_model='claude-4.5-sonnet',
                skip_confirm=True,
                runs=3,
                max_hops=1,
                no_eval=True
            )

    @patch('src.cli.__main__.rag_test')
    def test_routes_rag_test_command(self, mock_rag_test):
        """Test that main routes rag-test command correctly."""
        with patch('sys.argv', [
            'cli', 'rag-test',
            '--test', 'test-id',
            '--runs', '5',
            '--max-chunks', '20',
            '--min-relevance', '0.5'
        ]):
            try:
                main()
            except SystemExit:
                pass

            mock_rag_test.assert_called_once_with(
                test_id='test-id',
                runs=5,
                max_chunks=20,
                min_relevance=0.5
            )

    @patch('src.cli.__main__.rag_test_sweep')
    def test_routes_rag_test_sweep_command(self, mock_sweep):
        """Test that main routes rag-test-sweep command correctly."""
        with patch('sys.argv', [
            'cli', 'rag-test-sweep',
            '--param', 'rrf_k',
            '--values', '40,60,80',
            '--test', 'test-id',
            '--runs', '2'
        ]):
            try:
                main()
            except SystemExit:
                pass

            mock_sweep.assert_called_once()

    @patch('src.cli.__main__.download_team')
    def test_routes_download_team_command(self, mock_download):
        """Test that main routes download-team command correctly."""
        with patch('sys.argv', [
            'cli', 'download-team',
            'https://example.com/team.pdf',
            '--model', 'gemini-2.5-pro',
            '--team-name', 'pathfinders',
            '--update-date', '2024-01-01'
        ]):
            try:
                main()
            except SystemExit:
                pass

            mock_download.assert_called_once_with(
                url='https://example.com/team.pdf',
                model='gemini-2.5-pro',
                team_name='pathfinders',
                update_date='2024-01-01'
            )

    @patch('src.cli.__main__.download_all_teams')
    def test_routes_download_all_teams_command(self, mock_download_all):
        """Test that main routes download-all-teams command correctly."""
        with patch('sys.argv', ['cli', 'download-all-teams', '--dry-run', '--force']):
            try:
                main()
            except SystemExit:
                pass

            mock_download_all.assert_called_once_with(dry_run=True, force=True)

    def test_handles_keyboard_interrupt(self):
        """Test that main handles keyboard interrupt gracefully."""
        with patch('sys.argv', ['cli', 'run']):
            with patch('src.cli.__main__.run_bot', side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 130

    def test_handles_generic_exception(self):
        """Test that main handles generic exceptions."""
        with patch('sys.argv', ['cli', 'run']):
            with patch('src.cli.__main__.run_bot', side_effect=Exception("Test error")):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1
