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
from googleapiclient.discovery import build

# === CONFIG ===
GNEWS_API_KEY = os.getenv("GNEWS_KEY")
YOUTUBE_API_KEY = os.getenv("GCP_API_KEY") # You must set this environment variable
GNEWS_API_ENDPOINT = "https://gnews.io/api/v4/top-headlines"
IMAGE_DIR = "images"
VIDEO_CLIP_DIR = "videoclips" # Directory for downloaded clips
VOICE_PATH = "voice.mp3"
VIDEO_PATH = "final_content_combined.mp4"
ASS_PATH = "subtitles.ass"
METADATA_PATH = "video_metadata.json"
IMAGE_COUNT_PER_ARTICLE = 5 # How many images to get for each story
FONT_TEXT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
BGM_FILES = ["./assets/bkg1.mp3", "./assets/bkg2.mp3"]
LOGO_FILE = "assets/icon.png"
LIKE_FILE = "assets/like.gif"
SKIP_DOMAINS = [
    "washingtonpost.com", "navigacloud.com", "redlakenationnews.com",
    "imengine.public.prod.pdh.navigacloud.com", "arc-anglerfish-washpost-prod-washpost.s3.amazonaws.com"
]
# Path to a cookies file to avoid bot detection in automated environments.
YT_DLP_COOKIES_FILE = "cookies.txt"


def cleanup():
    print("🧹 Cleaning up previous run artifacts...")
    items_to_delete = (
        IMAGE_DIR, VIDEO_CLIP_DIR, "video_slides", "slides.txt", "subtitles.ass",
        "video_metadata.json", "voice.mp3", "final_content_combined.mp4", "final_news_combined.mp4", VIDEO_PATH
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

def get_news_stories(num_articles=5):
    """Fetches and parses multiple news articles, returning them as a list of objects."""
    print(f"📰 Fetching the top {num_articles} news stories...")
    params = {"token": GNEWS_API_KEY, "lang": "en", "country": "us", "max": 10}
    try:
        r = requests.get(GNEWS_API_ENDPOINT, params=params, timeout=10)
        r.raise_for_status()
        articles_data = r.json().get("articles", [])
        if not articles_data:
            print("❌ No articles returned from API."); return []

        stories = []
        for article_data in articles_data:
            if len(stories) >= num_articles:
                break
            try:
                print(f"  -> Parsing article: {article_data['title']}")
                article = Article(article_data['url'])
                article.download()
                article.parse()
                if article.text and len(article.text.split()) > 70:
                    stories.append({
                        "title": article_data['title'],
                        "content": article.text,
                        "images": [],
                        "videos": []
                    })
            except Exception as e:
                print(f"    ⚠️ Could not parse article: {article_data['url']}. Skipping.")

        return stories

    except Exception as e:
        print(f"❌ News fetch error: {e}"); return []

def search_images(query, num_images):
    API_KEY = os.getenv("GCP_API_KEY"); CSE_ID = os.getenv("GSEARCH_CSE_ID")
    if not API_KEY or not CSE_ID:
        print("    ⚠️ GCP_API_KEY or GSEARCH_CSE_ID not set. Skipping image search.")
        return []
    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params={"key": API_KEY, "cx": CSE_ID, "q": query, "searchType": "image", "num": num_images}, timeout=10)
        res.raise_for_status()
        items = res.json().get("items", [])
        return [item["link"] for item in items if not any(d in item["link"] for d in SKIP_DOMAINS)]
    except Exception as e:
        print(f"❌ Image search failed for query '{query}': {e}"); return []

def download_asset(url, save_path):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    Could not download asset from {url}. Error: {e}")
        return False

def search_and_download_videos(query, download_dir, num_clips=1, duration=12):
    """Searches YouTube and downloads short, silent video clips."""
    print(f"  🎬 Searching for video clips related to '{query}'...")
    if not YOUTUBE_API_KEY:
        print("    ⚠️ YOUTUBE_API_KEY environment variable not set. Skipping video search.")
        return []

    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    try:
        # CORRECTED LINE: Use the lowercase 'youtube' variable and access the 'search' resource.
        search_response = youtube.search().list(
            q=f"{query} news report",
            part='snippet',
            maxResults=5,
            type='video',
            videoDuration='short'
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        if not video_ids:
            print("    No relevant video clips found.")
            return []

        downloaded_clips = []
        for i, video_id in enumerate(video_ids):
            if len(downloaded_clips) >= num_clips:
                break

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            clip_path = os.path.join(download_dir, f"clip_{query.replace(' ', '_')[:20]}_{i}.mp4")

            print(f"    📥 Downloading silent clip from {video_url}...")

            yt_dlp_command = [
                "yt-dlp",
                "--quiet",
                "-f", "bestvideo[ext=mp4]/best[ext=mp4]",
                "--no-audio-multistreams",
                "--download-sections", f"*0-{duration}",
                "--force-keyframes-at-cuts",
                "-o", clip_path,
                video_url
            ]

            # Add the cookies argument ONLY if the file exists.
            if os.path.exists(YT_DLP_COOKIES_FILE):
                yt_dlp_command.extend(["--cookies", YT_DLP_COOKIES_FILE])
            else:
                print(f"    ⚠️ Cookies file '{YT_DLP_COOKIES_FILE}' not found. Downloads may fail.")

            try:
                subprocess.run(yt_dlp_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                if os.path.exists(clip_path):
                    downloaded_clips.append(clip_path)
                    print(f"    ✅ Downloaded clip: {clip_path}")
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.decode()
                print(f"    ❌ yt-dlp failed for {video_url}.")
                print(f"       Error: {error_output}")

        return downloaded_clips

    except Exception as e:
        print(f"    ❌ An error occurred during YouTube API call: {e}")
        return []

def generate_voice(text, out_path):
    print("🎤 Generating natural voice with Google TTS...")
    try:
        service_account_info = json.loads(os.environ["GCP_SA_KEY"])
        creds = service_account.Credentials.from_service_account_info(service_account_info)
        client = texttospeech.TextToSpeechClient(credentials=creds)

        max_bytes = 4900
        chunks = []
        current_chunk = ""
        for paragraph in text.split("\n\n"):
            if len(current_chunk.encode("utf-8")) + len(paragraph.encode("utf-8")) < max_bytes:
                current_chunk += paragraph + "\n\n"
            else:
                chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        full_audio = b""
        for i, chunk in enumerate(chunks):
            if not chunk: continue
            print(f"🧩 Synthesizing chunk {i+1}/{len(chunks)}")
            synthesis_input = texttospeech.SynthesisInput(text=chunk)
            voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Wavenet-D")
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.95
            )
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            full_audio += response.audio_content

        with open(out_path, "wb") as out:
            out.write(full_audio)
        print(f"✅ Voiceover saved: {out_path}")
    except Exception as e:
        print(f"❌ Failed to generate voice: {e}")

def generate_ass(text, audio_path, ass_path):
    print("📝 Generating styled subtitles (optimized)...")
    try:
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000.0
        wrapped_text = textwrap.fill(text, width=40)
        lines = wrapped_text.splitlines()

        if not lines: return
        per_line = duration / len(lines)

        def fmt_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            cs = int((seconds - int(seconds)) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Noto Sans,60,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3,1,2,50,50,50,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        dialogues = "\n".join(
            f"Dialogue: 0,{fmt_time(i * per_line)},{fmt_time((i + 1) * per_line)},Default,,0,0,0,,{line.strip()}"
            for i, line in enumerate(lines)
        )
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + dialogues)

        print(f"✅ Subtitles created.")
    except Exception as e:
        print(f"❌ Failed to generate subtitles: {e}")

def create_longform_video(stories, audio_path, output_path, ass_path, bgm_candidates, metadata):
    print("🎞 Rendering long-form video...")

    visual_assets = []
    for story in stories:
        visuals_for_story = story['images'] + story['videos']
        random.shuffle(visuals_for_story)
        visual_assets.extend(visuals_for_story)

    if not visual_assets:
        print("❌ No visual assets found to create video."); return

    narration_duration = get_media_duration(audio_path)
    if not narration_duration or narration_duration == 0:
        print("❌ Invalid narration duration."); return

    ffmpeg_cmd = ["ffmpeg", "-y"]
    input_streams = []
    total_visual_duration = 0
    asset_duration_img = 4

    final_asset_list = []
    while total_visual_duration < narration_duration:
        if not visual_assets:
            break
        final_asset_list.extend(visual_assets)
        for asset_path in visual_assets:
            if Path(asset_path).suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                total_visual_duration += asset_duration_img
            else:
                clip_duration = get_media_duration(asset_path) or 0
                total_visual_duration += clip_duration

    for i, asset_path in enumerate(final_asset_list):
        asset_path_obj = Path(asset_path)
        if asset_path_obj.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            ffmpeg_cmd.extend(["-loop", "1", "-t", str(asset_duration_img), "-i", str(asset_path_obj)])
        else:
            ffmpeg_cmd.extend(["-i", str(asset_path_obj)])
        input_streams.append(f"[{i}:v]")

    num_visual_inputs = len(input_streams)

    # Loop the background music at the input level for reliability
    ffmpeg_cmd.extend([
        "-i", audio_path,
        "-stream_loop", "-1", "-i", random.choice(bgm_candidates), # Loops BGM indefinitely
        "-ignore_loop", "0", "-i", LIKE_FILE,
        "-loop", "1", "-i", LOGO_FILE
    ])
    voice_input_idx, bgm_input_idx, gif_input_idx, logo_input_idx = num_visual_inputs, num_visual_inputs + 1, num_visual_inputs + 2, num_visual_inputs + 3

    filter_chains = []
    scaled_streams = []
    for i in range(num_visual_inputs):
        filter_chains.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]")
        scaled_streams.append(f"[v{i}]")

    filter_chains.append(f"{''.join(scaled_streams)}concat=n={len(scaled_streams)}:v=1:a=0[timeline]")
    filter_chains.append(f"[timeline]ass='{Path(ass_path).as_posix()}'[subtitled_video]")
    filter_chains.append(f"[{gif_input_idx}:v]scale=190:50[gif]")
    filter_chains.append(f"[{logo_input_idx}:v]scale=60:60[logo]")
    filter_chains.append(f"[subtitled_video][logo]overlay=10:10[tmp1];[tmp1]drawtext=text='HotWired':fontfile='{FONT_TEXT}':fontcolor=red:fontsize=36:x=75:y=18[tmp2];[tmp2][gif]overlay=W-w-10:10[v]")

    # Simplified audio filter chain without 'aloop'
    # 'amix=duration=first' will now reliably cut off the infinitely looped BGM when the narration ends.
    filter_chains.append(f"[{voice_input_idx}:a]volume=1.0[a1];[{bgm_input_idx}:a]volume=0.05[a2];[a1][a2]amix=inputs=2:duration=first[aout]")

    ffmpeg_cmd.extend([
        "-filter_complex", ";".join(filter_chains),
        "-map", "[v]", "-map", "[aout]",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-t", str(narration_duration), # This will now be respected
        "-movflags", "+faststart",
        "-metadata", f"title={metadata['title']}",
        "-metadata", f"description={metadata['description']}",
        "-metadata", f"comment=Tags: {', '.join(metadata['tags'])}",
        output_path
    ])

    print("---")
    print("DEBUG: Executing FFmpeg command...")
    # print(' '.join(f'"{arg}"' if ' ' in arg else arg for arg in ffmpeg_cmd))
    print("---")

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"✅ Long-form video saved: {output_path}")
    except subprocess.CalledProcessError as e:
        print("❌ FFmpeg rendering failed.")
        print(f"Error: {e}")

if __name__ == "__main__":
    cleanup()
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(VIDEO_CLIP_DIR, exist_ok=True)

    stories = get_news_stories(num_articles=5)
    if not stories:
        print("❌ No stories found. Exiting.")
        exit()

    all_content_parts = []
    main_title = stories[0]['title'] if stories else "Today's News Roundup"

    for i, story in enumerate(stories):
        print(f"\n--- Processing Story {i+1}/{len(stories)}: {story['title']} ---")

        if i > 0: all_content_parts.append("\n\nNext, in the news...\n\n")
        all_content_parts.append(f"{story['title']}.\n{story['content']}")

        print(f"  🖼️ Searching for images...")
        image_urls = search_images(story['title'], num_images=IMAGE_COUNT_PER_ARTICLE)
        if image_urls:
            for j, img_url in enumerate(image_urls):
                try:
                    safe_suffix = "".join(c for c in Path(img_url).suffix.split('?')[0] if c.isalnum() or c == '.')
                    if not safe_suffix: safe_suffix = ".jpg"
                    img_path = Path(IMAGE_DIR) / f"story{i}_img{j}{safe_suffix}"
                    if download_asset(img_url, img_path):
                        story['images'].append(str(img_path))
                except Exception as e:
                    print(f"    ⚠️ Error processing image URL {img_url}: {e}")

        story['videos'] = search_and_download_videos(story['title'], download_dir=VIDEO_CLIP_DIR, num_clips=2)

    full_narration_text = "".join(all_content_parts)

    description_text = " | ".join([s['title'] for s in stories])
    description_text += f"\n\nStay informed with the latest headlines. In this video: {stories[0]['title']}, and more."

    metadata = {
        "title": main_title,
        "description": description_text[:5000],
        "tags": ["news", "world news", "daily news", "breaking news", "headlines"] + [s['title'].split(' ')[0] for s in stories]
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print("\n✅ Saved consolidated video metadata to video_metadata.json")

    generate_voice(full_narration_text, VOICE_PATH)
    generate_ass(full_narration_text, VOICE_PATH, ASS_PATH)

    if os.path.exists(VOICE_PATH):
        create_longform_video(
            stories=stories,
            audio_path=VOICE_PATH,
            output_path=VIDEO_PATH,
            ass_path=ASS_PATH,
            bgm_candidates=BGM_FILES,
            metadata=metadata
        )