import os, time, json
from google.oauth2 import service_account
from google.cloud import aiplatform

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(KEY, scopes=SCOPES)

client = aiplatform.gapic.JobServiceClient(credentials=creds)
project = KEY["project_id"]
location = "us-central1"
model = "projects/{}/locations/{}/publishers/google/models/veo-3.0-generate-preview".format(project, location)

prompt = "Funny video man falling from first floor building holding a microwave"

request = {
    "model": model,
    "instances": [{"prompt": prompt}],
    "parameters": {"aspectRatio": "16:9", "durationSeconds": 8, "generateAudio": True}
}

operation = client.predict(request=request)
print("Operation started:", operation.operation.name)

op_client = aiplatform.gapic.OperationsClient(credentials=creds)
while not operation.done():
    time.sleep(20)
    operation = op_client.get_operation(name=operation.operation.name)
print("Done!")

videos = operation.response.generations[0].videos
url = videos[0].uri
print("Generated video URI:", url)

# Download via GCS (if needed). For simplicity, store URI for later upload.
with open("video_output/video_uri.txt", "w") as f:
    f.write(url)
