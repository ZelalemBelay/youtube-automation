from google.oauth2 import service_account
from google.cloud import aiplatform_v1beta1
import os, json, time

# Load credentials from GitHub Secret
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY)

project = KEY["project_id"]
location = "us-central1"
model = "projects/google/models/veo-3.0-generate-preview"
parent = f"projects/{project}/locations/{location}"

# Initialize client
client = aiplatform_v1beta1.PredictionServiceClient(credentials=creds)

prompt = "Funny video man falling from first floor building holding a microwave"

# Set up instance and parameters
instances = [{"prompt": prompt}]
parameters = {
    "durationSeconds": 8,
    "aspectRatio": "16:9",
    "generateAudio": True
}

endpoint = f"https://{location}-aiplatform.googleapis.com/v1beta1/{model}:predict"

# Call the prediction endpoint
response = client.predict(
    endpoint=endpoint,
    instances=instances,
    parameters=parameters
)

# Extract and store the video URL
video_uri = response.predictions[0]["videoUri"]

print("Generated video URI:", video_uri)
os.makedirs("video_output", exist_ok=True)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_uri)
