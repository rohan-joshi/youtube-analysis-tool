# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands
- Run the script: `python youtube_analysis.py [YouTube URL] --output-dir [DIR] --model [MODEL]`
- Install dependencies: `pip install pytube whisper openai anthropic`
- Linting: `flake8 *.py`
- Type checking: `mypy *.py`

## Code Style Guidelines
- Imports: Standard library first, then third-party, then local modules
- Formatting: Follow PEP 8 (4 spaces for indentation)
- Types: Use docstrings for function descriptions and type documentation
- Naming: Use snake_case for variables/functions, CamelCase for classes
- Error handling: Use try/except with specific exception types
- API keys: Never hardcode API keys in the code (use environment variables)
- Comments: Use docstrings for functions and meaningful inline comments
- Function size: Keep functions focused and reasonably sized
- Variable names: Use descriptive names that indicate purpose