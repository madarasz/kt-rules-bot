"""Error message builder for user-friendly error responses."""


class ErrorMessageBuilder:
    """Builds user-friendly error messages from exceptions."""

    @staticmethod
    def build_error_message(error: Exception) -> str:
        """Build user-friendly error message from exception.

        Args:
            error: Exception instance

        Returns:
            User-friendly error message
        """
        error_str = str(error).lower()

        # Check for credit balance issues
        if ErrorMessageBuilder._is_credit_error(error_str):
            return "💰 API credit balance is insufficient"

        # Check for invalid API key errors
        if ErrorMessageBuilder._is_auth_error(error_str):
            return "🔑 API key is invalid or expired"

        # Check for rate limit errors
        if ErrorMessageBuilder._is_rate_limit_error(error_str):
            return "⏳ API rate limit exceeded. Please try again in a moment."

        # Check for content filter/safety errors
        if ErrorMessageBuilder._is_content_filter_error(error_str):
            return "⚠️ Your query was blocked by content safety filters. Please rephrase your question."

        # Check for overloaded server errors
        if ErrorMessageBuilder._is_overload_error(error_str):
            return "🚧 The server is currently overloaded. Please try again later."

        # Generic error fallback
        return "❌ An error occurred while processing your request. Please try again in a moment."

    @staticmethod
    def _is_credit_error(error_str: str) -> bool:
        """Check if error is related to credit balance."""
        keywords = ["credit balance", "insufficient funds", "insufficient quota", "quota"]
        return any(keyword in error_str for keyword in keywords)

    @staticmethod
    def _is_auth_error(error_str: str) -> bool:
        """Check if error is related to authentication."""
        keywords = ["invalid api key", "authentication", "unauthorized"]
        return any(keyword in error_str for keyword in keywords)

    @staticmethod
    def _is_rate_limit_error(error_str: str) -> bool:
        """Check if error is related to rate limiting."""
        keywords = ["rate limit", "too many requests"]
        return any(keyword in error_str for keyword in keywords)

    @staticmethod
    def _is_content_filter_error(error_str: str) -> bool:
        """Check if error is related to content filtering."""
        return "content" in error_str and any(
            keyword in error_str for keyword in ["filter", "policy", "safety"]
        )

    @staticmethod
    def _is_overload_error(error_str: str) -> bool:
        """Check if error is related to overloaded server."""
        keywords = ["overload", "unavailable", "temporarily down", "503"]
        return any(keyword in error_str for keyword in keywords)
