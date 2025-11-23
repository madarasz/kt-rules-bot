#!/bin/bash
# Fix Python cache issues after Pydantic migration
# Run this if you're seeing API errors despite having latest code

set -e

echo "=================================================="
echo "Fixing Python Cache After Pydantic Migration"
echo "=================================================="

# Step 1: Clear Python cache
echo ""
echo "Step 1: Clearing Python bytecode cache..."
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true
rm -rf .pytest_cache/ 2>/dev/null || true
echo "✓ Cache cleared"

# Step 2: Verify git commit
echo ""
echo "Step 2: Verifying git commit..."
CURRENT_COMMIT=$(git log --oneline -1 | cut -d' ' -f1)
echo "Current commit: $CURRENT_COMMIT"

# Check if we have the Gemini fix commit (47cb01e or later)
if git log --oneline | grep -q "47cb01e"; then
    echo "✓ Found commit 47cb01e (Gemini fix)"
else
    echo "⚠️  Warning: Commit 47cb01e not found. You may need to pull latest changes."
fi

# Step 3: Check/reinstall dependencies (optional)
echo ""
echo "Step 3: Checking dependencies..."
read -p "Reinstall dependencies? This will upgrade all packages (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install -r requirements.txt --upgrade --force-reinstall
    echo "✓ Dependencies reinstalled"
else
    echo "⊘ Skipped dependency reinstall"
fi

# Step 4: Verify SDK versions
echo ""
echo "Step 4: Verifying SDK versions..."
python3 << 'EOF'
try:
    import anthropic
    print(f"✓ anthropic: {anthropic.__version__} (required: >=0.74.1)")
    if tuple(map(int, anthropic.__version__.split('.'))) < (0, 74, 1):
        print("  ⚠️  Version too old! Run: pip install anthropic>=0.74.1 --upgrade")
except ImportError:
    print("✗ anthropic not installed")

try:
    import openai
    print(f"✓ openai: {openai.__version__} (required: >=2.8.1)")
    version_parts = openai.__version__.split('.')
    major = int(version_parts[0])
    minor = int(version_parts[1]) if len(version_parts) > 1 else 0
    if major < 2 or (major == 2 and minor < 8):
        print("  ⚠️  Version too old! Run: pip install openai>=2.8.1 --upgrade")
except ImportError:
    print("✗ openai not installed")

try:
    from google import genai
    print("✓ google-genai: installed")
except ImportError:
    print("✗ google-genai not installed")
EOF

# Step 5: Run diagnostic
echo ""
echo "Step 5: Running diagnostic..."
if [ -f "scripts/verify_implementation.py" ]; then
    python3 scripts/verify_implementation.py
else
    echo "⚠️  Diagnostic script not found at scripts/verify_implementation.py"
fi

# Summary
echo ""
echo "=================================================="
echo "Next Steps:"
echo "=================================================="
echo ""
echo "1. Run unit tests:"
echo "   pytest tests/unit/test_llm_adapters.py -v"
echo ""
echo "2. Run a single quality test:"
echo "   python -m src.cli quality-test --model claude-4.5-sonnet --test eliminator-concealed-counteract"
echo ""
echo "3. If errors persist, see: docs/TROUBLESHOOTING-PYDANTIC-MIGRATION.md"
echo ""
