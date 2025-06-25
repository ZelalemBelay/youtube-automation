import os
from moviepy.editor import *
from gtts import gTTS

# Create output folder
os.makedirs("video_output", exist_ok=True)

# Define conversation (hardcoded for now)
dialogues = [
    {"speaker": "A", "text": "Hey, did you hear about the guy who fell off the first floor holding a microwave?"},
    {"speaker": "B", "text": "Yeah, I saw it. Funniest thing I’ve seen all week!"},
    {"speaker": "A", "text": "I still can't believe he saved the microwave."}
]

# Background and character placeholders
video_width, video_height = 1280, 720
bg_color = (30, 30, 30)
char_a = TextClip("🙂", fontsize=150, color="white").set_position(("left", "center"))
char_b = TextClip("😮", fontsize=150, color="white").set_position(("right", "center"))

# Generate audio clips and subtitle clips
clips = []
current_time = 0
subtitle_clips = []

for i, line in enumerate(dialogues):
    speaker = line["speaker"]
    text = line["text"]

    # Generate TTS
    tts = gTTS(text=text)
    tts_path = f"video_output/audio_{i}.mp3"
    tts.save(tts_path)

    # Load audio and calculate duration
    audio = AudioFileClip(tts_path)
    duration = audio.duration

    # Background clip
    bg_clip = ColorClip(size=(video_width, video_height), color=bg_color, duration=duration)
    bg_clip = bg_clip.set_audio(audio).set_start(current_time)

    # Character placement
    speaker_clip = char_a if speaker == "A" else char_b
    speaker_clip = speaker_clip.set_duration(duration).set_start(current_time)

    # Subtitle
    subtitle = TextClip(text, fontsize=40, color="white", bg_color="black", size=(video_width - 100, None), method="caption")
    subtitle = subtitle.set_position(("center", video_height - 100)).set_duration(duration).set_start(current_time)

    clips.extend([bg_clip, speaker_clip])
    subtitle_clips.append(subtitle)

    current_time += duration

# Combine everything
final_video = CompositeVideoClip(clips + subtitle_clips, size=(video_width, video_height))
final_path = "video_output/generated_convo.mp4"
final_video.write_videofile(final_path, fps=24)

print("✅ Video generated:", final_path)
