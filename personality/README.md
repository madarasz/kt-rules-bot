# Bot Personality System

The bot's personality is fully configurable through YAML descriptor files. This allows you to easily switch between different bot personalities or create new ones.

## Configuration

Set the `PERSONALITY` environment variable in `config/.env`:

```bash
PERSONALITY=necron
```

## Personality Structure

Each personality must be in its own directory under `personality/` with the following structure:

```
personality/
  your-personality-name/
    personality.yaml          # Required: Configuration descriptor
    personality.md            # Required: Personality description for system prompt
    acknowledgements.txt      # Required: Random acknowledgement messages (one per line)
    disclaimers.txt           # Required: Random disclaimer messages (one per line)
```

## personality.yaml Format

```yaml
# Path to the full personality description (inserted into system prompt)
description_file: personality/your-personality-name/personality.md

# Example phrase for [PERSONALITY SHORT ANSWER] placeholder in system prompt
short_answer_example: "Your short answer phrase here."

# Example phrase for [PERSONALITY AFTERWORD] placeholder in system prompt
afterword_example: "Your afterword phrase here."

# Discord bot acknowledgement messages file
acknowledgements_file: personality/your-personality-name/acknowledgements.txt

# Discord bot disclaimer messages file
disclaimers_file: personality/your-personality-name/disclaimers.txt
```

## How It Works

1. **System Prompt**: The base template at `prompts/rule-helper-prompt.md` contains three placeholders:
   - `[PERSONALITY DESCRIPTION]` - Replaced with contents of your `personality.md`
   - `[PERSONALITY SHORT ANSWER]` - Replaced with `short_answer_example`
   - `[PERSONALITY AFTERWORD]` - Replaced with `afterword_example`

2. **Discord Messages**: Random acknowledgements and disclaimers are selected from your text files when the bot processes queries.

## Creating a New Personality

1. Create a new directory: `personality/my-personality/`

2. Create `personality.yaml` with your configuration

3. Create `personality.md` with your bot's personality description:
   ```markdown
   ## Persona description

   Your personality backstory and style guide here...
   ```

4. Create `acknowledgements.txt` (one message per line):
   ```
   Processing your query...
   Analyzing rules...
   Consulting the rulebook...
   ```

5. Create `disclaimers.txt` (one message per line):
   ```
   This is an automated interpretation. Consult official rules.
   Results may vary. Check with your TO.
   ```

6. Update your `.env` file:
   ```bash
   PERSONALITY=my-personality
   ```

7. Restart the bot

## Example: Necron Personality

See `personality/necron/` for a complete example of:
- An ancient, condescending AI personality
- Cryptek-themed acknowledgements with glitch effects
- Technical, clinical disclaimers

## Validation

The system validates on startup that:
- The personality directory exists
- `personality.yaml` exists and is valid
- All referenced files in the YAML exist (warnings logged if missing)

## Tips

- Keep `short_answer_example` and `afterword_example` concise (1-2 sentences)
- Use the personality to add flavor, but keep rule explanations clear
- Test your personality by running: `python -m src.cli query "test question"`
- The personality description should focus on tone and style, not rule interpretation
