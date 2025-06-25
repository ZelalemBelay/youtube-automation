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

# For Vertex AI (Veo)
# Make sure you have 'google-cloud-aiplatform' installed
from google.cloud import aiplatform
# You might need specific modules like:
# from google.cloud.aiplatform.gapic.schema import predict_pb2
# from google.cloud.aiplatform_v1.services.prediction_service import PredictionServiceClient
# from google.protobuf.struct_pb2 import Value # For passing JSON-like structures as protobuf
# The exact Veo interaction can vary; this uses a common GenerativeModel pattern.

# --- Configuration ---
# Vertex AI/Veo API
# It's highly recommended to get these from GitHub Secrets or environment variables
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "youtube-auto-uploader-463700") # Replace or set via env
LOCATION = os.getenv("GCP_LOCATION", "us-central1") # Or the region where Veo is available

# The Veo model ID. This is a common pattern for Google's generative models.
# Always verify the exact model name from Google's official Veo documentation for Vertex AI.
VEO_MODEL_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/veo-2.0-generate"
# If it's a specific endpoint, you'd use something like:
# VEO_ENDPOINT_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{os.getenv('VEO_ENDPOINT_ID')}"

VIDEO_OUTPUT_DIR = "generated_videos"

# YouTube API Configuration
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22" # Example: People & Blogs (adjust as needed)

# Get YouTube API credentials from environment variables (GitHub Secrets)
CLIENT_ID = os.getenv("YT_CLIENT_ID")
CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN") # This is crucial for non-interactive auth

# --- Initialize Vertex AI SDK ---
# This initializes the client and sets the project/location for subsequent calls.
try:
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"Failed to initialize Vertex AI: {e}")
    print("Please ensure GCP_PROJECT_ID and GCP_LOCATION are set correctly,")
    print("and the Vertex AI API is enabled for your project.")
    # Exit if Vertex AI can't be initialized as Veo won't work
    exit(1)


def authenticate_youtube():
    """
    Authenticates with YouTube Data API using OAuth 2.0.
    Prioritizes loading from token.pickle, then uses refresh token from environment.
    This function is designed for a non-interactive CI/CD environment.
    """
    creds = None
    token_pickle_path = "token.pickle"

    # 1. Try to load existing credentials from token.pickle (if it exists from a previous run)
    if os.path.exists(token_pickle_path):
        try:
            with open(token_pickle_path, "rb") as token:
                creds = pickle.load(token)
            print("Loaded credentials from token.pickle.")
        except Exception as e:
            print(f"Error loading token.pickle: {e}. Will attempt to create new credentials.")
            creds = None # Reset creds if loading fails

    # 2. If no valid creds, or existing ones expired, use refresh token from environment variables
    if not creds or not creds.valid:
        # If existing creds are expired but have a refresh token, refresh them
        if creds and creds.expired and creds.refresh_token:
            print("Existing credentials expired, attempting to refresh...")
            try:
                creds.refresh(Request())
                print("Credentials refreshed successfully.")
            except Exception as e:
                print(f"Failed to refresh credentials: {e}. Will attempt to create new ones from environment variables.")
                creds = None
        
        # If still no valid creds after refresh attempt, try to build from environment variables
        if not creds and all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
            print("Creating new credentials from environment variables (Client ID, Client Secret, Refresh Token)...")
            try:
                creds = Credentials(
                    token=None,  # No initial access token needed, will be refreshed
                    refresh_token=REFRESH_TOKEN,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=SCOPES
                )
                creds.refresh(Request()) # Force an immediate refresh to get an access token
                print("Credentials created and refreshed using environment variables.")
            except Exception as e:
                print(f"Failed to create credentials from environment variables: {e}")
                creds = None

        # 3. If after all attempts, no valid credentials could be obtained, raise an error
        if not creds:
            raise Exception(
                "YouTube OAuth credentials missing or invalid. "
                "Ensure YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
                "and YOUTUBE_REFRESH_TOKEN are correctly set as GitHub Secrets. "
                "The REFRESH_TOKEN must be obtained via a *one-time local interactive authentication*."
            )

    # Save the updated credentials (including new access token) to token.pickle
    # This is important for subsequent runs to quickly load fresh credentials
    try:
        with open(token_pickle_path, "wb") as token:
            pickle.dump(creds, token)
        print("Credentials saved/updated in token.pickle.")
    except Exception as e:
        print(f"Warning: Could not save credentials to token.pickle: {e}")

    return build("youtube", "v3", credentials=creds)


def generate_veo_video(prompt: str, output_path: str):
    """Generates a video using Veo (Vertex AI) and saves it to output_path."""
    print(f"Generating video for prompt: '{prompt}' using Vertex AI Veo...")

    try:
        # Use GenerativeModel for Veo (as per latest patterns for Google's generative models)
        # The 'preview' namespace is crucial for pre-GA models like Veo.
        model = aiplatform.preview.generative_models.GenerativeModel(model_name="veo-2.0-generate")

        # The input structure for Veo. Refer to latest Veo API docs for exact parameters.
        # This is based on typical generative model API structures.
        generation_config = {
            "aspectRatio": "16:9",
            "durationSeconds": 8, # Max 8 seconds for single prompt in preview, check docs
            "numberOfVideos": 1,
            # If your Veo model supports persona generation or other features:
            # "personGeneration": "dont_allow",
            # "negativePrompt": "blurry, low quality"
            # For Veo 3 with audio: "audio_description": "sound of rain"
        }

        # Make the prediction call
        # The content can be a string or a list of parts.
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )

        # Poll for operation completion if the response is an Operation
        # (This is typical for long-running generative tasks like video generation)
        if hasattr(response, 'operation') and response.operation:
            print("Veo generation initiated, polling for completion...")
            operation = response.operation # Get the operation object
            # The wait_until_done() method polls until the operation is complete or fails
            operation.wait_until_done()
            
            if operation.done():
                if operation.error:
                    raise Exception(f"Veo generation failed with error: {operation.error.message}")
                
                # The actual generated video URL will be in the operation.result()
                generated_video_uri = None
                if hasattr(operation.result(), 'generated_videos') and operation.result().generated_videos:
                    # Assuming the first video in the list
                    generated_video_uri = operation.result().generated_videos[0].uri
                elif hasattr(operation.result(), 'video_uri'): # Another possibility
                    generated_video_uri = operation.result().video_uri
                
                if not generated_video_uri:
                    raise ValueError("Could not find video URI in Veo response operation result.")
                
                generated_video_url = generated_video_uri # Assume URI is directly downloadable URL
            else:
                raise Exception("Veo generation operation did not complete successfully.")

        else: # This block is for direct responses, less common for video generation but kept as a fallback
            print("Veo generation returned a direct response (not an operation).")
            generated_video_url = None
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
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
                raise ValueError("Could not find video URL in direct Veo response.")

        print(f"Video generated! Downloading from: {generated_video_url}")

        # Download the video
        download_response = requests.get(generated_video_url, stream=True)
        download_response.raise_for_status() # Raise an exception for HTTP errors
        with open(output_path, 'wb') as f:
            for chunk in download_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Video downloaded to: {output_path}")
        return output_path

    except Exception as e:
        print(f"Error during Veo video generation for prompt '{prompt}': {e}")
        raise # Re-raise to stop the pipeline if generation fails

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

        # For large files, resumable upload is key. chunksize=-1 attempts to upload in one go.
        media_body = MediaFileUpload(video_path, chunksize=-1, resumable=True)

        request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media_body
        )

        response = None
        # This loop handles the actual upload and progress reporting
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")

        video_id = response.get('id')
        youtube_url = f"http://www.youtube.com/watch?v={video_id}" # Standard YouTube URL format

        print(f"Video uploaded! Video ID: {video_id}")
        print(f"YouTube URL: {youtube_url}")
        return video_id

    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred during YouTube upload:\n{e.content}")
        raise # Re-raise to propagate the error
    except Exception as e:
        print(f"An unexpected error occurred during YouTube upload: {e}")
        raise # Re-raise to propagate the error

if __name__ == "__main__":
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    # --- Main Workflow ---
    prompts = [
        "A cinematic shot of a bustling futuristic city at sunset with flying cars.",
        "A playful animated squirrel collecting nuts in a whimsical forest.",
        "A serene nature scene with a waterfall and lush greenery.",
    ]

    # Authenticate YouTube API
    try:
        youtube = authenticate_youtube()
        print("YouTube API authenticated successfully.")
    except Exception as e:
        print(f"Failed to authenticate YouTube API: {e}")
        print("Workflow cannot proceed without YouTube authentication. Exiting.")
        exit(1) # Exit if YouTube authentication fails

    for i, prompt in enumerate(prompts):
        video_filename = f"veo_video_{i+1}.mp4"
        video_filepath = os.path.join(VIDEO_OUTPUT_DIR, video_filename)

        print(f"\n--- Processing video {i+1} for prompt: '{prompt}' ---")
        try:
            # Generate video using Veo
            generated_video_path = generate_veo_video(prompt, video_filepath)

            # Generate dynamic title, description, tags
            video_title = f"AI Generated Video: {prompt[:70]}..." # Truncate for title length
            if len(prompt) > 70:
                video_description = f"This video was generated using Google Veo (Vertex AI) from the prompt: '{prompt}'.\n\n#AIvideo #Veo #TextToVideo #Automation #GoogleAI #VertexAI"
            else:
                 video_description = f"This video was generated using Google Veo (Vertex AI) from the prompt: '{prompt}'. #AIvideo #Veo #TextToVideo #Automation #GoogleAI #VertexAI"

            video_tags = ["AI video", "Veo", "Text to Video", "Automation", "Google AI", "Vertex AI"]
            # Add more specific tags based on the prompt content if possible
            video_tags.extend([tag.strip() for tag in prompt.lower().replace('.', '').replace(',', '').split() if len(tag) > 2][:5]) # Add first 5 words of prompt as tags

            # Upload to YouTube
            youtube_video_id = upload_youtube_video(
                youtube,
                generated_video_path,
                video_title,
                video_description,
                video_tags,
                "unlisted" # Set to "public" after thorough testing!
            )
            print(f"Successfully processed video {i+1}. YouTube ID: {youtube_video_id}")

            # Optional: Clean up local video file after successful upload
            if os.path.exists(generated_video_path):
                 os.remove(generated_video_path)
                 print(f"Cleaned up local file: {generated_video_path}")

        except Exception as e:
            print(f"A critical error occurred during processing for prompt '{prompt}': {e}")
            # Depending on your needs, you might want to `exit(1)` here to fail the workflow
            # or `continue` to try the next video. For now, it will print and continue.

    print("\n--- Workflow complete ---")
