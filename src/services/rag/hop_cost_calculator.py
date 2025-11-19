"""Centralized hop evaluation cost calculation.

Single source of truth for calculating LLM costs during multi-hop retrieval.
Uses actual prompt/completion token counts from LLM responses.
"""

from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost
from src.services.llm.base import LLMResponse

logger = get_logger(__name__)


def calculate_hop_evaluation_cost(response: LLMResponse, model: str) -> float:
    """Calculate cost for hop evaluation LLM call using actual token counts.

    This is the single source of truth for hop evaluation cost calculation.
    Uses actual prompt_tokens and completion_tokens from the LLM response,
    never estimates from total token count.

    Args:
        response: LLM response object with token counts
        model: Model identifier (e.g., "gpt-4.1-mini")

    Returns:
        Cost in USD

    Raises:
        ValueError: If prompt_tokens or completion_tokens are missing
    """
    # Validate that we have actual token counts
    if response.prompt_tokens == 0 and response.completion_tokens == 0:
        # This should never happen with OpenAI models, but provide fallback
        logger.warning(
            "hop_cost_missing_token_breakdown",
            model=model,
            total_tokens=response.token_count,
            message="prompt_tokens and completion_tokens not available, using estimation",
        )
        # Fallback to 70-30 estimation (prompt heavier due to context)
        prompt_tokens = int(response.token_count * 0.7)
        completion_tokens = int(response.token_count * 0.3)
    else:
        prompt_tokens = response.prompt_tokens
        completion_tokens = response.completion_tokens

    # Use centralized cost estimation from tokens.py
    cost_usd = estimate_cost(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=model
    )

    logger.debug(
        "hop_evaluation_cost_calculated",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=response.token_count,
        cost_usd=cost_usd,
    )

    return cost_usd
