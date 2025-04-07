import os
import argparse
import ssl
import whisper
from datetime import datetime
import time
import subprocess
import json
from urllib.parse import parse_qs, urlparse


# Fix for SSL certificate issue on macOS
ssl._create_default_https_context = ssl._create_unverified_context


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze YouTube videos for investment insights.')
    parser.add_argument('url', type=str, help='YouTube video URL')
    parser.add_argument(
        '--output-dir', type=str, default='output',
        help='Directory to save output files')
    parser.add_argument(
        '--model', type=str, default='claude-3-7-sonnet-20250219',
        help='LLM model to use for analysis')
    return parser.parse_args()


def download_audio(url, output_dir):
    """Download audio from YouTube video using yt-dlp."""
    print(f"Downloading audio from: {url}")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Get the path to yt-dlp
    py_bin = "/Library/Frameworks/Python.framework/Versions/3.11/bin"
    yt_dlp_path = f"{py_bin}/yt-dlp"

    # Extract video ID from URL
    query = urlparse(url).query
    params = parse_qs(query)
    video_id = params.get('v', ['unknown_video'])[0]

    # Temporary file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{timestamp}_{video_id}.mp3"
    output_path = os.path.join(output_dir, output_filename)
    # Add retry mechanism
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # First, get video info to get the title
            info_command = [
                yt_dlp_path,
                '--dump-json',
                '--no-playlist',
                url
            ]
            result = subprocess.run(
                info_command,
                capture_output=True,
                text=True,
                check=True
            )

            # Parse the video information
            video_info = json.loads(result.stdout)
            video_title = video_info.get('title', f"YouTube_Video_{video_id}")
            print(f"Video title: {video_title}")

            # Download the audio with audio extraction
            command = [
                yt_dlp_path,
                '-f', 'bestaudio',
                '-x',
                '--audio-format', 'mp3',
                '-o', output_path,
                '--no-playlist',
                url
            ]

            subprocess.run(command, check=True)

            print(f"Audio downloaded to: {output_path}")
            return output_path, video_title
        except subprocess.CalledProcessError as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt+1} failed: {e}. Retrying...")
                # Add delay between retries
                time.sleep(2)
            else:
                if 'video_title' not in locals():
                    video_title = f"YouTube_Video_{video_id}"
                print(f"Failed to download after {max_retries} attempts: {e}")
                raise
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                msg = f"Attempt {attempt+1} failed: JSON parse error."
                print(f"{msg} Retrying...")
                time.sleep(2)
            else:
                video_title = f"YouTube_Video_{video_id}"
                print(f"Failed to get video info after {max_retries} attempts")
                raise


def transcribe_audio(audio_file):
    """Transcribe audio file using Whisper."""
    print("Transcribing audio...")

    # Load Whisper model
    model = whisper.load_model("base")

    # Transcribe audio
    result = model.transcribe(audio_file)
    transcript = result["text"]

    print(f"Transcription completed: {len(transcript)} characters")
    return transcript


def analyze_with_llm(transcript, video_title, model):
    """Analyze transcript using an LLM."""
    print(f"Analyzing transcript with {model}...")

    # Prompt for the LLM
    prompt = f"""
    The following is a transcript from a YouTube video titled "{video_title}".

    Transcript:
    {transcript}

    Please provide:
    1. A detailed summary of the main ideas with emphasis on explaining the macroeconomic behavior. I understand a lot of economic fundamentals but there are holes in my knowledge so I need some educating on how everything fits together. Explain like i'm 10y/o.
    2. Specific investment trades or opportunities suggested or implied
    3. Potential risks, downsides, and tradeoffs for each suggested trade
    4. Any limitations or biases in the analysis presented in the video

    Format your response in clear sections with headings.
    """

    # Send request to the LLM
    if "claude" in model.lower():
        # Use Anthropic API for Claude models
        try:
            from anthropic import Anthropic
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not set in environment")

            anthropic = Anthropic(api_key=anthropic_api_key)
            response = anthropic.messages.create(
                model=model,
                max_tokens=4000,
                system="You are a helpful financial analysis assistant that "
                       "specializes in extracting investment insights.",
                messages=[{"role": "user", "content": prompt}]
            )
            analysis = response.content[0].text
        except Exception as e:
            print(f"Error using Anthropic API: {str(e)}")
            raise
    else:
        # Use OpenAI API for other models
        try:
            from openai import OpenAI
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")

            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful "
                     "financial analysis assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000
            )
            analysis = response.choices[0].message.content
        except Exception as e:
            print(f"Error using OpenAI API: {str(e)}")
            raise

    print("Analysis completed")
    return analysis


def save_outputs(transcript, analysis, video_title, output_dir):
    """Save transcript and analysis to files."""
    # Create timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize video title for filename
    safe_title = "".join([c if c.isalnum() or c in " _-" else "_"
                         for c in video_title]).strip()
    safe_title = safe_title[:50]  # Truncate long titles

    # Save transcript
    transcript_filename = os.path.join(
        output_dir, f"{timestamp}_{safe_title}_transcript.txt")
    with open(transcript_filename, "w") as f:
        f.write(transcript)

    # Save analysis
    analysis_filename = os.path.join(
        output_dir, f"{timestamp}_{safe_title}_analysis.md")
    with open(analysis_filename, "w") as f:
        f.write(f"# Analysis of: {video_title}\n\n")
        f.write(analysis)

    print(f"Transcript saved to: {transcript_filename}")
    print(f"Analysis saved to: {analysis_filename}")

    return transcript_filename, analysis_filename


def main():
    """Main function to run the analysis pipeline."""
    # Parse arguments
    args = parse_arguments()

    # Download audio
    audio_file, video_title = download_audio(args.url, args.output_dir)

    # Transcribe audio
    transcript = transcribe_audio(audio_file)

    # Analyze transcript
    analysis = analyze_with_llm(transcript, video_title, args.model)

    # Save outputs
    transcript_file, analysis_file = save_outputs(
        transcript, analysis, video_title, args.output_dir)

    print("\nAnalysis completed successfully!")
    print(f"Video: {video_title}")
    print(f"Transcript: {transcript_file}")
    print(f"Analysis: {analysis_file}")


if __name__ == "__main__":
    main()
