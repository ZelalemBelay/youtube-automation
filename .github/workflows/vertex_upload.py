from google.cloud import aiplatform # or specific modules within aiplatform for Veo
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import pickle

# --- Configuration ---
# Veo API
VEO_API_KEY = "AIzaSyArHBF4m6Z99imW-7J6Wq9bHs9n-BrKSI4" # Or configure authentication for Vertex AI
VEO_MODEL = "veo-2.0-generate-001" # Or veo-3.0-generate-preview
VIDEO_OUTPUT_DIR = "generated_videos"

# YouTube API
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22" # Example: People & Blogs

def authenticate_youtube():
    """Authenticates with YouTube Data API using OAuth 2.0."""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)

def generate_veo_video(prompt: str, output_path: str):
    """Generates a video using Veo and saves it to output_path."""
    print(f"Generating video for prompt: '{prompt}'...")
    veo_client = VeoClient(api_key=VEO_API_KEY) # Replace if using Vertex AI directly

    operation = veo_client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=VeoTypes.GenerateVideosConfig(
            aspect_ratio="16:9",
            duration_seconds=8, # Max 8 seconds for Veo 3 previews, check API docs for longer
            number_of_videos=1,
            # Add other config like negativePrompt, personGeneration etc.
        ),
    )

    # Poll for operation completion (Veo generation can take time)
    while not operation.done:
        print("Video generation in progress...")
        operation = veo_client.operations.get(operation.name) # Refresh operation status
        import time
        time.sleep(20) # Wait 20 seconds before checking again

    generated_video_url = operation.result().generated_videos[0].uri # Assuming one video generated
    print(f"Video generated! Downloading from: {generated_video_url}")

    # Download the video
    import requests
    response = requests.get(generated_video_url, stream=True)
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Video downloaded to: {output_path}")
    return output_path

def upload_youtube_video(youtube_service, video_path: str, title: str, description: str, tags: list, privacy_status: str):
    """Uploads a video to YouTube."""
    print(f"Uploading video '{title}' to YouTube...")
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

    media_body = MediaFileUpload(video_path, chunksize=-1, resumable=True) # -1 for single HTTP request if reliable connection

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

    print(f"Video uploaded! Video ID: {response.get('id')}")
    print(f"YouTube URL: https://www.youtube.com/watch?v={response.get('id')}")
    return response.get('id')

if __name__ == "__main__":
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    # --- Main Workflow ---
    prompts = [
        "A cinematic shot of a bustling futuristic city at sunset with flying cars.",
        "A playful animated squirrel collecting nuts in a whimsical forest.",
        "A serene nature scene with a waterfall and lush greenery.",
    ]

    youtube = authenticate_youtube()

    for i, prompt in enumerate(prompts):
        video_filename = f"veo_video_{i+1}.mp4"
        video_filepath = os.path.join(VIDEO_OUTPUT_DIR, video_filename)

        try:
            generated_video_path = generate_veo_video(prompt, video_filepath)

            # Generate dynamic title, description, tags based on prompt or other logic
            video_title = f"AI Generated Video: {prompt[:50]}..."
            video_description = f"This video was generated using Google Veo Flow from the prompt: '{prompt}'. #AIvideo #VeoFlow #YouTubeAutomation"
            video_tags = ["AI video", "Veo Flow", "Text to Video", "Automation", "Google AI"]

            youtube_video_id = upload_youtube_video(
                youtube,
                generated_video_path,
                video_title,
                video_description,
                video_tags,
                "unlisted" # Set to "public" after testing
            )
            print(f"Successfully processed video {i+1}. YouTube ID: {youtube_video_id}")

            # Optional: Clean up local video file after upload
            # os.remove(generated_video_path)

        except Exception as e:
            print(f"Error processing video for prompt '{prompt}': {e}")

    print("Workflow complete.")
