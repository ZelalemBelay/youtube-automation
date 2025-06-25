import os, json
from google.oauth2 import service_account
from google.cloud import aiplatform_v1beta1 as aiplatform

# Setup credentials
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY, scopes=SCOPES)

# Set project and location
project = KEY["project_id"]
location = "us-central1"
endpoint = f"projects/{project}/locations/{location}/publishers/google/models/veo-3.0-generate-preview"

# Create prediction client
client = aiplatform.PredictionServiceClient(credentials=creds)

# Prepare request
instances = [{"prompt": "Funny video man falling from first floor building holding a microwave"}]
parameters = {
    "aspectRatio": "16:9",
    "durationSeconds": 8,
    "generateAudio": True
}

response = client.predict(endpoint=endpoint, instances=instances, parameters=parameters)

# Extract URL
try:
    video_uri = response.predictions[0]["videoUri"]
    print("Generated video URI:", video_uri)

    # Save for later (e.g. for YouTube upload)
    os.makedirs("video_output", exist_ok=True)
    with open("video_output/video_uri.txt", "w") as f:
        f.write(video_uri)

except Exception as e:
    print("Failed to retrieve video URL:", str(e))
