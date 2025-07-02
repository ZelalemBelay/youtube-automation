import os
import json
import requests
import mimetypes
import subprocess
import random
import textwrap
import shutil
from pathlib import Path
from pydub import AudioSegment
from newspaper import Article
from google.cloud import texttospeech
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# === CONFIG ===
GNEWS_API_KEY = os.getenv("GNEWS_KEY")
GNEWS_API_ENDPOINT = "https://gnews.io/api/v4/top-headlines"
IMAGE_DIR = ".github/workflows/images"
VOICE_PATH = ".github/workflows/voice.mp3"
ASS_PATH = ".github/workflows/subtitles.ass"
TEMP_VIDEO_FILE = "temp_final_video.mp4"
IMAGE_COUNT = 10
VIDEO_LENGTH_SECONDS = 420
FONT_TEXT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BGM_FILES = ["assets/bkg1.mp3", "assets/bkg2.mp3"]

SKIP_DOMAINS = [
    "washingtonpost.com", "navigacloud.com", "redlakenationnews.com",
    "imengine.public.prod.pdh.navigacloud.com", "arc-anglerfish-washpost-prod-washpost.s3.amazonaws.com"
]

YT_CLIENT_SECRET_JSON = os.getenv("YT_CLIENT_SECRET_JSON")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN")
YT_UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

service_account_info = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
client = texttospeech.TextToSpeechClient(credentials=creds)

def get_latest_news():
    params = {"token": GNEWS_API_KEY, "lang": "en", "country": "us", "max": 5}
    try:
        r = requests.get(GNEWS_API_ENDPOINT, params=params, timeout=10)
        r.raise_for_status()
        articles = r.json().get("articles", [])
        if not articles:
            return None, None, None
        a = articles[0]
        title, url = a.get("title", ""), a.get("url", "")
        try:
            article = Article(url)
            article.download()
            article.parse()
            content = article.text
        except:
            content = a.get("description", "") or a.get("content", "")
        return title, url, content
    except Exception as e:
        print(f"❌ News fetch error: {e}")
        return None, None, None

def search_images(query):
    API_KEY = os.getenv("GCP_API_KEY")
    CSE_ID = os.getenv("GSEARCH_CSE_ID")
    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params={
            "key": API_KEY, "cx": CSE_ID, "q": query, "searchType": "image", "num": IMAGE_COUNT
        }, timeout=10)
        res.raise_for_status()
        items = res.json().get("items", [])
        return [item["link"] for item in items if not any(d in item["link"] for d in SKIP_DOMAINS)]
    except Exception as e:
        print(f"❌ Image search failed: {e}")
        return []

def download_image(url, path):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if not content_type.startswith("image"):
            return None
        ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".jpg"
        path = Path(path).with_suffix(ext)
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        return path
    except:
        return None

def generate_voice(text, out_path):
    print("🎤 Generating natural voice with Google TTS...")
    chunks, max_bytes = [], 4900
    current_chunk = ""
    for paragraph in text.split("\n"):
        if len(current_chunk.encode("utf-8")) + len(paragraph.encode("utf-8")) < max_bytes:
            current_chunk += paragraph + "\n"
        else:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())

    full_audio = b""
    for i, chunk in enumerate(chunks):
        print(f"🧩 Synthesizing chunk {i+1}/{len(chunks)}")
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=random.choice(["en-US-Wavenet-D", "en-US-Wavenet-F"]))
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        full_audio += response.audio_content

    with open(out_path, "wb") as out:
        out.write(full_audio)
    print(f"✅ Voiceover saved: {out_path}")

def generate_ass(text, audio_path, ass_path):
    print("📝 Generating styled subtitles (optimized)...")
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio) / 1000.0
    lines = textwrap.wrap(text, width=70)
    per_line = duration / len(lines)

    def fmt_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,56,&H00FFFF00,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = "\n".join(
        f"Dialogue: 0,{fmt_time(i * per_line)},{fmt_time((i + 1) * per_line)},Default,,0,0,0,,{line}"
        for i, line in enumerate(lines)
    )
    with open(ass_path, "w") as f:
        f.write(header + dialogues)
    print(f"✅ Subtitles created.")

def create_ffmpeg_video(image_dir, audio_path, output_path, ass_path, video_length, bgm_candidates):
    images = sorted(Path(image_dir).glob("*"))
    if not images:
        print("❌ No images found.")
        return

    per_image = video_length / len(images)
    slide_dir = Path("video_slides")
    slide_dir.mkdir(exist_ok=True)
    slide_paths = []
    for i, img in enumerate(images):
        out = slide_dir / f"slide_{i:03d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img),
            "-t", f"{per_image:.2f}", "-vf", "scale=1280:720",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        slide_paths.append(out)

    concat_list = Path("slides.txt")
    with open(concat_list, "w") as f:
        for path in slide_paths:
            f.write(f"file '{path.resolve()}'\n")

    selected_bgm = random.choice(bgm_candidates)
    print(f"🎶 Mixing background music: {selected_bgm}")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-i", audio_path,
        "-i", selected_bgm,
        "-filter_complex",
        "[1:a]volume=1.0[a1];[2:a]volume=0.05[a2];[a1][a2]amix=inputs=2:duration=first:normalize=0[aout]",
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-shortest", "-loglevel", "error",
        output_path
    ]

    print("🎞 Rendering final video...")
    subprocess.run(cmd, check=True)
    print(f"✅ Final video rendered: {output_path}")

def upload_to_youtube(video_path, title, description):
    creds_info = json.loads(YT_CLIENT_SECRET_JSON)
    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_info["installed"]["client_id"],
        client_secret=creds_info["installed"]["client_secret"],
        scopes=YT_UPLOAD_SCOPES
    )
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["news", "ai generated", "daily news"],
            "categoryId": "25"
        },
        "status": {"privacyStatus": "public"}
    }

    print("📤 Uploading video to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=video_path
    )
    response = request.execute()
    print(f"✅ Video uploaded: https://youtube.com/watch?v={response['id']}")

def cleanup_temp_files():
    print("🧹 Cleaning up temporary files...")
    shutil.rmtree("video_slides", ignore_errors=True)
    shutil.rmtree(IMAGE_DIR, ignore_errors=True)
    for f in [VOICE_PATH, ASS_PATH, "slides.txt"]:
        try: os.remove(f)
        except FileNotFoundError: pass
    print("✅ Cleanup complete.")

if __name__ == "__main__":
    os.makedirs(IMAGE_DIR, exist_ok=True)
    print("📰 Fetching news...")
    title, url, content = get_latest_news()
    if not title or not url:
        print("❌ No news found.")
        exit()

    narration_text = content if content and len(content.strip()) > 50 else title
    narration_text = "Welcome: Please Like comment and Subscribe:.. ON TODAY'S LATEST:  " + narration_text

    print("🔍 Searching for images...")
    image_urls = search_images(title)

    print("📥 Downloading images...")
    downloaded = 0
    for i, img_url in enumerate(image_urls):
        path = os.path.join(IMAGE_DIR, f"img_{i:03d}")
        if download_image(img_url, path):
            downloaded += 1
            if downloaded >= IMAGE_COUNT:
                break
    if downloaded == 0:
        print("❌ No images downloaded, exiting.")
        exit()

    print("🎤 Creating voiceover...")
    generate_voice(narration_text, VOICE_PATH)

    print("📝 Creating subtitles...")
    generate_ass(narration_text, VOICE_PATH, ASS_PATH)

    print("🎞 Creating video...")
    create_ffmpeg_video(IMAGE_DIR, VOICE_PATH, TEMP_VIDEO_FILE, ASS_PATH, VIDEO_LENGTH_SECONDS, BGM_FILES)

    print("📤 Uploading to YouTube...")
    upload_to_youtube(TEMP_VIDEO_FILE, title, content)

    cleanup_temp_files()
    try: os.remove(TEMP_VIDEO_FILE)
    except FileNotFoundError: pass