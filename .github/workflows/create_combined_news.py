import os
import requests
import subprocess
import random
import textwrap
import json
import re
from pathlib import Path
from pydub import AudioSegment
from newspaper import Article
from google.cloud import texttospeech
from google.oauth2 import service_account
import shutil
from googleapiclient.discovery import build
from PIL import Image # For image validation
import cairosvg # For SVG to PNG conversion
import google.generativeai as genai

# === CONFIG ===
GNEWS_API_KEY = os.getenv("GNEWS_KEY")
YOUTUBE_API_KEY = os.getenv("GCP_API_KEY")
GOOGLE_API_KEY = os.getenv("GCP_API_KEY")
GNEWS_API_ENDPOINT = "https://gnews.io/api/v4/top-headlines"
IMAGE_DIR = "images"
VIDEO_CLIP_DIR = "videoclips"
VOICE_PATH = "voice.mp3"
VIDEO_PATH = "final_content_combined.mp4"
ASS_PATH = "subtitles.ass"
METADATA_PATH = "video_metadata.json"
IMAGE_COUNT_PER_ARTICLE = 5
FONT_TEXT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
BGM_FILES = ["./assets/bkg1.mp3", "./assets/bkg2.mp3"]
LOGO_FILE = "assets/icon.png"
LIKE_FILE = "assets/like.gif"
SKIP_DOMAINS = [
    "washingtonpost.com", "navigacloud.com", "redlakenationnews.com",
    "imengine.public.prod.pdh.navigacloud.com", "arc-anglerfish-washpost-prod-washpost.s3.amazonaws.com"
]
cookies_file_path = "cookies.txt"

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

def preprocess_and_summarize_text(raw_text):
    print("    -> Cleaning and summarizing article text...")
    lines = raw_text.split('\n')
    cleaned_lines = []
    patterns_to_remove = [
        r"advertisement", r"image source", r"photo by", r"read more",
        r"related topics", r"copyright", r"all rights reserved",
        r"follow us on", r"share this story"
    ]
    for line in lines:
        if any(re.search(p, line, re.IGNORECASE) for p in patterns_to_remove): continue
        if len(line.split()) < 4: continue
        cleaned_lines.append(line)
    cleaned_text = "\n".join(cleaned_lines)
    if not GOOGLE_API_KEY:
        print("    ⚠️ GOOGLE_API_KEY not set. Skipping AI summarization, using cleaned text.")
        return cleaned_text
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are a news script editor. Your task is to take the raw text from a news article and prepare it for a text-to-speech engine that will be used in a video news report.
        Perform the following actions:
        1. Summarize the article into a concise narrative of 3-4 key paragraphs. The summary should be fluid and engaging.
        2. Remove any remaining artifacts like photo captions, legal disclaimers, or any other text that would sound unnatural in a spoken news report.
        3. Ensure the output is clean, coherent, and ready to be read aloud directly.
        4. Do NOT add any introductory or concluding phrases like "Here is the summary:". Output ONLY the final, clean news script text.

        Here is the article text to process:
        ---
        {cleaned_text}
        ---
        """
        response = model.generate_content(prompt)
        summarized_text = response.text
        print("    ✅ AI summarization complete.")
        return summarized_text.strip()
    except Exception as e:
        print(f"    ❌ Error during AI summarization: {e}")
        print("    ⚠️ Falling back to cleaned text without summarization.")
        return cleaned_text

def cleanup():
    print("🧹 Cleaning up previous run artifacts...")
    for item in Path(".").glob("segment_*.mp4"): item.unlink()
    for item in Path(".").glob("voice_*.mp3"): item.unlink()
    for item in Path(".").glob("subtitles_*.ass"): item.unlink()
    items_to_delete = (
        IMAGE_DIR, VIDEO_CLIP_DIR, "video_slides", "slides.txt", "subtitles.ass",
        "video_metadata.json", "voice.mp3", "final_content_combined.mp4", "concat_list.txt",
        "final_news_combined.mp4", VIDEO_PATH
    )
    for item in items_to_delete:
        try:
            if os.path.exists(item):
                if os.path.isdir(item): shutil.rmtree(item)
                else: os.remove(item)
        except OSError as e: print(f"  Error deleting {item}: {e}")

def get_media_duration(media_path):
    if not shutil.which("ffprobe"):
        print("❌ Error: ffprobe is not installed or not in your system's PATH."); return None
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", media_path]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"❌ Error getting duration for {media_path}: {e}"); return None

def get_news_stories(num_articles=5):
    print(f"📰 Fetching the top {num_articles} news stories...")
    params = {"token": GNEWS_API_KEY, "lang": "en", "country": "us", "max": 10}
    try:
        r = requests.get(GNEWS_API_ENDPOINT, params=params, timeout=10)
        r.raise_for_status()
        articles_data = r.json().get("articles", [])
        if not articles_data: print("❌ No articles returned from API."); return []
        stories = []
        for article_data in articles_data:
            if len(stories) >= num_articles: break
            try:
                print(f"  -> Parsing article: {article_data['title']}")
                article = Article(article_data['url'])
                article.download()
                article.parse()
                if article.text and len(article.text.split()) > 70:
                    processed_content = preprocess_and_summarize_text(article.text)
                    if not processed_content or len(processed_content.split()) < 40:
                        print("    ⚠️ Summarization resulted in text that is too short. Skipping article."); continue
                    stories.append({"title": article_data['title'], "content": processed_content, "images": [], "videos": []})
            except Exception as e: print(f"    ⚠️ Could not parse or process article: {article_data['url']}. Error: {e}")
        return stories
    except Exception as e: print(f"❌ News fetch error: {e}"); return []

def search_images(query, num_images):
    API_KEY, CSE_ID = os.getenv("GCP_API_KEY"), os.getenv("GSEARCH_CSE_ID")
    if not API_KEY or not CSE_ID: print("    ⚠️ GCP_API_KEY or GSEARCH_CSE_ID not set. Skipping image search."); return []
    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params={"key": API_KEY, "cx": CSE_ID, "q": query, "searchType": "image", "num": num_images}, timeout=10)
        res.raise_for_status()
        items = res.json().get("items", [])
        return [item["link"] for item in items if not any(d in item["link"] for d in SKIP_DOMAINS)]
    except Exception as e: print(f"❌ Image search failed for query '{query}': {e}"); return []

def download_asset(url, save_path):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        with open(save_path, "wb") as f: f.write(r.content)
        return True
    except Exception as e: print(f"    Could not download asset from {url}. Error: {e}"); return False

def search_and_download_videos(query, download_dir, num_clips=1, duration=12):
    print(f"  🎬 Searching for video clips related to '{query}'...")
    if not YOUTUBE_API_KEY:
        print("    ⚠️ YOUTUBE_API_KEY not set. Skipping video search.")
        return []

    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    try:
        search_response = youtube.search().list(
            q=f"{query} news report",
            part='snippet',
            maxResults=5,
            type='video',
            videoDuration='short'
        ).execute()
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        if not video_ids:
            print("    ❌ No video results returned from YouTube.")
            return []

        downloaded_clips = []
        for i, video_id in enumerate(video_ids):
            if len(downloaded_clips) >= num_clips:
                break

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            safe_name = re.sub(r'[^\w\d_-]', '', query.lower().replace(' ', '_'))[:20]
            clip_path = os.path.join(download_dir, f"clip_{safe_name}_{i}.mp4")

            print(f"    📥 Attempting download: {video_url}")
            yt_dlp_command = [
                "yt-dlp",
                "--quiet",
                "--no-warnings",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
                "--merge-output-format", "mp4",
                "--download-sections", f"*0-{duration}",
                "--force-keyframes-at-cuts",
                "-o", clip_path,
                video_url
            ]

            # Optional: Skip cookies even if file exists
            if os.path.exists(cookies_file_path):
                print("    🔍 Running without cookies despite cookies.txt existing.")

            try:
                result = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=True)
                if os.path.exists(clip_path):
                    downloaded_clips.append(clip_path)
                    print(f"    ✅ Downloaded clip to: {clip_path}")
                else:
                    print(f"    ❌ Downloaded file not found: {clip_path}")
            except subprocess.CalledProcessError as e:
                print(f"    ❌ yt-dlp failed to download from {video_url}")
                print(f"       stderr: {e.stderr.strip()}")
            except Exception as e:
                print(f"    ❌ Unexpected error: {e}")

        if not downloaded_clips:
            print("    ⚠️ No clips were successfully downloaded.")
        return downloaded_clips

    except Exception as e:
        print(f"    ❌ Error while using YouTube API: {e}")
        return []

def generate_voice(text, out_path):
    print("🎤 Generating natural voice with Google TTS...")
    try:
        # --- NEW: Randomly select a high-quality voice and adjust prosody ---
        CANDIDATE_VOICES = [
            "en-US-Studio-M",   # Male, Studio quality, for narration
            "en-US-Studio-O",   # Female, Studio quality, for narration
            "en-US-Wavenet-J",  # Male, expressive
            "en-US-Wavenet-I",  # Male, expressive
            "en-US-Wavenet-H",  # Female, expressive
            "en-US-Wavenet-G",  # Female, expressive
            "en-US-Wavenet-A",  # Male
            "en-US-Wavenet-F"   # Female
        ]
        selected_voice_name = random.choice(CANDIDATE_VOICES)
        speaking_rate = random.uniform(0.95, 1.05)
        pitch = random.uniform(-1.0, 1.0)

        print(f"    -> Voice: {selected_voice_name}, Rate: {speaking_rate:.2f}, Pitch: {pitch:.2f}")

        service_account_info = json.loads(os.environ["GCP_SA_KEY"])
        creds = service_account.Credentials.from_service_account_info(service_account_info)
        client = texttospeech.TextToSpeechClient(credentials=creds)
        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US", name=selected_voice_name
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch
        )
        # --- END OF NEW LOGIC ---

        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        with open(out_path, "wb") as out: out.write(response.audio_content)
        print(f"✅ Voiceover saved: {out_path}")
    except Exception as e: print(f"❌ Failed to generate voice: {e}")

def generate_ass(text, audio_path, ass_path):
    print("📝 Generating styled subtitles (optimized)...")
    try:
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000.0
        wrapped_text = textwrap.fill(text, width=70)
        lines = wrapped_text.splitlines()
        if not lines: return
        per_line = duration / len(lines)
        def fmt_time(seconds):
            h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60); cs = int((seconds - int(seconds)) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
        header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans,60,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3,1,2,50,50,50,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        dialogues = "\n".join(f"Dialogue: 0,{fmt_time(i * per_line)},{fmt_time((i + 1) * per_line)},Default,,0,0,0,,{line.strip()}" for i, line in enumerate(lines))
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + dialogues)
        print(f"✅ Subtitles created.")
    except Exception as e:
        print(f"❌ Failed to generate subtitles: {e}")

def create_story_video(story_index, story_data, audio_path, ass_path, output_path):
    print(f"🎞 Creating video segment for story {story_index+1}...")
    visual_assets = story_data['images'] + story_data['videos']
    random.shuffle(visual_assets)
    if not visual_assets:
        print("    ❌ No visual assets for this story. Skipping segment."); return None
    narration_duration = get_media_duration(audio_path)
    if not narration_duration or narration_duration == 0:
        print("    ❌ Invalid narration duration for segment."); return None
    ffmpeg_cmd = ["ffmpeg", "-y"]
    final_asset_list, total_visual_duration, asset_duration_img = [], 0, 4
    while total_visual_duration < narration_duration:
        if not visual_assets: break
        final_asset_list.extend(visual_assets)
        for asset_path in visual_assets:
            if Path(asset_path).suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']: total_visual_duration += asset_duration_img
            else: total_visual_duration += get_media_duration(asset_path) or 0
    for asset_path in final_asset_list:
        if Path(asset_path).suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            ffmpeg_cmd.extend(["-loop", "1", "-t", str(asset_duration_img), "-i", str(asset_path)])
        else:
            ffmpeg_cmd.extend(["-i", str(asset_path)])
    ffmpeg_cmd.extend(["-i", audio_path])
    voice_input_idx = len(final_asset_list)
    filter_chains, scaled_streams = [], []
    for i in range(len(final_asset_list)):
        filter_chains.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]")
        scaled_streams.append(f"[v{i}]")
    filter_chains.append(f"{''.join(scaled_streams)}concat=n={len(scaled_streams)}:v=1:a=0[timeline]")
    filter_chains.append(f"[timeline]ass='{Path(ass_path).as_posix()}'[v]")
    ffmpeg_cmd.extend(["-filter_complex", ";".join(filter_chains), "-map", "[v]", "-map", f"{voice_input_idx}:a", "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-t", str(narration_duration), output_path])
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"    ✅ Segment saved: {output_path}"); return output_path
    except subprocess.CalledProcessError as e:
        print(f"    ❌ FFmpeg segment rendering failed. Error: {e}"); return None

def combine_videos(segment_paths, full_audio_path, output_path, metadata):
    print("🎬 Combining all video segments...")
    concat_file_path = "concat_list.txt"
    with open(concat_file_path, "w") as f:
        for path in segment_paths: f.write(f"file '{path}'\n")
    narration_duration = get_media_duration(full_audio_path)
    ffmpeg_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file_path, "-i", full_audio_path, "-stream_loop", "-1", "-i", random.choice(BGM_FILES), "-ignore_loop", "0", "-i", LIKE_FILE, "-loop", "1", "-i", LOGO_FILE]
    filter_complex = f"[1:a]volume=1.0[a1];[2:a]volume=0.05[a2];[a1][a2]amix=inputs=2:duration=first[aout];[3:v]scale=190:50[gif];[4:v]scale=60:60[logo];[0:v][logo]overlay=10:10[tmp1];[tmp1]drawtext=text='HotWired':fontfile='{FONT_TEXT}':fontcolor=red:fontsize=36:x=75:y=18[tmp2];[tmp2][gif]overlay=W-w-10:10[vout]"
    ffmpeg_cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-t", str(narration_duration), "-movflags", "+faststart", "-metadata", f"title={metadata['title']}", "-metadata", f"description={metadata['description']}", "-metadata", f"comment=Tags: {', '.join(metadata['tags'])}", output_path])
    print("--- \nDEBUG: Executing Final FFmpeg command...\n---")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"✅ Final video saved: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Final video combination failed. Error: {e}")

if __name__ == "__main__":
    cleanup()
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(VIDEO_CLIP_DIR, exist_ok=True)
    stories = get_news_stories(num_articles=5)
    if not stories: print("❌ No stories found. Exiting."); exit()
    video_segments, segment_audio_files = [], []
    main_title = stories[0]['title'] if stories else "Today's News Roundup"
    for i, story in enumerate(stories):
        print(f"\n--- Processing Story {i+1}/{len(stories)}: {story['title']} ---")
        story_text = "In our next story... " + f"{story['title']}.\n{story['content']}" if i > 0 else f"{story['title']}.\n{story['content']}"
        segment_audio_path, segment_ass_path = f"voice_{i}.mp3", f"subtitles_{i}.ass"
        generate_voice(story_text, segment_audio_path)
        if not os.path.exists(segment_audio_path): print(f"    ❌ Could not generate audio for story {i}, skipping."); continue
        segment_audio_files.append(segment_audio_path)
        generate_ass(story_text, segment_audio_path, segment_ass_path)
        print(f"  🖼️ Searching for images...")
        image_urls = search_images(story['title'], num_images=IMAGE_COUNT_PER_ARTICLE)
        if image_urls:
            for j, img_url in enumerate(image_urls):
                try:
                    safe_suffix = "".join(c for c in Path(img_url).suffix.split('?')[0] if c.isalnum() or c == '.') or ".jpg"
                    img_path = Path(IMAGE_DIR) / f"story{i}_img{j}{safe_suffix}"
                    if download_asset(img_url, img_path):
                        final_image_path = str(img_path)
                        if final_image_path.endswith(".svg"):
                            print(f"    🎨 Converting SVG to PNG: {final_image_path}")
                            png_path = Path(final_image_path).with_suffix(".png")
                            try:
                                cairosvg.svg2png(url=final_image_path, write_to=str(png_path)); os.remove(final_image_path); final_image_path = str(png_path)
                            except Exception as e: print(f"    ❌ Failed to convert SVG: {e}"); continue
                        try:
                            with Image.open(final_image_path) as img: img.verify()
                            print(f"    ✅ Valid image ready: {final_image_path}")
                            story['images'].append(final_image_path)
                        except Exception as e:
                            print(f"    ❌ Invalid image file. Deleting. Error: {e}")
                            if os.path.exists(final_image_path): os.remove(final_image_path)
                except Exception as e: print(f"    ⚠️ Error processing image URL {img_url}: {e}")
        story['videos'] = search_and_download_videos(story['title'], download_dir=VIDEO_CLIP_DIR, num_clips=2)
        segment_path = create_story_video(i, story, segment_audio_path, segment_ass_path, f"segment_{i}.mp4")
        if segment_path: video_segments.append(segment_path)
    if not video_segments: print("❌ No video segments created. Exiting."); exit()
    print("🔊 Combining all audio segments into master track...")
    combined_audio = sum((AudioSegment.from_mp3(f) for f in segment_audio_files), AudioSegment.empty())
    combined_audio.export(VOICE_PATH, format="mp3")
    duration_in_seconds = get_media_duration(VOICE_PATH)
    if duration_in_seconds:
        minutes, seconds = int(duration_in_seconds // 60), int(duration_in_seconds % 60)
        print(f"🔊 Master audio created. Total video length: {minutes} minutes and {seconds} seconds.")
    description_text = " | ".join([s['title'] for s in stories]) + f"\n\nStay informed with the latest headlines. In this video: {stories[0]['title']}, and more."
    metadata = {"title": main_title, "description": description_text[:5000], "tags": ["news", "world news", "daily news", "breaking news", "headlines"] + [s['title'].split(' ')[0] for s in stories]}
    with open(METADATA_PATH, "w") as f: json.dump(metadata, f, indent=2)
    print("\n✅ Saved consolidated video metadata.")
    combine_videos(video_segments, VOICE_PATH, VIDEO_PATH, metadata)