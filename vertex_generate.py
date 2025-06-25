from google.cloud.aiplatform_v1beta1 import GenerativeServiceClient, types
from google.oauth2 import service_account
import os, json, time

# Load credentials
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY)

project = KEY["project_id"]
location = "us-central1"
model = "projects/google/models/veo-3.0-generate-preview"
parent = f"projects/{project}/locations/{location}"

client = GenerativeServiceClient(credentials=creds)

# Request
prompt = "Funny video man falling from first floor building holding a microwave"
request = types.GenerateContentRequest(
    model=model,
    prompt=prompt,
    generation_config=types.GenerationConfig(
        duration_seconds=8,
        aspect_ratio="16:9",
        generate_audio=True,
    )
)

operation = client.generate_content(request=request)
print("🟡 Generating video...")

# Poll until ready
while not operation.done():
    time.sleep(15)
    operation = client._transport.operations_client.get_operation(operation.operation.name)

# Get result
response = operation.response
video_uri = response.generations[0].videos[0].uri
print("✅ Video URI:", video_uri)

# Save locally
os.makedirs("video_output", exist_ok=True)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_uri)
