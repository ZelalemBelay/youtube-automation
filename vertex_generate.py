import os, json, time, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# Load credentials
KEY = json.loads(os.getenv("GCP_SA_KEY"))
creds = service_account.Credentials.from_service_account_info(
    KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
creds.refresh(Request())

# Set constants
project = KEY["project_id"]
location = "us-central1"
model = "veo-3.0-generate-preview"
url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/publishers/google/models/{model}:predict"

# Headers
headers = {
    "Authorization": f"Bearer {creds.token}",
    "Content-Type": "application/json"
}

# Valid JSON payload
payload = {
    "instances": [
        {
            "prompt": "Funny video man falling from first floor building holding a microwave"
        }
    ],
    "parameters": {
        "durationSeconds": 8,
        "aspectRatio": "16:9",
        "generateAudio": True
    }
}

# Send request
print("📤 Sending generation request to Vertex AI Veo...")
res = requests.post(url, headers=headers, json=payload)
if res.status_code != 200:
    print("❌ ERROR:", res.text)
    exit(1)

# Get operation ID
operation = res.json()
operation_name = operation["name"]
print("⏳ Operation started:", operation_name)

# Poll for completion
op_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{operation_name}"
while True:
    time.sleep(30)  # Longer wait to allow full render
    poll_res = requests.get(op_url, headers=headers)
    poll_data = poll_res.json()
    if poll_data.get("done"):
        break
    print("⏳ Still rendering...")

# Extract and save video URL
try:
    video_url = poll_data["response"]["predictions"][0]["videoUri"]
    print("✅ Video ready:", video_url)
    os.makedirs("video_output", exist_ok=True)
    with open("video_output/video_uri.txt", "w") as f:
        f.write(video_url)
except Exception as e:
    print("❌ Failed to get video URI:", poll_data)
    raise e
