import os
import subprocess
from gtts import gTTS

# Prepare output directory
os.makedirs("video_output", exist_ok=True)

# Define conversation
dialogues = [
    {"speaker": "A", "text": "Hey, did you hear about the guy who fell off the first floor holding a microwave?"},
    {"speaker": "B", "text": "Yeah, I saw it. Funniest thing I’ve seen all week!"},
    {"speaker": "A", "text": "I still can't believe he saved the microwave."}
]

# Generate audio clips and calculate durations
total_duration = 0
segments = []
for i, line in enumerate(dialogues):
    text = line["text"]
    tts = gTTS(text=text)
    audio_path = f"video_output/line_{i}.mp3"
    tts.save(audio_path)

    # Get audio duration using ffprobe
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    duration = float(result.stdout.strip())
    start = total_duration
    end = start + duration
    segments.append({"start": start, "end": end, "text": text, "audio": audio_path})
    total_duration = end

# Create silent background video with subtitles
video_path = "video_output/generated_convo.mp4"
text_filters = []

for i, segment in enumerate(segments):
    escaped_text = segment["text"].replace("'", r"\'").replace(":", "\:")
    y_pos = 600 if i % 2 == 0 else 500  # Alternate subtitle position
    text_filters.append(
        f"drawtext=text='{escaped_text}':"
        f"fontcolor=white:fontsize=36:x=(w-text_w)/2:y={y_pos}:"
        f"enable='between(t,{segment['start']},{segment['end']})'"
    )

# Combine all audios
audio_list_path = os.path.join("video_output", "audio_list.txt")
with open(audio_list_path, "w") as f:
    for seg in segments:
        f.write(f"file '{os.path.abspath(seg['audio'])}'\n")
        
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_list,
     "-c", "copy", "video_output/combined_audio.mp3"],
    check=True
)

# Build the full ffmpeg command
ffmpeg_cmd = [
    "ffmpeg",
    "-y",
    "-f", "lavfi",
    "-i", f"color=c=black:s=1280x720:d={int(total_duration + 1)}",
    "-i", "video_output/combined_audio.mp3",
    "-vf", ",".join(text_filters),
    "-c:v", "libx264",
    "-c:a", "aac",
    "-pix_fmt", "yuv420p",
    "-shortest",
    video_path
]

subprocess.run(ffmpeg_cmd, check=True)
print("✅ Video generated:", video_path)
