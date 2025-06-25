# runway_generate.py
import requests
import time
import os

API_KEY = os.environ['RUNWAY_API_KEY']
PROMPT = "Funny video man falling from first floor building holding a microwave"

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

data = {
    "prompt": PROMPT,
    "max_duration": 10
}

response = requests.post("https://api.runwayml.com/v1/generations", headers=headers, json=data)
response.raise_for_status()

job_id = response.json()['id']

# Poll until complete
status_url = f"https://api.runwayml.com/v1/jobs/{job_id}"
while True:
    r = requests.get(status_url, headers=headers)
    status = r.json()
    if status['status'] == 'succeeded':
        video_url = status['output']['video']
        break
    elif status['status'] == 'failed':
        raise RuntimeError("Runway generation failed")
    time.sleep(5)

video_file = "video_output/generated_video.mp4"
with requests.get(video_url, stream=True) as r:
    r.raise_for_status()
    with open(video_file, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
print("🎥 Runway video saved.")
