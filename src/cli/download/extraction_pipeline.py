"""PDF extraction pipeline orchestration.

Orchestrates the complete flow of downloading, extracting, and saving team PDFs.
Extracted from download_team.py to follow Single Responsibility Principle.
"""

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, List

from src.cli.download.http_client import HTTPClient
from src.cli.download.team_name_extractor import TeamNameExtractor
from src.cli.download.frontmatter_generator import FrontmatterGenerator
from src.cli.download.markdown_validator import MarkdownValidator
from src.lib.logging import get_logger
from src.lib.tokens import estimate_cost
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.base import ExtractionConfig, ExtractionRequest

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    """Result of PDF extraction pipeline.

    Attributes:
        success: Whether extraction succeeded
        team_name: Extracted team name
        output_file: Path to saved markdown file
        tokens: Total tokens used
        latency_ms: Total latency in milliseconds
        cost_usd: Estimated cost in USD
        error: Error message if failed
        validation_warnings: List of validation warnings
    """

    success: bool
    team_name: Optional[str]
    output_file: Optional[str]
    tokens: int
    latency_ms: int
    cost_usd: float
    error: Optional[str]
    validation_warnings: List[str]


class ExtractionPipeline:
    """Pipeline for extracting team rules from PDFs.

    Orchestrates the complete extraction workflow:
    1. Download PDF
    2. Extract using LLM
    3. Extract team name
    4. Add frontmatter
    5. Validate
    6. Save to file
    """

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        output_dir: Path = None,
    ):
        """Initialize extraction pipeline.

        Args:
            model: LLM model to use for extraction
            output_dir: Output directory for markdown files
        """
        self.model = model
        self.output_dir = output_dir or Path("extracted-rules") / "team"

    def extract_from_url(
        self,
        url: str,
        team_name: Optional[str] = None,
        update_date: Optional[date] = None,
        verbose: bool = True,
    ) -> ExtractionResult:
        """Extract team rules from PDF URL.

        Args:
            url: PDF URL
            team_name: Optional team name override
            update_date: Optional update date override
            verbose: Whether to print progress messages

        Returns:
            ExtractionResult with extraction details
        """
        # Step 1: Download PDF
        if verbose:
            print(f"Downloading PDF from URL...")

        try:
            pdf_bytes, file_size = HTTPClient.download_pdf(url)
            size_mb = file_size / (1024 * 1024)
            if verbose:
                print(f"✓ Downloaded {size_mb:.1f} MB")
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                team_name=None,
                output_file=None,
                tokens=0,
                latency_ms=0,
                cost_usd=0.0,
                error=f"Download failed: {e}",
                validation_warnings=[],
            )

        # Step 2: Load extraction prompt
        try:
            prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "team-extraction-prompt.md"
            if not prompt_file.exists():
                raise FileNotFoundError(f"Extraction prompt not found: {prompt_file}")

            extraction_prompt = prompt_file.read_text(encoding='utf-8')
            logger.info(f"Loaded extraction prompt from {prompt_file}")
        except Exception as e:
            logger.error(f"Failed to load extraction prompt: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                team_name=None,
                output_file=None,
                tokens=0,
                latency_ms=0,
                cost_usd=0.0,
                error=f"Failed to load extraction prompt: {e}",
                validation_warnings=[],
            )

        # Step 3: Extract using LLM
        if verbose:
            print(f"\nExtracting team rules using {self.model}...")

        try:
            llm_provider = LLMProviderFactory.create(provider_name=self.model)

            if llm_provider is None:
                error_msg = f"API key not configured for {self.model}. Please check your .env file."
                logger.error(error_msg)
                return ExtractionResult(
                    success=False,
                    team_name=None,
                    output_file=None,
                    tokens=0,
                    latency_ms=0,
                    cost_usd=0.0,
                    error=error_msg,
                    validation_warnings=[],
                )

            # Create temporary file for PDF
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf.write(pdf_bytes)
                temp_pdf_path = temp_pdf.name

            # Create extraction request
            with open(temp_pdf_path, 'rb') as pdf_file:
                extraction_config = ExtractionConfig()
                request = ExtractionRequest(
                    pdf_file=pdf_file,
                    extraction_prompt=extraction_prompt,
                    config=extraction_config,
                )

                # Extract (synchronous wrapper for async method)
                response = asyncio.run(llm_provider.extract_pdf(request))

            # Clean up temp file
            Path(temp_pdf_path).unlink(missing_ok=True)

            if verbose:
                print(f"✓ Extraction complete")

        except Exception as e:
            logger.error(f"Failed to extract PDF: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                team_name=None,
                output_file=None,
                tokens=0,
                latency_ms=0,
                cost_usd=0.0,
                error=f"Extraction failed: {e}",
                validation_warnings=[],
            )

        # Step 4: Determine team name
        if team_name is None:
            try:
                team_name = TeamNameExtractor.extract_from_markdown(response.markdown_content)
                if verbose:
                    print(f"\nTeam name: {team_name.upper()}")
            except Exception as e:
                logger.error(f"Failed to extract team name: {e}", exc_info=True)
                return ExtractionResult(
                    success=False,
                    team_name=None,
                    output_file=None,
                    tokens=response.token_count,
                    latency_ms=response.latency_ms,
                    cost_usd=estimate_cost(response.prompt_tokens, response.completion_tokens, self.model),
                    error=f"Failed to extract team name: {e}",
                    validation_warnings=[],
                )
        else:
            if verbose:
                print(f"\nTeam name: {team_name.upper()} (provided)")

        # Step 5: Add YAML frontmatter
        try:
            # Determine update date
            if update_date is None:
                from src.cli.download_team import extract_date_from_url
                last_update_date = extract_date_from_url(url) or date.today()
            else:
                last_update_date = update_date

            markdown_with_frontmatter = FrontmatterGenerator.prepend_frontmatter(
                markdown=response.markdown_content,
                team_name=team_name,
                last_update_date=last_update_date,
            )
        except Exception as e:
            logger.error(f"Failed to add frontmatter: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                team_name=team_name,
                output_file=None,
                tokens=response.token_count,
                latency_ms=response.latency_ms,
                cost_usd=estimate_cost(response.prompt_tokens, response.completion_tokens, self.model),
                error=f"Failed to add frontmatter: {e}",
                validation_warnings=[],
            )

        # Step 6: Validate final markdown
        validation_warnings = MarkdownValidator.validate_frontmatter_markdown(
            markdown_with_frontmatter,
            team_name
        )
        if validation_warnings and verbose:
            print(f"\n⚠️  Validation warnings:")
            for warning in validation_warnings:
                print(f"   - {warning}")
            logger.warning(f"Validation warnings: {validation_warnings}")

        # Step 7: Save to file
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_file = self.output_dir / f"{team_name}.md"
            output_file.write_text(markdown_with_frontmatter, encoding='utf-8')

            if verbose:
                print(f"Saved to: {output_file}")
            logger.info(f"Saved extracted rules to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save file: {e}", exc_info=True)
            return ExtractionResult(
                success=False,
                team_name=team_name,
                output_file=None,
                tokens=response.token_count,
                latency_ms=response.latency_ms,
                cost_usd=estimate_cost(response.prompt_tokens, response.completion_tokens, self.model),
                error=f"Failed to save file: {e}",
                validation_warnings=validation_warnings,
            )

        # Step 8: Calculate final metrics
        cost = estimate_cost(response.prompt_tokens, response.completion_tokens, self.model)

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

        return ExtractionResult(
            success=True,
            team_name=team_name,
            output_file=str(output_file),
            tokens=response.token_count,
            latency_ms=response.latency_ms,
            cost_usd=cost,
            error=None,
            validation_warnings=validation_warnings,
        )
