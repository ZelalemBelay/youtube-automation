from google.cloud import aiplatform_v1beta1
from google.oauth2 import service_account
import os, json, time

KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY)

client = aiplatform_v1beta1.GenerativeServiceClient(credentials=creds)

project = KEY["project_id"]
location = "us-central1"
model = "projects/google/models/veo-3.0-generate-preview"
parent = f"projects/{project}/locations/{location}"

prompt = "Funny video man falling from first floor building holding a microwave"

request = aiplatform_v1beta1.GenerateContentRequest(
    model=model,
    prompt=prompt,
    generation_config=aiplatform_v1beta1.GenerationConfig(
        duration_seconds=8,
        aspect_ratio="16:9",
        generate_audio=True,
    )
)

operation = client.generate_content(request=request)

print("Waiting for video to finish rendering...")
while not operation.done():
    time.sleep(20)
    operation = client.get_operation(name=operation.operation.name)

response = operation.response
video_url = response.generations[0].videos[0].uri

print("Generated video URL:", video_url)

# Save URL for later use (e.g., upload to YouTube)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_url)
