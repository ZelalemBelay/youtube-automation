import subprocess
import os

text = "Funny video man falling from first floor building holding a microwave"
output_dir = "video_output"
output_path = os.path.join(output_dir, "generated_video.mp4")

os.makedirs(output_dir, exist_ok=True)

# Generate a black background video with white text in the center
ffmpeg_cmd = [
    "ffmpeg",
    "-f", "lavfi",
    "-i", "color=c=black:s=1280x720:d=10",
    "-vf", f"drawtext=text='{text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
    "-c:v", "libx264",
    "-t", "10",
    "-y",
    output_path
]

subprocess.run(ffmpeg_cmd, check=True)
