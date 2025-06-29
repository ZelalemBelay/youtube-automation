import os
import pickle
import json
import requests
import time

# For YouTube API
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# For Veo (using google-generativeai as per Google's latest examples)
import google.generativeai as genai
# Removed explicit import for 'Operation' as it's causing ImportErrors.
# We will rely on the object returned by the API having the necessary attributes.


# --- Configuration ---
# Google AI Studio / Veo API Key (for google-generativeai client)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Veo Model Name (as per Google's documentation for google-generativeai)
VEO_MODEL_NAME_GENAI = "veo-2.0-generate-001" 

VIDEO_OUTPUT_DIR = "generated_videos"

# YouTube API Configuration
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22" # Example: People & Blogs (adjust as needed for your content)

# Get YouTube API credentials from environment variables (GitHub Secrets)
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

def authenticate_youtube():
    """
    Authenticates with YouTube Data API using OAuth 2.0.
    Prioritizes loading from token.pickle, then uses refresh token from environment.
    This function is designed for a non-interactive CI/CD environment.
    """
    print(REFRESH_TOKEN)

    creds = None
    token_pickle_path = "token.pickle"

    if os.path.exists(token_pickle_path):
        try:
            with open(token_pickle_path, "rb") as token:
                creds = pickle.load(token)
            print("Loaded credentials from token.pickle.")
        except Exception as e:
            print(f"Error loading token.pickle: {e}. Will attempt to create new credentials.")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Existing credentials expired, attempting to refresh...")
            try:
                creds.refresh(Request())
                print("Credentials refreshed successfully.")
            except Exception as e:
                print(f"Failed to refresh credentials: {e}. Will attempt to create new ones from environment variables.")
                creds = None
        
        if not creds and all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
            print("Creating new credentials from environment variables (Client ID, Client Secret, Refresh Token)...")
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=REFRESH_TOKEN,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=SCOPES
                )
                creds.refresh(Request())
                print("Credentials created and refreshed using environment variables.")
            except Exception as e:
                print(f"Failed to create credentials from environment variables: {e}")
                creds = None

        if not creds:
            raise Exception(
                "YouTube OAuth credentials missing or invalid. "
                "Ensure YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
                "and YOUTUBE_REFRESH_TOKEN are correctly set as GitHub Secrets. "
                "The REFRESH_TOKEN must be obtained via a *one-time local interactive authentication*."
            )

    try:
        with open(token_pickle_path, "wb") as token:
            pickle.dump(creds, token)
        print("Credentials saved/updated in token.pickle.")
    except Exception as e:
        print(f"Warning: Could not save credentials to token.pickle: {e}")

    return build("youtube", "v3", credentials=creds)


def generate_veo_video(prompt: str, output_path: str):
    """Generates a video using Veo with the google-generativeai client."""
    print(f"Generating video for prompt: '{prompt}' using Veo via google-generativeai...")

    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable is not set. Cannot use Veo.")

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # Initialize the base client - this was problematic before, but needed for .models.generate_videos
        # Let's try it again, as the alternative was worse.
        client = genai.Client() 

        # The config for video generation as a dictionary, passed to 'config' argument
        config_dict = {
            "aspect_ratio": "16:9",
            "person_generation": "dont_allow",
            "number_of_videos": 1, 
            "duration_seconds": 8, 
            # "negative_prompt": "blurry, low quality, bad composition",
            # "audio_description": "sound of rain",
        }
        
        print("Sending video generation request to Veo (this may take a few minutes)...")
        # Use the specialized models.generate_videos method
        # This returns an Operation object.
        operation = client.models.generate_videos(
            model=VEO_MODEL_NAME_GENAI,
            prompt=prompt,
            config=config_dict, # Pass the dictionary directly as 'config'
        )
        
        # --- CRITICAL FIX HERE: Simplified Operation Polling ---
        # The Operation object returned by client.models.generate_videos *should* have wait_until_done()
        # This avoids needing to manually call client.operations.get(operation.name) or re-import Operation type.
        print("Video generation initiated, polling for completion (this may take a few minutes)...")
        operation.wait_until_done() 
        
        if operation.error:
            raise Exception(f"Veo generation failed with error: {operation.error.message}")
        
        generated_video_url = None
        # The structure from google.generativeai's GenerateVideosResponse (which is operation.result()) is:
        # response.generated_videos[0].video.uri 
        if hasattr(operation.result(), 'generated_videos') and operation.result().generated_videos:
            if hasattr(operation.result().generated_videos[0], 'video') and hasattr(operation.result().generated_videos[0].video, 'uri'):
                generated_video_url = operation.result().generated_videos[0].video.uri
        
        # Fallback patterns (less likely if generate_videos is used, but for robustness)
        if not generated_video_url and hasattr(operation.result(), 'candidates') and operation.result().candidates:
            for candidate in operation.result().candidates:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'file_data') and hasattr(part.file_data, 'file_uri'):
                            generated_video_url = part.file_data.file_uri
                            break
                        elif hasattr(part, 'video_uri'):
                            generated_video_url = part.video_uri
                            break
                if generated_video_url:
                    break

        if not generated_video_url:
            raise ValueError("Could not find video URL in Veo response. Response structure might have changed or generation failed silently.")

        print(f"Veo video generated! Downloading from: {generated_video_url}")

        download_url = f"{generated_video_url}&key={GOOGLE_API_KEY}"
        download_response = requests.get(download_url, stream=True)
        download_response.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in download_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Video downloaded to: {output_path}")
        return output_path

    except Exception as e:
        print(f"Error during Veo video generation for prompt '{prompt}': {e}")
        raise

def upload_youtube_video(youtube_service, video_path: str, title: str, description: str, tags: list, privacy_status: str):
    """Uploads a video to YouTube."""
    print(f"Uploading video '{title}' to YouTube...")
    try:
        body = dict(
            snippet=dict(
                title=title,
                description=description,
                tags=tags,
                categoryId=YOUTUBE_CATEGORY_ID
            ),
            status=dict(
                privacyStatus=privacy_status
            )
        )

        media_body = MediaFileUpload(video_path, chunksize=-1, resumable=True)

        request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media_body
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")

        video_id = response.get('id')
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"Video uploaded! Video ID: {video_id}")
        print(f"YouTube URL: {youtube_url}")
        return video_id

    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred during YouTube upload:\n{e.content}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during YouTube upload: {e}")
        raise

if __name__ == "__main__":
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    prompts = [
        "A cinematic shot of a bustling futuristic city at sunset with flying cars.",
        "A playful animated squirrel collecting nuts in a whimsical forest.",
        "A serene nature scene with a waterfall and lush greenery.",
    ]

    try:
        youtube = authenticate_youtube()
        print("YouTube API authenticated successfully.")
    except Exception as e:
        print(f"Failed to authenticate YouTube API: {e}")
        print("Workflow cannot proceed without YouTube authentication. Exiting.")
        exit(1)

    for i, prompt in enumerate(prompts):
        video_filename = f"veo_video_{i+1}.mp4"
        video_filepath = os.path.join(VIDEO_OUTPUT_DIR, video_filename)

        print(f"\n--- Processing video {i+1} for prompt: '{prompt}' ---")
        try:
            generated_video_path = generate_veo_video(prompt, video_filepath)

            video_title = f"AI Generated Video: {prompt[:70]}..."
            if len(prompt) > 70:
                video_description = f"This video was generated using Google Veo (Gemini API) from the prompt: '{prompt}'.\n\n#AIvideo #Veo #TextToVideo #Automation #GoogleAI #GeminiAPI"
            else:
                 video_description = f"This video was generated using Google Veo (Gemini API) from the prompt: '{prompt}'. #AIvideo #Veo #TextToVideo #Automation #GoogleAI #GeminiAPI"

            video_tags = ["AI video", "Veo", "Text to Video", "Automation", "Google AI", "Gemini API"]
            video_tags.extend([tag.strip() for tag in prompt.lower().replace('.', '').replace(',', '').split() if len(tag) > 2][:5]) 

            youtube_video_id = upload_youtube_video(
                youtube,
                generated_video_path,
                video_title,
                video_description,
                video_tags,
                "unlisted"
            )
            print(f"Successfully processed video {i+1}. YouTube ID: {youtube_video_id}")

            if os.path.exists(generated_video_path):
                 os.remove(generated_video_path)
                 print(f"Cleaned up local file: {generated_video_path}")

        except Exception as e:
            print(f"A critical error occurred during processing for prompt '{prompt}': {e}")

    print("\n--- Workflow complete ---")
