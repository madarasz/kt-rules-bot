"""CLI command to download and extract team rule PDFs.

Usage:
    python -m src.cli download-team https://assets.warhammer-community.com/.../teamrules.pdf
"""

import re
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from datetime import date, datetime

from src.lib.config import get_config
from src.lib.logging import get_logger
from src.lib.constants import PDF_EXTRACTION_PROVIDERS
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.base import ExtractionConfig, ExtractionRequest

logger = get_logger(__name__)


def extract_date_from_url(url: str) -> Optional[date]:
    """Extract date from Warhammer Community URL pattern.

    Args:
        url: PDF URL (e.g., containing 'eng_jul25_')

    Returns:
        Date object if found, None otherwise

    Examples:
        eng_jul25_ -> 2025-07-23 (last day of July 2025)
        eng_jan24_ -> 2024-01-31 (last day of January 2024)
    """
    # Pattern: eng_<month><year>_
    pattern = r'eng_([a-z]{3})(\d{2})_'
    match = re.search(pattern, url.lower())

    if not match:
        return None

    month_abbr = match.group(1)
    year_short = match.group(2)

    # Map month abbreviations
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    month = month_map.get(month_abbr)
    if not month:
        return None

    # Convert 2-digit year to 4-digit (assume 20xx)
    year = 2000 + int(year_short)

    # Use last day of month as default
    # Days in month (handle leap years for Feb)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        day = 29  # Leap year
    else:
        day = days_in_month[month - 1]

    try:
        return date(year, month, day)
    except ValueError:
        return None


def download_pdf(url: str) -> Tuple[bytes, int]:
    """Download PDF from URL.

    Args:
        url: PDF URL

    Returns:
        Tuple of (PDF bytes, file size in bytes)

    Raises:
        HTTPError: HTTP error occurred
        URLError: Network error occurred
        ValueError: Invalid URL or not a PDF
    """
    if not url.startswith('https://'):
        raise ValueError("URL must be HTTPS")

    if not url.lower().endswith('.pdf'):
        raise ValueError("URL must point to a PDF file")

    logger.info(f"Downloading PDF from {url}")

    # Create request with user agent
    headers = {
        'User-Agent': 'Kill-Team-Rules-Bot/1.0 (PDF Extraction Tool)'
    }
    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise HTTPError(url, response.status, f"HTTP {response.status}", response.headers, None)

            pdf_bytes = response.read()

            if len(pdf_bytes) == 0:
                raise ValueError("Downloaded PDF is empty")

            # Basic PDF validation (check magic bytes)
            if not pdf_bytes.startswith(b'%PDF'):
                raise ValueError("Downloaded file is not a valid PDF")

            logger.info(f"Downloaded {len(pdf_bytes)} bytes")
            return pdf_bytes, len(pdf_bytes)

    except HTTPError as e:
        logger.error(f"HTTP error downloading PDF: {e}")
        raise
    except URLError as e:
        logger.error(f"Network error downloading PDF: {e}")
        raise


def extract_team_name(markdown: str) -> str:
    """Extract team name from first H1 header in markdown.

    Args:
        markdown: Extracted markdown content

    Returns:
        Team name in lowercase (e.g., "pathfinders")

    Raises:
        ValueError: If no H1 header found
    """
    # Find first H1 header (# TEAM NAME)
    lines = markdown.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('# ') and not line.startswith('##'):
            # Extract team name (remove '# ' prefix)
            team_name = line[2:].strip()
            # Convert to lowercase and replace spaces with underscores
            team_name_clean = team_name.lower().replace(' ', '_')
            return team_name_clean

    raise ValueError("Could not find team name in extracted markdown (no H1 header found)")


def prepend_yaml_frontmatter(
    markdown: str,
    team_name: str,
    last_update_date: date,
) -> str:
    """Prepend YAML frontmatter to extracted markdown.

    Args:
        markdown: Extracted markdown content
        team_name: Team name (lowercase)
        last_update_date: Last update date

    Returns:
        Markdown with YAML frontmatter prepended
    """
    frontmatter = f"""---
source: "WC downloads"
last_update_date: {last_update_date.strftime('%Y-%m-%d')}
document_type: team-rules
section: {team_name}
---

"""
    return frontmatter + markdown


def validate_final_markdown(markdown: str, team_name: str) -> list[str]:
    """Validate final markdown with frontmatter.

    Args:
        markdown: Complete markdown with frontmatter
        team_name: Expected team name

    Returns:
        List of validation warnings (empty if all checks pass)
    """
    warnings = []

    # Check for YAML frontmatter
    if not markdown.startswith("---"):
        warnings.append("Missing YAML frontmatter")

    # Check for required YAML fields
    required_fields = ["source:", "last_update_date:", "document_type:", "section:"]
    for field in required_fields:
        if field not in markdown[:500]:
            warnings.append(f"Missing required field: {field.rstrip(':')}")

    # Check for team name in content
    if f"# {team_name.upper()}" not in markdown and f"# {team_name.replace('_', ' ').upper()}" not in markdown:
        warnings.append(f"Team name heading not found in markdown")

    # Check for key sections
    if "## " not in markdown:
        warnings.append("No H2 headers found (may indicate incomplete extraction)")

    return warnings


def calculate_cost(token_count: int, model: str) -> float:
    """Calculate estimated cost for LLM usage.

    Args:
        token_count: Total tokens used
        model: Model identifier

    Returns:
        Estimated cost in USD
    """
    # Gemini 2.5 Pro pricing (as of 2025)
    # Input: $1.25 per million tokens
    # Output: $5.00 per million tokens
    # Assume 80/20 split (input/output) as rough estimate for PDF extraction
    if 'gemini-2.5-pro' in model.lower():
        input_tokens = token_count * 0.8
        output_tokens = token_count * 0.2
        cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 5.00 / 1_000_000)
        return cost

    # Fallback for other models
    return token_count * 2.00 / 1_000_000


def download_team_internal(
    url: str,
    model: str = "gemini-2.5-pro",
    verbose: bool = True,
    team_name: Optional[str] = None,
    update_date: Optional[date] = None,
) -> dict:
    """Download and extract team rule PDF (internal function).

    Args:
        url: PDF URL
        model: LLM model to use for extraction
        verbose: If True, print progress messages
        team_name: Optional team name override (if None, extracts from markdown)
        update_date: Optional update date override (if None, extracts from URL or uses today)

    Returns:
        Dictionary with results:
        {
            "success": bool,
            "team_name": str,
            "output_file": str,
            "tokens": int,
            "latency_ms": int,
            "cost_usd": float,
            "error": Optional[str],
            "validation_warnings": list[str]
        }
    """
    config = get_config()

    # Validate Google API key
    if not config.google_api_key:
        logger.error("GOOGLE_API_KEY not configured")
        return {
            "success": False,
            "team_name": None,
            "output_file": None,
            "tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "error": "GOOGLE_API_KEY not configured in environment",
            "validation_warnings": [],
        }

    # Step 1: Download PDF
    if verbose:
        print(f"Downloading PDF from URL...")
    try:
        pdf_bytes, file_size = download_pdf(url)
        size_mb = file_size / (1024 * 1024)
        if verbose:
            print(f"✓ Downloaded {size_mb:.1f} MB")
    except Exception as e:
        logger.error(f"Failed to download PDF: {e}", exc_info=True)
        return {
            "success": False,
            "team_name": None,
            "output_file": None,
            "tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "error": f"Download failed: {e}",
            "validation_warnings": [],
        }

    # Step 2: Load extraction prompt
    try:
        prompt_file = Path(__file__).parent.parent.parent / "prompts" / "team-extraction-prompt.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Extraction prompt not found: {prompt_file}")

        extraction_prompt = prompt_file.read_text(encoding='utf-8')
        logger.info(f"Loaded extraction prompt from {prompt_file}")
    except Exception as e:
        logger.error(f"Failed to load extraction prompt: {e}", exc_info=True)
        return {
            "success": False,
            "team_name": None,
            "output_file": None,
            "tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "error": f"Failed to load extraction prompt: {e}",
            "validation_warnings": [],
        }

    # Step 3: Extract using Gemini
    if verbose:
        print(f"\nExtracting team rules using {model}...")
    try:
        # Create temporary file for PDF
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # Initialize Gemini adapter
        gemini = GeminiAdapter(api_key=config.google_api_key, model=model)

        # Create extraction request
        with open(temp_pdf_path, 'rb') as pdf_file:
            extraction_config = ExtractionConfig()
            request = ExtractionRequest(
                pdf_file=pdf_file,
                extraction_prompt=extraction_prompt,
                config=extraction_config,
            )

            # Extract (synchronous wrapper for async method)
            import asyncio
            response = asyncio.run(gemini.extract_pdf(request))

        # Clean up temp file
        Path(temp_pdf_path).unlink(missing_ok=True)

        if verbose:
            print(f"✓ Extraction complete")

        # Note: We skip validation warnings from the LLM adapter here because
        # they check for YAML frontmatter, which we add in the next step

    except Exception as e:
        logger.error(f"Failed to extract PDF: {e}", exc_info=True)
        return {
            "success": False,
            "team_name": None,
            "output_file": None,
            "tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "error": f"Extraction failed: {e}",
            "validation_warnings": [],
        }

    # Step 4: Determine team name
    if team_name is None:
        # Extract team name from markdown
        try:
            team_name = extract_team_name(response.markdown_content)
            if verbose:
                print(f"\nTeam name: {team_name.upper()}")
        except Exception as e:
            logger.error(f"Failed to extract team name: {e}", exc_info=True)
            return {
                "success": False,
                "team_name": None,
                "output_file": None,
                "tokens": response.token_count,
                "latency_ms": response.latency_ms,
                "cost_usd": calculate_cost(response.token_count, model),
                "error": f"Failed to extract team name: {e}",
                "validation_warnings": [],
            }
    else:
        # Use provided team name
        if verbose:
            print(f"\nTeam name: {team_name.upper()} (provided)")

    # Step 5: Add YAML frontmatter
    try:
        # Determine update date
        if update_date is None:
            # Extract date from URL or use current date
            last_update_date = extract_date_from_url(url) or date.today()
        else:
            # Use provided date
            last_update_date = update_date

        markdown_with_frontmatter = prepend_yaml_frontmatter(
            markdown=response.markdown_content,
            team_name=team_name,
            last_update_date=last_update_date,
        )
    except Exception as e:
        logger.error(f"Failed to add frontmatter: {e}", exc_info=True)
        return {
            "success": False,
            "team_name": team_name,
            "output_file": None,
            "tokens": response.token_count,
            "latency_ms": response.latency_ms,
            "cost_usd": calculate_cost(response.token_count, model),
            "error": f"Failed to add frontmatter: {e}",
            "validation_warnings": [],
        }

    # Step 5b: Validate final markdown
    validation_warnings = validate_final_markdown(markdown_with_frontmatter, team_name)
    if validation_warnings and verbose:
        print(f"\n⚠️  Validation warnings:")
        for warning in validation_warnings:
            print(f"   - {warning}")
        logger.warning(f"Validation warnings: {validation_warnings}")

    # Step 6: Save to file
    try:
        output_dir = Path("extracted-rules") / "team"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{team_name}.md"
        output_file.write_text(markdown_with_frontmatter, encoding='utf-8')

        if verbose:
            print(f"Saved to: {output_file}")
        logger.info(f"Saved extracted rules to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}", exc_info=True)
        return {
            "success": False,
            "team_name": team_name,
            "output_file": None,
            "tokens": response.token_count,
            "latency_ms": response.latency_ms,
            "cost_usd": calculate_cost(response.token_count, model),
            "error": f"Failed to save file: {e}",
            "validation_warnings": validation_warnings,
        }

    # Step 7: Calculate metrics
    cost = calculate_cost(response.token_count, model)

    if verbose:
        latency_s = response.latency_ms / 1000
        print(f"\nMetrics:")
        print(f"  Tokens: {response.token_count:,}")
        print(f"  Time: {latency_s:.1f}s")
        print(f"  Estimated cost: ${cost:.2f}")

    logger.info(
        f"Extraction metrics",
        extra={
            "team_name": team_name,
            "tokens": response.token_count,
            "latency_ms": response.latency_ms,
            "cost_usd": cost,
        },
    )

    # Return success result
    return {
        "success": True,
        "team_name": team_name,
        "output_file": str(output_file),
        "tokens": response.token_count,
        "latency_ms": response.latency_ms,
        "cost_usd": cost,
        "error": None,
        "validation_warnings": validation_warnings,
    }


def download_team(
    url: str,
    model: str = "gemini-2.5-pro",
    team_name: Optional[str] = None,
    update_date: Optional[str] = None,
) -> None:
    """Download and extract team rule PDF (CLI entry point).

    Args:
        url: PDF URL
        model: LLM model to use for extraction
        team_name: Optional team name override
        update_date: Optional update date override (YYYY-MM-DD format)
    """
    # Parse update_date string to date object
    parsed_date = None
    if update_date:
        try:
            parsed_date = datetime.strptime(update_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"❌ Invalid date format: {update_date}. Expected YYYY-MM-DD")
            sys.exit(1)

    result = download_team_internal(
        url,
        model,
        verbose=True,
        team_name=team_name,
        update_date=parsed_date,
    )

    if not result["success"]:
        print(f"❌ {result['error']}")
        sys.exit(1)


def main():
    """Main entry point for download_team CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and extract Kill Team rule PDFs"
    )
    parser.add_argument(
        "url",
        help="PDF URL (must be HTTPS)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        choices=PDF_EXTRACTION_PROVIDERS,
        help="LLM model to use for extraction (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--team-name",
        help="Team name override (default: extract from markdown)",
    )
    parser.add_argument(
        "--update-date",
        help="Update date override in YYYY-MM-DD format (default: extract from URL or use today)",
    )

    args = parser.parse_args()

    try:
        download_team(
            args.url,
            model=args.model,
            team_name=args.team_name,
            update_date=args.update_date,
        )
    except Exception as e:
        logger.error(f"download-team failed: {e}", exc_info=True)
        print(f"❌ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
