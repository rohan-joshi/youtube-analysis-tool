# YouTube Video Analysis Tool

A Python tool that downloads, transcribes, and analyzes YouTube videos to extract key insights, particularly focused on investment and economic content.

## Features

- Downloads audio from YouTube videos
- Transcribes audio using OpenAI's Whisper model
- Analyzes transcripts using Large Language Models (Claude or OpenAI)
- Saves transcripts and analysis as text/markdown files

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/rohan-joshi/youtube-analysis-tool.git
   cd youtube-analysis-tool
   ```

2. Install dependencies:
   ```
   pip install pytube whisper openai anthropic
   ```

3. Required external dependencies:
   - [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube video downloading

4. Set up API keys as environment variables:
   ```
   export ANTHROPIC_API_KEY=your_anthropic_api_key
   export OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

Basic usage:
```
python youtube_analysis.py [YouTube URL] --output-dir [DIR] --model [MODEL]
```

Examples:
```
# Using Claude
python youtube_analysis.py https://www.youtube.com/watch?v=EXAMPLE --model claude-3-7-sonnet-20250219

# Using OpenAI
python youtube_analysis.py https://www.youtube.com/watch?v=EXAMPLE --model gpt-4
```

## Customizing Analysis

You can customize how the transcript is analyzed by editing the `analyze_with_llm()` function in the `youtube_analysis.py` file.

The current analysis provides:
1. A summary of main ideas with emphasis on explaining macroeconomic concepts
2. Specific investment opportunities suggested in the video
3. Potential risks and downsides for each suggestion
4. Limitations or biases in the analysis

To modify the analysis:

1. Edit the prompt template in the `analyze_with_llm()` function (around line 129)
2. Adjust the system message for the LLM to focus on specific areas of interest
3. Change the output format to suit your needs

## Output Files

The tool generates two files for each video:
- `{timestamp}_{video_title}_transcript.txt`: Raw transcript of the video
- `{timestamp}_{video_title}_analysis.md`: Analysis of the video content

## License

MIT License

Copyright (c) 2025 Rohan Joshi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.