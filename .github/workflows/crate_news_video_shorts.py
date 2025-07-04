import os
import requests
import mimetypes
import subprocess
import random
import textwrap
import json
from pathlib import Path
from pydub import AudioSegment
from newspaper import Article
from google.cloud import texttospeech
from google.oauth2 import service_account
import shutil

# === CONFIG ===
GNEWS_API_KEY = os.getenv("GNEWS_KEY")
GNEWS_API_ENDPOINT = "https://gnews.io/api/v4/top-headlines"
IMAGE_DIR = "images"
VOICE_PATH = "voice.mp3"
VIDEO_PATH = "final_content_shorts.mp4"
ASS_PATH = "subtitles.ass"
METADATA_PATH = "video_metadata.json"
IMAGE_COUNT = 10
FONT_TEXT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
BGM_FILES = ["./assets/bkg1.mp3", "./assets/bkg2.mp3"]
LOGO_FILE = "assets/icon.png"
LIKE_FILE = "assets/like.gif"
SKIP_DOMAINS = [
    "washingtonpost.com", "navigacloud.com", "redlakenationnews.com",
    "imengine.public.prod.pdh.navigacloud.com", "arc-anglerfish-washpost-prod-washpost.s3.amazonaws.com"
]


def cleanup():
    print("🧹 Cleaning up previous run artifacts...")
    items_to_delete = (
        "images", "video_slides", "slides.txt", "subtitles.ass",
        "video_metadata.json", "voice.mp3", "final_content.mp4", "final_news.mp4", VIDEO_PATH
    )
    for item in items_to_delete:
        try:
            if os.path.exists(item):
                if os.path.isdir(item):
                    shutil.rmtree(item)
                    print(f"  Deleted folder: {item}")
                else:
                    os.remove(item)
                    print(f"  Deleted file: {item}")
        except OSError as e:
            print(f"  Error deleting {item}: {e}")

def get_media_duration(media_path):
    """Gets the duration of a video or audio file in seconds using ffprobe."""
    if not shutil.which("ffprobe"):
        print("❌ Error: ffprobe is not installed or not in your system's PATH.")
        return None
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", media_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"❌ Error getting duration for {media_path}: {e}")
        return None

def get_latest_news():
    params = {"token": GNEWS_API_KEY, "lang": "en", "country": "us", "max": 5}
    try:
        r = requests.get(GNEWS_API_ENDPOINT, params=params, timeout=10)
        r.raise_for_status()
        articles = r.json().get("articles", [])
        if not articles: return None, None, None
        a = articles[0]
        title, url = a.get("title", ""), a.get("url", "")
        try:
            article = Article(url); article.download(); article.parse(); content = article.text
        except:
            content = a.get("description", "") or a.get("content", "")
        return title, url, content
    except Exception as e:
        print(f"❌ News fetch error: {e}"); return None, None, None

def search_images(query):
    API_KEY = os.getenv("GCP_API_KEY"); CSE_ID = os.getenv("GSEARCH_CSE_ID")
    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params={"key": API_KEY, "cx": CSE_ID, "q": query, "searchType": "image", "num": IMAGE_COUNT}, timeout=10)
        res.raise_for_status()
        items = res.json().get("items", [])
        return [item["link"] for item in items if not any(d in item["link"] for d in SKIP_DOMAINS)]
    except Exception as e:
        print(f"❌ Image search failed: {e}"); return []

def download_image(url, path):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "");
        if not content_type.startswith("image"): return None
        ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".jpg"
        path = Path(path).with_suffix(ext)
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024): f.write(chunk)
        return path
    except: return None

def generate_voice(text, out_path):
    print("🎤 Generating natural voice with Google TTS...")
    service_account_info = json.loads(os.environ["GCP_SA_KEY"])
    creds = service_account.Credentials.from_service_account_info(service_account_info)
    client = texttospeech.TextToSpeechClient(credentials=creds)
    max_bytes = 4900; chunks = []; current_chunk = ""
    for paragraph in text.split("\n"):
        if len(current_chunk.encode("utf-8")) + len(paragraph.encode("utf-8")) < max_bytes:
            current_chunk += paragraph + "\n"
        else:
            chunks.append(current_chunk.strip()); current_chunk = paragraph + "\n"
    if current_chunk: chunks.append(current_chunk.strip())
    full_audio = b""
    for i, chunk in enumerate(chunks):
        print(f"🧩 Synthesizing chunk {i+1}/{len(chunks)}")
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Wavenet-D")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        full_audio += response.audio_content
    with open(out_path, "wb") as out: out.write(full_audio)
    print(f"✅ Voiceover saved: {out_path}")

def generate_ass_for_shorts(text, audio_path, ass_path):
    """MODIFIED to generate subtitles in 3-line blocks."""
    print("📝 Generating 3-line styled subtitles for Shorts (9:16)...")
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio) / 1000.0

    # First, wrap the text into individual lines
    lines = textwrap.wrap(text, width=35)

    # Then, group these lines into chunks of 3
    three_line_groups = [lines[i:i + 3] for i in range(0, len(lines), 3)]

    if not three_line_groups:
        print("⚠️ No text to generate subtitles for.")
        return

    # Calculate the duration each 3-line block should be on screen
    duration_per_group = duration / len(three_line_groups)

    def fmt_time(seconds):
        h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100); return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    header = f"[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,70,&H0000FFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,100,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

    dialogue_lines = []
    for i, group in enumerate(three_line_groups):
        start_time = fmt_time(i * duration_per_group)
        end_time = fmt_time((i + 1) * duration_per_group)
        # Join the lines with the .ass newline character '\N'
        text_block = "\\N".join(group)
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text_block}"
        )

    dialogues = "\n".join(dialogue_lines)
    with open(ass_path, "w") as f: f.write(header + dialogues)
    print(f"✅ Subtitles created.")

def create_shorts_video(image_dir, audio_path, output_path, ass_path, video_length, bgm_candidates, metadata):
    """Creates a YouTube Short (9:16) with dynamic cropping and overlays."""
    print("🎞 Rendering YouTube Short video...")
    images = sorted(Path(image_dir).glob("*"))
    if not images:
        print("❌ No images found."); return

    image_duration = 5
    num_slides = int(video_length // image_duration) + 1
    looped_images = [images[i % len(images)] for i in range(num_slides)]

    ffmpeg_cmd = ["ffmpeg", "-y"]

    for img_path in looped_images:
        ffmpeg_cmd.extend(["-loop", "1", "-t", str(image_duration), "-i", str(img_path)])

    current_index = len(looped_images)

    voice_input_index = current_index
    ffmpeg_cmd.extend(["-i", audio_path]); current_index += 1

    selected_bgm = random.choice(bgm_candidates)
    bgm_input_index = current_index
    ffmpeg_cmd.extend(["-i", selected_bgm]); current_index += 1

    gif_input_index = current_index
    ffmpeg_cmd.extend(["-ignore_loop", "0", "-i", LIKE_FILE]); current_index += 1

    logo_input_index = current_index
    ffmpeg_cmd.extend(["-loop", "1", "-i", LOGO_FILE]); current_index += 1

    filter_chains = []
    processed_slide_streams = []

    for i in range(num_slides):
        input_stream = f"[{i}:v]"
        output_stream_name = f"[v{i}]"
        scale_crop_filter = f"{input_stream}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1{output_stream_name}"
        filter_chains.append(scale_crop_filter)
        processed_slide_streams.append(output_stream_name)

    concat_inputs = "".join(processed_slide_streams)
    filter_chains.append(f"{concat_inputs}concat=n={num_slides}:v=1:a=0[slides_raw]")
    filter_chains.append(f"[slides_raw]ass='{Path(ass_path).as_posix()}',format=yuv420p[subtitled_slides]")
    filter_chains.append(f"[{gif_input_index}:v]scale=190:50[gif]")
    filter_chains.append(f"[{logo_input_index}:v]scale=60:60[logo]")

    filter_chains.append(
        f"[subtitled_slides][logo]overlay=30:30[tmp1];"
        f"[tmp1]drawtext=text='HotWired':fontfile='{FONT_TEXT}':fontcolor=red:fontsize=60:x=105:y=30[tmp2];"
        f"[tmp2][gif]overlay=W-w-30:30[v]"
    )

    filter_chains.append(f"[{voice_input_index}:a]volume=1.0[a1];[{bgm_input_index}:a]volume=0.05[a2];[a1][a2]amix=inputs=2:duration=first:normalize=0[aout]")

    full_filter_complex = ";".join(filter_chains)
    ffmpeg_cmd.extend(["-filter_complex", full_filter_complex])

    ffmpeg_cmd.extend([
        "-map", "[v]",
        "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ])

    subprocess.run(ffmpeg_cmd, check=True)
    print(f"✅ YouTube Short saved: {output_path}")

if __name__ == "__main__":
    cleanup()
    os.makedirs(IMAGE_DIR, exist_ok=True)

    print("📰 Fetching news...")
    title, url, content = get_latest_news()
    if not title or not url: print("❌ No news found."); exit()

    max_words_for_shorts = 140
    short_content = ' '.join(content.split()[:max_words_for_shorts])

    if len(content.split()) > max_words_for_shorts:
        short_content += "..."

    print(f"✂️  Content truncated to ~{max_words_for_shorts} words for YouTube Shorts format.")

    metadata = {"title": title, "description": content, "tags": ["news", "shorts", "update", "daily"]}
    with open(METADATA_PATH, "w") as f: json.dump(metadata, f, indent=2)
    print("✅ Saved video metadata to video_metadata.json")

    print("🔍 Searching for images...")
    image_urls = search_images(title)
    if not image_urls: print("❌ Image search failed. Exiting."); exit()

    print("📥 Downloading images...")
    downloaded = 0
    for i, img_url in enumerate(image_urls):
        path = os.path.join(IMAGE_DIR, f"img_{i:03d}")
        if download_image(img_url, path): downloaded += 1
    if downloaded == 0: print("❌ No images downloaded, exiting."); exit()

    narration_text = f"Welcome to today's update. Please like, comment, and subscribe. Here's the latest:\n\n{short_content}"
    print("🎤 Creating voiceover...")
    generate_voice(narration_text, VOICE_PATH)

    narration_duration = get_media_duration(VOICE_PATH)
    if not narration_duration:
        print("❌ Could not determine narration duration. Exiting.")
        exit()

    if narration_duration >= 60:
        print(f"⚠️ WARNING: Narration is {narration_duration:.2f}s, which may be too long for Shorts. Continuing anyway.")

    print(f"✅ Narration duration is {narration_duration:.2f} seconds.")

    print("📝 Creating subtitles...")
    generate_ass_for_shorts(narration_text, VOICE_PATH, ASS_PATH)

    create_shorts_video(
        image_dir=IMAGE_DIR,
        audio_path=VOICE_PATH,
        output_path=VIDEO_PATH,
        ass_path=ASS_PATH,
        video_length=narration_duration,
        bgm_candidates=BGM_FILES,
        metadata=metadata
    )