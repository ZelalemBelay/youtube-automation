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

# For Vertex AI (Veo) - Using PredictionServiceClient
# Make sure you have 'google-cloud-aiplatform' installed
from google.cloud import aiplatform
from google.cloud.aiplatform_v1.services.prediction_service import PredictionServiceClient
from google.cloud.aiplatform_v1.types import predict as aiplatform_predict_types # For PredictRequest type
from google.protobuf.struct_pb2 import Value # For passing JSON-like structures as protobuf
from google.protobuf import json_format # For parsing dicts into protobuf Value

# --- Configuration ---
# Google Cloud Project ID and Location (REQUIRED for Vertex AI)
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-gcp-project-id") # Set your Google Cloud Project ID as a GitHub Secret
LOCATION = os.getenv("GCP_LOCATION", "us-central1") # Set your GCP region (e.g., 'us-central1', 'europe-west4')

# Veo Prediction Endpoint ID (CRITICAL for this approach)
# You MUST find this in your Google Cloud Console -> Vertex AI -> Generative AI -> Model Garden (or similar Veo/Video AI section)
# If Veo is a preview, Google might provide a specific endpoint for it.
VEO_ENDPOINT_ID = os.getenv("VEO_ENDPOINT_ID", "your-veo-prediction-endpoint-id") # Set this as a GitHub Secret
VEO_ENDPOINT_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{VEO_ENDPOINT_ID}"

VIDEO_OUTPUT_DIR = "generated_videos"

# YouTube API Configuration
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22" # Example: People & Blogs (adjust as needed for your content)

# Get YouTube API credentials from environment variables (GitHub Secrets)
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")


# --- Initialize Vertex AI SDK ---
# This initializes the client and sets the project/location for subsequent calls.
try:
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
    print(f"Vertex AI SDK initialized for project '{PROJECT_ID}' in location '{LOCATION}'.")
except Exception as e:
    print(f"Failed to initialize Vertex AI SDK: {e}")
    print("Please ensure GCP_PROJECT_ID and GCP_LOCATION are set correctly as GitHub Secrets,")
    print("and the Vertex AI API is enabled for your project.")
    exit(1)


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
    """Generates a video using Veo via Vertex AI PredictionServiceClient."""
    print(f"Generating video for prompt: '{prompt}' using Vertex AI Veo...")

    # Ensure VEO_ENDPOINT_ID is set if we're using this path
    if not VEO_ENDPOINT_ID or VEO_ENDPOINT_ID == "your-veo-prediction-endpoint-id":
        raise ValueError("VEO_ENDPOINT_ID is not set or is default. Please configure it in GitHub Secrets.")

    try:
        # Initialize the prediction service client
        client_options = {"api_endpoint": f"{LOCATION}-aiplatform.googleapis.com"}
        client = PredictionServiceClient(client_options=client_options)

        # Prepare the instance for the prediction request.
        # The exact structure of this payload MUST be verified with Google's official Veo documentation for Vertex AI Prediction API.
        # This is a common pattern for Vertex AI custom models/endpoints.
        instance_dict = {
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "person_generation": "dont_allow", # "dont_allow" or "allow_adult" or "allow_all"
            "number_of_videos": 1, 
            "duration_seconds": 8, # Ensure this is within Veo's limits (e.g., 5-8s for Veo 2)
            # "negative_prompt": "blurry, low quality, bad composition", # Optional
            # "audio_description": "sound of rain", # For Veo 3 if applicable
        }
        
        instance_proto = json_format.ParseDict(instance_dict, Value())

        # The prediction request
        # This calls the deployed Veo endpoint.
        request = aiplatform_predict_types.PredictRequest(
            endpoint=VEO_ENDPOINT_NAME, # This is the full resource name of your Veo endpoint
            instances=[instance_proto]
            # You might need to add 'parameters' here if the model expects them separately, e.g.:
            # parameters=json_format.ParseDict({}, Value())
        )

        print("Sending video generation request to Veo (this may take a few minutes)...")
        # Make the prediction call. This method typically returns a synchronous response for predictions,
        # but for long-running generative tasks, the response itself might contain an operation ID
        # that needs to be polled, or the API call implicitly handles it.
        response = client.predict(request=request)

        # IMPORTANT: The way to extract the video URL will depend ENTIRELY
        # on the structure of `response.predictions`.
        # You WILL need to print `response.predictions` in a test run to inspect its structure.
        generated_video_url = None
        if response.predictions:
            # Assuming the video URL is in the first prediction's first generated video URI
            # This is highly speculative and needs verification from Veo API response examples.
            prediction_dict = json_format.MessageToDict(response.predictions[0])
            
            # Common patterns for video URL extraction:
            if 'generated_videos' in prediction_dict and prediction_dict['generated_videos']:
                generated_video_url = prediction_dict['generated_videos'][0].get('uri')
            elif 'video_uri' in prediction_dict: # Another possibility
                generated_video_url = prediction_dict['video_uri']
            elif 'file_data' in prediction_dict and 'file_uri' in prediction_dict['file_data']: # Yet another
                generated_video_url = prediction_dict['file_data']['file_uri']
            
        if not generated_video_url:
            # Print the full predictions object to debug its structure if URL is not found
            print(f"DEBUG: Veo Prediction Response: {json_format.MessageToDict(response.predictions)}")
            raise ValueError("Could not find video URL in Veo prediction response. Response structure unknown or generation failed.")

        print(f"Veo video generated! Downloading from: {generated_video_url}")

        # For Vertex AI generated URLs, you typically don't need to append the API key to download.
        # This is more common with Google AI Studio (genai library) direct URLs.
        download_response = requests.get(generated_video_url, stream=True)
        download_response.raise_for_status() # Raise an exception for HTTP errors
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
                video_description = f"This video was generated using Google Veo (Vertex AI) from the prompt: '{prompt}'.\n\n#AIvideo #Veo #TextToVideo #Automation #GoogleAI #VertexAI"
            else:
                 video_description = f"This video was generated using Google Veo (Vertex AI) from the prompt: '{prompt}'. #AIvideo #Veo #TextToVideo #Automation #GoogleAI #VertexAI"

            video_tags = ["AI video", "Veo", "Text to Video", "Automation", "Google AI", "Vertex AI"]
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
