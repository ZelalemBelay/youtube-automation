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


# --- Configuration ---
# Google AI Studio / Veo API Key (for google-generativeai client)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Veo Model Name (as per Google's documentation for google-generativeai)
VEO_MODEL_NAME_GENAI = "veo-2.0-generate-001" # Double-check this on Google's official Veo documentation

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
        model = genai.GenerativeModel(model_name=VEO_MODEL_NAME_GENAI) 

        # --- CRITICAL FIX HERE: NEST VIDEO-SPECIFIC PARAMETERS ---
        # The 'aspect_ratio' and other video parameters need to be nested
        # under a 'video_generation_parameters' key within the generation_config.
        generation_config = {
            "video_generation_parameters": { # This is the new nesting
                "aspect_ratio": "16:9",
                "person_generation": "dont_allow",
                "number_of_videos": 1,
                "duration_seconds": 8, # Ensure this is within Veo's limits (e.g., 5-8s for Veo 2)
                # "negative_prompt": "blurry, low quality, bad composition",
                # "audio_description": "sound of rain", # For Veo 3 if applicable
            },
            # Any other general generation config params go here if needed
            # For example, safety settings etc., though often handled at top-level configure() or request
            # "candidate_count": 1 # Example if you want more candidates
        }
        
        print("Sending video generation request to Veo (this may take a few minutes)...")
        # For Veo models, the method might specifically be client.models.generate_videos
        # However, generate_content is common for multimodal models. Let's stick with generate_content
        # as it was causing the 'Unknown field' error, implying the model was hit correctly.
        operation = model.generate_content(
            prompt,
            generation_config=generation_config, # Now with nested parameters
        )
        
        while not operation.done:
            print("Video generation in progress... (waiting 20s)")
            time.sleep(20)
            operation = client.operations.get(operation.name) # Correct way to reload operation state

        if operation.error:
            raise Exception(f"Veo generation failed with error: {operation.error.message}")
        
        generated_video_url = None
        # Trying to extract video URL based on common patterns.
        # The exact path can still vary, inspecting the 'operation.result()' object is key.
        
        # Pattern 1: Direct generated_videos list on the result object
        if hasattr(operation.result(), 'generated_videos') and operation.result().generated_videos:
            if hasattr(operation.result().generated_videos[0], 'video') and hasattr(operation.result().generated_videos[0].video, 'uri'):
                generated_video_url = operation.result().generated_videos[0].video.uri
        
        # Pattern 2: Nested under candidates -> content -> parts -> file_data or video_uri
        # This is more common for generic multimodal outputs
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
