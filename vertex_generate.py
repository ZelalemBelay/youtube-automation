from google.cloud import aiplatform
from google.oauth2 import service_account
import os, json, time

KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY)

client = aiplatform.gapic.GenerativeServiceClient(credentials=creds)

project = KEY["project_id"]
location = "us-central1"
parent = f"projects/{project}/locations/{location}"

prompt_text = "Funny video man falling from first floor building holding a microwave"

request = {
    "model": "projects/google/models/veo-3.0-generate-preview",
    "prompt": {"text": prompt_text},
    "generation_config": {
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        "generate_audio": True
    },
    "parent": parent
}

operation = client.generate_content(request=request)

print("Waiting for video to finish rendering...")
result = operation.result(timeout=300)  # wait max 5 mins

video_url = result.generations[0].video.uri
print("Generated video URL:", video_url)

os.makedirs("video_output", exist_ok=True)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_url)
