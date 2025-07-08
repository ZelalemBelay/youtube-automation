import os
import sys
import requests
import subprocess
import random
import textwrap
import json
import re
import itertools
import datetime
from pathlib import Path
from newspaper import Article
from google.cloud import texttospeech
from google.oauth2 import service_account
import shutil
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PIL import Image
import cairosvg
import google.generativeai as genai
import yt_dlp

# --- Configuration ---
class Config:
    """Holds all configuration and validates the environment."""
    def __init__(self):
        self.gnews_api_key = os.getenv("GNEWS_KEY")
        self.youtube_api_key = os.getenv("GCP_API_KEY")
        self.google_api_key = os.getenv("GCP_API_KEY")
        self.gcp_sa_key = os.getenv("GCP_SA_KEY")
        self.gsearch_cse_id = os.getenv("GSEARCH_CSE_ID")
        self.pexels_api_key = os.getenv("PEXELS_API_KEY")
        self.validate()
        if self.google_api_key: genai.configure(api_key=self.google_api_key)

        self.image_dir = Path("images")
        self.video_clip_dir = Path("videoclips")
        self.final_video_path = Path("final_content.mp4")
        self.voice_path = Path("voice.mp3")
        self.ass_path = Path("subtitles.ass")
        self.images_to_fetch = 8
        self.youtube_videos_to_fetch = 3
        self.pexels_videos_to_fetch = 2
        self.video_clip_duration = 10
        self.METADATA_PATH = "video_metadata.json"
        self.image_duration = 6
        self.font_text = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
        self.bgm_files = ["./assets/bkg1.mp3", "./assets/bkg2.mp3"]
        self.logo_file = Path("assets/icon.png")
        self.like_file = Path("assets/like.gif")

    def validate(self):
        required = {"GNEWS_KEY": self.gnews_api_key, "GCP_API_KEY": self.google_api_key, "GCP_SA_KEY": self.gcp_sa_key, "GSEARCH_CSE_ID": self.gsearch_cse_id}
        missing = [k for k, v in required.items() if not v]
        if missing: print(f"❌ Critical Error: Missing environment variables: {', '.join(missing)}"); sys.exit(1)

METADATA_PATH = "video_metadata.json"

# --- Utility Functions ---
def cleanup(cfg: Config):
    print("🧹 Cleaning up previous run artifacts...")
    shutil.rmtree(cfg.image_dir, ignore_errors=True)
    shutil.rmtree(cfg.video_clip_dir, ignore_errors=True)
    for f in [cfg.voice_path, cfg.final_video_path, cfg.ass_path, Path("timeline.mp4")]:
        f.unlink(missing_ok=True)

def get_media_duration(media_path: Path) -> float | None:
    if not shutil.which("ffprobe"): print("❌ Error: ffprobe is not installed."); return None
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception: return None

# --- Text Processing ---
def clean_ai_script(text: str) -> str:
    print("    - Sanitizing AI-generated script for narration...")
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = text.replace("Narrator:", "")
    text = text.replace('*', '')
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if re.match(r'^[A-Z\s]+:$', stripped_line): continue
        cleaned_lines.append(stripped_line)
    return "\n".join(filter(None, cleaned_lines))

# --- Core Workflow Functions ---
def get_top_story(cfg: Config) -> tuple[str, str] | None:
    print("📰 Fetching top news stories to select one randomly...")
    params = {"token": cfg.gnews_api_key, "lang": "en", "country": "us", "max": 10}
    try:
        r = requests.get("https://gnews.io/api/v4/top-headlines", params=params, timeout=10)
        r.raise_for_status()
        articles_data = r.json().get("articles", [])
        if not articles_data: print("❌ GNews API returned no articles."); return None
        random.shuffle(articles_data)
        for article_data in articles_data:
            try:
                print(f"  -> Attempting to process: {article_data['title']}")
                article = Article(article_data['url'])
                article.download(); article.parse()
                if not article.text or len(article.text.split()) < 400: continue
                print("    - Generating detailed script with AI for a ~3 minute video...")
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Analyze the following news article and expand it into a detailed news script suitable for a 3-minute video narration. Structure it with an introduction, several paragraphs covering key details and context, and a conclusion. Output ONLY the finished, clean script text."
                response = model.generate_content(prompt + f"\n\n---\n{article.text}\n---")
                clean_content = clean_ai_script(response.text)
                if len(clean_content.split()) < 300: continue
                print(f"✅ Randomly selected story: {article_data['title']}")
                return article_data['title'], clean_content
            except Exception as e: print(f"    - Failed to process article. Error: {e}. Trying next.")
    except Exception as e: print(f"❌ News fetch API error: {e}")
    print("❌ Could not find a suitable top story to process.")
    return None

def get_visual_assets(query: str, cfg: Config) -> tuple[list, list]:
    print(f"🖼️ 📹 Acquiring visual assets for: '{query}'")
    downloaded_images = []
    try:
        img_params = {"key": cfg.google_api_key, "cx": cfg.gsearch_cse_id, "q": query, "searchType": "image", "num": cfg.images_to_fetch}
        res = requests.get("https://www.googleapis.com/customsearch/v1", params=img_params, timeout=10); res.raise_for_status()
        image_urls = [item["link"] for item in res.json().get("items", [])]
        if image_urls:
            print(f"    - Downloading & sanitizing {len(image_urls)} images...")
            for i, url in enumerate(image_urls):
                img_path = None
                try:
                    ext = (Path(url.split('?')[0]).suffix or ".jpg")[:5]
                    if not ext.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.svg']: ext = '.jpg'
                    img_path = cfg.image_dir / f"img_{i}{ext}"
                    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
                    img_path.write_bytes(r.content)
                    final_path = img_path
                    if img_path.suffix.lower() == ".svg":
                        png_path = img_path.with_suffix(".png")
                        cairosvg.svg2png(url=str(img_path), write_to=str(png_path)); img_path.unlink(); final_path = png_path
                    with Image.open(final_path) as img:
                        rgb_img = img.convert('RGB')
                        jpeg_path = final_path.with_suffix(".jpg")
                        rgb_img.save(jpeg_path, "jpeg", quality=95)
                        if final_path != jpeg_path: final_path.unlink()
                        downloaded_images.append(str(jpeg_path))
                except Exception:
                    if img_path and img_path.exists(): img_path.unlink()
    except Exception as e: print(f"    - Warning: Image search failed: {e}")

    youtube_videos = search_and_download_youtube_videos(query, cfg)
    pexels_videos = search_and_download_pexels_videos(query, cfg)
    return downloaded_images, youtube_videos + pexels_videos

def extract_keywords(title: str) -> str:
    stop_words = {"a", "an", "the", "and", "or", "in", "on", "for", "with", "is", "are", "was", "were", "of", "to", "at", "by", "it", "from", "as", "after", "before", "how", "what", "why", "today", "live", "updates"}
    title = re.sub(r'[^\w\s]', '', title.lower())
    words = title.split()
    return " ".join([word for word in words if word not in stop_words and len(word) > 3][:4])

def search_and_download_youtube_videos(query: str, cfg: Config) -> list[str]:
    print(f"    - Searching YouTube (no cookies) for {cfg.youtube_videos_to_fetch} Creative Commons clips...")
    downloaded_clips = []
    search_terms = [f'"{query} news"', f'"{query}" footage', f'"{query}" b-roll']

    for i, term in enumerate(search_terms):
        if len(downloaded_clips) >= cfg.youtube_videos_to_fetch:
            break

        clip_path = cfg.video_clip_dir / f"yt_clip_{i}.mp4"
        search_query = f'ytsearch10:{term}'

        ydl_opts = {
            'format': 'b[ext=mp4]',
            'outtmpl': str(clip_path),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'match_filter': yt_dlp.utils.match_filter_func("!is_live"),
            'postprocessor_args': {
                'ffmpeg': ['-ss', '00:00:05.00', '-t', str(cfg.video_clip_duration), '-an']
            },
        }

        try:
            print(f"      - Searching and attempting download for clip #{i+1} using query: {search_query}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([search_query])

            if clip_path.exists():
                print(f"      ✅ Successfully downloaded: {clip_path}")
                downloaded_clips.append(str(clip_path))
            else:
                print(f"      ❌ Clip {i+1} not found at expected path: {clip_path}")
        except yt_dlp.utils.DownloadError as e:
            print(f"      ❌ yt_dlp DownloadError for clip #{i+1}: {e}")
        except Exception as e:
            print(f"      ❌ Unexpected error while downloading clip #{i+1}: {e}")

    print(f"    - Downloaded {len(downloaded_clips)} clip(s) from YouTube (without cookies).")
    return downloaded_clips


def search_and_download_pexels_videos(query: str, cfg: Config) -> list[str]:
    if not cfg.pexels_api_key: return []
    print(f"    - Searching Pexels for {cfg.pexels_videos_to_fetch} clips...")
    keywords = extract_keywords(query)
    search_queries = [query, keywords]
    downloaded_clips, processed_ids = [], set()
    for q in search_queries:
        if len(downloaded_clips) >= cfg.pexels_videos_to_fetch: break
        try:
            headers = {"Authorization": cfg.pexels_api_key}
            params = {"query": q, "per_page": (cfg.pexels_videos_to_fetch-len(downloaded_clips))*2+3, "orientation": "landscape"}
            res = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=15); res.raise_for_status()
            videos = res.json().get("videos", [])
            if not videos: continue
            for video in videos:
                if len(downloaded_clips) >= cfg.pexels_videos_to_fetch: break
                if video.get('id') in processed_ids: continue
                processed_ids.add(video.get('id'))
                video_link = next((f['link'] for f in video.get('video_files', []) if f.get('quality') == 'hd'), None)
                if not video_link: continue
                clip_path = cfg.video_clip_dir / f"px_clip_{video.get('id')}.mp4"
                r_dl = requests.get(video_link, timeout=45, headers={"User-Agent": "Mozilla/5.0"}); r_dl.raise_for_status()
                clip_path.write_bytes(r_dl.content)
                if clip_path.exists(): downloaded_clips.append(str(clip_path))
        except Exception: continue
    print(f"    - Downloaded {len(downloaded_clips)} clips from Pexels.")
    return downloaded_clips

# --- REWRITTEN: Final, simplest subtitle generation logic ---
def generate_audio_and_subs(text: str, cfg: Config) -> float | None:
    """Generates voiceover and subtitles using the simplest reliable timing method."""
    print("🎤 Generating voiceover...")
    try:
        selected_voice = random.choice(["en-US-Studio-M", "en-US-Wavenet-J", "en-US-Wavenet-F"])
        creds = service_account.Credentials.from_service_account_info(json.loads(cfg.gcp_sa_key))
        client = texttospeech.TextToSpeechClient(credentials=creds)
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(language_code="en-US", name=selected_voice)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice_params, audio_config=audio_config)
        cfg.voice_path.write_bytes(response.audio_content)
        duration = get_media_duration(cfg.voice_path)
        if not duration: raise ValueError("Audio duration could not be determined.")
        print(f"✅ Voiceover saved. Duration: {duration:.2f}s")
    except Exception as e: print(f"❌ Could not generate audio. Error: {e}"); return None

    print("📝 Generating subtitles using simple, reliable timing...")
    if duration < 1: return duration

    clean_text = text.replace('\n', ' ').strip()
    lines = textwrap.wrap(clean_text, width=85, break_long_words=False, replace_whitespace=True)
    if not lines: return duration

    duration_per_line = duration / len(lines)

    def format_time(seconds: float) -> str:
        """Formats seconds into ASS subtitle format h:mm:ss.cs using datetime."""
        if seconds < 0: seconds = 0
        td = datetime.timedelta(seconds=seconds)
        minutes, sec = divmod(td.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        centiseconds = td.microseconds // 10000
        return f"{hours}:{minutes:02d}:{sec:02d}.{centiseconds:02d}"

    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans,42,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ass_data = header

    current_time = 0.0
    for line in lines:
        start_time = current_time
        end_time = current_time + duration_per_line
        ass_data += f"Dialogue: 0,{format_time(start_time)},{format_time(end_time)},Default,,0,0,0,,{line}\n"
        current_time = end_time

    cfg.ass_path.write_text(ass_data, encoding="utf-8")
    print("✅ Subtitles created.")
    return duration

def render_video(images: list, videos: list, duration: float, cfg: Config):
    """Renders the final video with a specific, user-defined asset sequence."""
    print("🎞️ Rendering final video with specific visual sequence...")
    if not images and not videos: print("❌ No visual assets available to render."); sys.exit(1)

    playlist, image_pool = [], list(images)
    if image_pool: playlist.append({'path': image_pool.pop(0), 'duration': cfg.image_duration, 'is_image': True})
    if image_pool: playlist.append({'path': image_pool.pop(0), 'duration': cfg.image_duration, 'is_image': True})

    remaining_assets = image_pool + videos
    random.shuffle(remaining_assets)
    playlist.extend([{'path': p, 'duration': cfg.image_duration if Path(p).suffix.lower() == '.jpg' else cfg.video_clip_duration, 'is_image': Path(p).suffix.lower() == '.jpg'} for p in remaining_assets])

    final_visual_sequence, current_duration = [], 0
    playlist_cycle = itertools.cycle(playlist)
    while current_duration < duration:
        item = next(playlist_cycle)
        final_visual_sequence.append(item)
        current_duration += item['duration']

    print(f"  - Assembled a visual playlist of {len(final_visual_sequence)} items to cover {duration:.2f}s.")

    ffmpeg_cmd = ["ffmpeg", "-y", "-v", "error"]
    filter_chains = []

    for i, item in enumerate(final_visual_sequence):
        if item['is_image']:
            ffmpeg_cmd.extend(["-loop", "1", "-t", str(item['duration']), "-i", item['path']])
        else:
            ffmpeg_cmd.extend(["-i", item['path']])
        filter_chains.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]")

    concat_inputs = "".join(f"[v{i}]" for i in range(len(final_visual_sequence)))
    scaling_chain = ";".join(filter_chains)
    concat_chain = f"{concat_inputs}concat=n={len(final_visual_sequence)}:v=1:a=0[timeline_v]"

    audio_idx, bgm_idx, gif_idx, logo_idx = len(final_visual_sequence), len(final_visual_sequence)+1, len(final_visual_sequence)+2, len(final_visual_sequence)+3
    ffmpeg_cmd.extend(["-i", str(cfg.voice_path), "-i", random.choice(cfg.bgm_files), "-ignore_loop", "0", "-i", str(cfg.like_file), "-loop", "1", "-i", str(cfg.logo_file)])

    overlay_chains = [
        f"[timeline_v]ass='{cfg.ass_path.as_posix()}'[sub]",
        f"[{bgm_idx}:a]volume=0.08,afade=t=out:st={duration-3}:d=3[bgm]",
        f"[{audio_idx}:a][bgm]amix=inputs=2:duration=first:dropout_transition=3[a]",
        f"[{gif_idx}:v]scale=190:50[gif]", f"[{logo_idx}:v]scale=60:60[logo]",
        f"[sub][logo]overlay=10:10[ol1]",
        f"[ol1]drawtext=text='HotWired':fontfile='{cfg.font_text}':fontcolor=red:fontsize=36:x=75:y=18[ol2]",
        f"[ol2][gif]overlay=W-w-10:10[v]"
    ]

    final_filter_complex = ";".join([scaling_chain, concat_chain] + overlay_chains)
    ffmpeg_cmd.extend(["-filter_complex", final_filter_complex, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac", "-t", str(duration), "-movflags", "+faststart", str(cfg.final_video_path)])

    print("  - Executing final render command...")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"✅ Final video saved: {cfg.final_video_path}")
    except subprocess.CalledProcessError:
        print(f"❌ FFmpeg rendering failed. Full command was: {' '.join(ffmpeg_cmd)}"); sys.exit(1)

# --- Main Execution ---
def main():
    """Main function to run the single-story video generation workflow."""
    cfg = Config()
    cleanup(cfg)
    cfg.image_dir.mkdir(exist_ok=True)
    cfg.video_clip_dir.mkdir(exist_ok=True)
    story_data = get_top_story(cfg)
    if not story_data: sys.exit(1)

    title, content = story_data
    images, videos = get_visual_assets(title, cfg)
    if not images and not videos:
        print("❌ No visual assets could be found for the story. Exiting."); sys.exit(1)

    intro_line = "Welcome to Hot Wired. In today's top story:"
    narration_text = f"{intro_line}\n\n{title}.\n\n{content}"

    metadata = {"title": title, "description": content, "tags": ["news", "Usa Today", "update", "daily"]}
    with open(METADATA_PATH, "w") as f: json.dump(metadata, f, indent=2)
    print("✅ Saved video metadata to video_metadata.json")

    duration = generate_audio_and_subs(narration_text, cfg)
    if not duration: sys.exit(1)

    render_video(images, videos, duration, cfg)

    print("\n🎉 Single-story video creation complete!")

if __name__ == "__main__":
    main()