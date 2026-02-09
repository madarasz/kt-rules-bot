#!/usr/bin/env python3
"""Diagnostic script to verify Pydantic implementation is loaded correctly."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def verify_gemini():
    """Verify Gemini implementation."""
    print("\n=== Gemini Adapter ===")
    try:
        import inspect

        from src.services.llm.gemini import GeminiAdapter

        # Get the source code of the generate method
        source = inspect.getsource(GeminiAdapter.generate)

        # Check for correct implementation
        if "response_schema=pydantic_model" in source:
            print("✅ Gemini: Passing Pydantic model directly (CORRECT)")
        elif "response_schema=pydantic_model.model_json_schema()" in source:
            print("❌ Gemini: Passing JSON schema (OLD - WRONG)")
        else:
            print("⚠️  Gemini: Cannot determine implementation")

        # Check imports
        if "types.GenerateContentConfig" in source:
            print("✅ Gemini: Using types.GenerateContentConfig")
        else:
            print("⚠️  Gemini: Not using types.GenerateContentConfig")

    except Exception as e:
        print(f"❌ Error checking Gemini: {e}")


def verify_claude():
    """Verify Claude implementation."""
    print("\n=== Claude Adapter ===")
    try:
        import inspect

        from src.services.llm.claude import ClaudeAdapter

        # Get the __init__ source
        source = inspect.getsource(ClaudeAdapter.__init__)

        # Check for correct beta header
        if "structured-outputs-2025-11-13" in source:
            print("✅ Claude: Using correct beta header (2025-11-13)")
        elif "structured-outputs-2025-09-17" in source:
            print("❌ Claude: Using OLD beta header (2025-09-17)")
        else:
            print("⚠️  Claude: Cannot find beta header")

        # Check generate method
        gen_source = inspect.getsource(ClaudeAdapter.generate)
        if "beta.messages.parse" in gen_source:
            print("✅ Claude: Using beta.messages.parse")
        else:
            print("❌ Claude: Not using beta.messages.parse")

    except Exception as e:
        print(f"❌ Error checking Claude: {e}")


def verify_schemas():
    """Verify schema definitions."""
    print("\n=== Schemas ===")
    try:
        import inspect

        from src.services.llm.schemas import HopEvaluation

        # Check HopEvaluation.missing_query field
        source = inspect.getsource(HopEvaluation)

        if "missing_query: str | None" in source or "missing_query: Optional[str]" in source:
            print("✅ HopEvaluation.missing_query: Nullable (CORRECT)")
        elif "missing_query: str" in source:
            print("❌ HopEvaluation.missing_query: Not nullable (WRONG)")
        else:
            print("⚠️  HopEvaluation.missing_query: Cannot determine")

        # Check if schema file exists at correct location
        from pathlib import Path
        schema_path = Path(__file__).parent.parent / "src" / "services" / "llm" / "schemas.py"
        if schema_path.exists():
            print(f"✅ schemas.py exists at: {schema_path}")
        else:
            print(f"❌ schemas.py NOT found at: {schema_path}")

    except Exception as e:
        print(f"❌ Error checking schemas: {e}")


def verify_sdk_versions():
    """Verify SDK versions."""
    print("\n=== SDK Versions ===")
    try:
        import anthropic
        print(f"anthropic: {anthropic.__version__} (required: >=0.74.1)")

        import openai
        print(f"openai: {openai.__version__} (required: >=2.8.1)")

        from google import genai
        print("google-genai: installed")

    except ImportError as e:
        print(f"❌ Import error: {e}")


def main():
    """Run all verifications."""
    print("=" * 60)
    print("Pydantic Implementation Verification")
    print("=" * 60)

    verify_sdk_versions()
    verify_schemas()
    verify_claude()
    verify_gemini()

    print("\n" + "=" * 60)
    print("If you see ❌ or ⚠️  above, run:")
    print("  1. find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null")
    print("  2. find . -name '*.pyc' -delete")
    print("  3. pip install -r requirements.txt --upgrade --force-reinstall")
    print("  4. python scripts/verify_implementation.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
