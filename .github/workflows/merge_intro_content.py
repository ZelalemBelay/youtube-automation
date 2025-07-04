import subprocess
import shutil
import json

def get_video_duration(video_path):
    """Gets the duration of a video file in seconds using ffprobe."""
    if not shutil.which("ffprobe"):
        print("❌ Error: ffprobe is not installed or not in your system's PATH.")
        print("Please install ffmpeg (which includes ffprobe) to run this script.")
        return None

    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"❌ Error getting duration for {video_path}: {e}")
        return None


def merge_videos_with_transition(intro_path, content_path, output_path, transition_type="fade", transition_duration=1):
    """
    Merges an intro with a content video, adding a visual transition and
    joining their respective audio tracks.
    """
    if not shutil.which("ffmpeg"):
        print("❌ Error: ffmpeg is not installed or not in your system's PATH.")
        return

    # 1. Get the exact duration of the intro video
    print(f"🔎 Analyzing intro video: {intro_path}...")
    intro_duration = get_video_duration(intro_path)
    if intro_duration is None:
        return

    if intro_duration <= transition_duration:
        print(f"❌ Error: Intro duration ({intro_duration}s) must be longer than transition duration ({transition_duration}s).")
        return

    print(f"✅ Intro duration detected: {intro_duration:.2f} seconds.")

    # 2. Calculate the offset for the transition to start
    xfade_offset = intro_duration - transition_duration

    # 3. Construct the ffmpeg command
    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-i", intro_path,
        "-i", content_path,
        "-filter_complex",
        (
            # --- VIDEO CHAIN ---
            # Conform both video streams to the same frame rate (30fps) and pixel format
            "[0:v]fps=30,format=yuv420p[v0];"
            "[1:v]fps=30,format=yuv420p[v1];"

            # Apply the crossfade transition to the conformed video streams
            f"[v0][v1]xfade=transition={transition_type}:duration={transition_duration}:offset={xfade_offset}[outv];"

            # --- AUDIO CHAIN ---
            # Conform both audio streams to a standard sample rate (44.1kHz) and channel layout (stereo)
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
            "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"

            # Concatenate the conformed audio streams
            "[a0][a1]concat=n=2:v=0:a=1[outa]"
        ),
        "-map", "[outv]",  # Map the final video stream
        "-map", "[outa]",  # Map the final audio stream
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]

    # 4. Execute the command
    print(f"🎬 Starting merge with a {transition_duration}s '{transition_type}' transition and combined audio...")
    try:
        subprocess.run(ffmpeg_command, check=True)
        print(f"✅ Success! Video with transition and intro audio saved to '{output_path}'")
    except subprocess.CalledProcessError as e:
        print("❌ An error occurred during the ffmpeg merge process.")
        print(f"Return code: {e.returncode}")
    except FileNotFoundError:
        print(f"❌ Error: Could not find one of the input files.")
        print(f"  Checked for intro: '{intro_path}'")
        print(f"  Checked for content: '{content_path}'")


if __name__ == "__main__":
    # --- Configuration ---
    INTRO_VIDEO_PATH = "assets/intro.mp4"
    CONTENT_VIDEO_PATH = "final_content.mp4"
    FINAL_OUTPUT_PATH = "final_news.mp4"

    # --- Transition Options ---
    # Common types: fade, wipeleft, wiperight, slideup, slidedown, circleopen
    TRANSITION = "fade"
    TRANSITION_SECONDS = 1

    merge_videos_with_transition(
        INTRO_VIDEO_PATH,
        CONTENT_VIDEO_PATH,
        FINAL_OUTPUT_PATH,
        transition_type=TRANSITION,
        transition_duration=TRANSITION_SECONDS
    )