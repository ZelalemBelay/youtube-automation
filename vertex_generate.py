import os, json, time, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# Authenticate with service account
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(
    KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
creds.refresh(Request())

project = KEY["project_id"]
location = "us-central1"
model = "veo-3.0-generate-preview"
url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"

# Prepare request
headers = {
    "Authorization": f"Bearer {creds.token}",
    "Content-Type": "application/json",
}
payload = {
    "prompt": "Funny video man falling from first floor building holding a microwave",
    "generationConfig": {
        "durationSeconds": 8,
        "aspectRatio": "16:9",
        "generateAudio": True
    }
}

# Send generation request
print("📤 Sending generation request...")
res = requests.post(url, headers=headers, json=payload)
if res.status_code != 200:
    print("❌ Error:", res.text)
    exit(1)

operation = res.json()
operation_name = operation["name"]
print("⏳ Operation started:", operation_name)

# Poll the operation
op_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{operation_name}"
while True:
    time.sleep(15)
    poll_res = requests.get(op_url, headers=headers)
    poll_data = poll_res.json()
    if poll_data.get("done"):
        break
    print("⏳ Waiting...")

# Extract video URI
try:
    video_url = poll_data["response"]["generations"][0]["videos"][0]["uri"]
    print("✅ Video generated:", video_url)
except Exception as e:
    print("❌ Failed to extract video URL:", poll_data)
    raise e

# Save to file
os.makedirs("video_output", exist_ok=True)
with open("video_output/video_uri.txt", "w") as f:
    f.write(video_url)
