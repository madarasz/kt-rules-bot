"""Parameter parsing utilities for test commands.

Extracted from rag_test_sweep.py to reduce code duplication.
"""

from typing import List, Dict, Any

from src.lib.logging import get_logger

logger = get_logger(__name__)


class ParameterParser:
    """Parses parameter values for test sweeps.

    Provides consistent parameter parsing for RAG test commands.
    """

    # Define parameter types
    INTEGER_PARAMS = {'max_chunks', 'rrf_k', 'chunk_header_level'}
    FLOAT_PARAMS = {'min_relevance', 'bm25_k1', 'bm25_b', 'bm25_weight'}
    STRING_PARAMS = {'embedding_model'}

    @staticmethod
    def parse_parameter_values(param_name: str, values_str: str) -> List:
        """Parse comma-separated parameter values.

        Args:
            param_name: Name of parameter
            values_str: Comma-separated values string

        Returns:
            List of parsed values (int, float, or str depending on parameter)

        Raises:
            ValueError: If values cannot be parsed or parameter is unknown
        """
        values_list = [v.strip() for v in values_str.split(',')]

        # Determine type based on parameter name
        if param_name in ParameterParser.INTEGER_PARAMS:
            # Integer parameters
            try:
                return [int(v) for v in values_list]
            except ValueError as e:
                raise ValueError(f"Failed to parse {param_name} values as integers: {e}")

        elif param_name in ParameterParser.FLOAT_PARAMS:
            # Float parameters
            try:
                return [float(v) for v in values_list]
            except ValueError as e:
                raise ValueError(f"Failed to parse {param_name} values as floats: {e}")

        elif param_name in ParameterParser.STRING_PARAMS:
            # String parameters
            return values_list

        else:
            raise ValueError(f"Unknown parameter: {param_name}")

    @staticmethod
    def parse_grid_params(
        max_chunks: str = None,
        min_relevance: str = None,
        rrf_k: str = None,
        bm25_k1: str = None,
        bm25_b: str = None,
        bm25_weight: str = None,
        embedding_model: str = None,
        chunk_header_level: str = None,
    ) -> Dict[str, List]:
        """Parse grid search parameters.

        Args:
            max_chunks: Comma-separated max_chunks values
            min_relevance: Comma-separated min_relevance values
            rrf_k: Comma-separated rrf_k values
            bm25_k1: Comma-separated bm25_k1 values
            bm25_b: Comma-separated bm25_b values
            bm25_weight: Comma-separated bm25_weight values
            embedding_model: Comma-separated embedding_model values
            chunk_header_level: Comma-separated chunk_header_level values

        Returns:
            Dictionary mapping parameter names to value lists

        Raises:
            ValueError: If values cannot be parsed
        """
        param_grid = {}

        if max_chunks:
            try:
                param_grid['max_chunks'] = [int(v.strip()) for v in max_chunks.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse max_chunks: {e}")

        if min_relevance:
            try:
                param_grid['min_relevance'] = [float(v.strip()) for v in min_relevance.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse min_relevance: {e}")

        if rrf_k:
            try:
                param_grid['rrf_k'] = [int(v.strip()) for v in rrf_k.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse rrf_k: {e}")

        if bm25_k1:
            try:
                param_grid['bm25_k1'] = [float(v.strip()) for v in bm25_k1.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse bm25_k1: {e}")

        if bm25_b:
            try:
                param_grid['bm25_b'] = [float(v.strip()) for v in bm25_b.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse bm25_b: {e}")

        if bm25_weight:
            try:
                param_grid['bm25_weight'] = [float(v.strip()) for v in bm25_weight.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse bm25_weight: {e}")

        if embedding_model:
            param_grid['embedding_model'] = [v.strip() for v in embedding_model.split(',')]

        if chunk_header_level:
            try:
                param_grid['chunk_header_level'] = [int(v.strip()) for v in chunk_header_level.split(',')]
            except ValueError as e:
                raise ValueError(f"Failed to parse chunk_header_level: {e}")

        return param_grid

    @staticmethod
    def validate_parameter_name(param_name: str) -> bool:
        """Validate that parameter name is recognized.

        Args:
            param_name: Parameter name to validate

        Returns:
            True if valid, False otherwise
        """
        return param_name in (
            ParameterParser.INTEGER_PARAMS |
            ParameterParser.FLOAT_PARAMS |
            ParameterParser.STRING_PARAMS
        )

    @staticmethod
    def get_all_parameter_names() -> List[str]:
        """Get list of all recognized parameter names.

        Returns:
            List of parameter names
        """
        return sorted(
            ParameterParser.INTEGER_PARAMS |
            ParameterParser.FLOAT_PARAMS |
            ParameterParser.STRING_PARAMS
        )
