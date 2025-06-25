import os, json, time
from google.oauth2 import service_account
from google.cloud import aiplatform_v1beta1

# Load credentials from GitHub Secret
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY)

# Setup project and client
project = KEY["project_id"]
location = "us-central1"
client = aiplatform_v1beta1.PredictionServiceClient(credentials=creds)

# Format endpoint and model
endpoint = f"projects/{project}/locations/{location}/publishers/google/models/veo-3.0-generate-preview"

# Prompt and generation parameters
instances = [{"prompt": "Funny video man falling from first floor building holding a microwave"}]
parameters = {
    "durationSeconds": 8,
    "aspectRatio": "16:9",
    "generateAudio": True
}

# Start long-running prediction
operation = client.long_running_predict(
    endpoint=endpoint,
    instances=instances,
    parameters=parameters,
)

print("🟡 Waiting for video to finish rendering...")
while not operation.done():
    time.sleep(20)
    operation = client._transport.operations_client.get_operation(name=operation.operation.name)

# Parse response
response = operation.response
video_uri = response.predictions[0]["videoUri"]
print("✅ Generated video URL:", video_uri)

# Save to file
os.makedirs("video_output", exist_ok=True)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_uri)
