import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# --- Configuration ---
METADATA_FILE = "video_metadata.json"
# This should be the final merged video file ready for upload
VIDEO_FILE_TO_UPLOAD = "final_content_shorts.mp4"

# Load YouTube OAuth credentials from environment
client_id = os.environ['YT_CLIENT_ID']
client_secret = os.environ['YT_CLIENT_SECRET']
refresh_token = os.environ['YT_REFRESH_TOKEN']

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# --- Main Upload Logic ---

# 1. Load video metadata from the file
print(f"📄 Loading metadata from {METADATA_FILE}...")
with open(METADATA_FILE, "r") as f:
    metadata = json.load(f)

# 2. Prepare credentials
creds = Credentials(
    None,
    refresh_token=refresh_token,
    token_uri='https://oauth2.googleapis.com/token',
    client_id=client_id,
    client_secret=client_secret,
    scopes=SCOPES,
)

youtube = build('youtube', 'v3', credentials=creds)

# 3. **MODIFICATION: Add #Shorts to the title**
# This is the crucial step to ensure the video is categorized as a Short.
base_title = metadata['title']
shorts_tag = "#Shorts"
youtube_title_limit = 100

# Add the #Shorts tag only if it's not already in the title
if shorts_tag.lower() not in base_title.lower():
    # Check if adding the tag would exceed YouTube's 100-character limit
    if len(base_title) + len(shorts_tag) + 1 > youtube_title_limit:
        # If so, truncate the base title to make space
        available_length = youtube_title_limit - (len(shorts_tag) + 1) # +1 for the space
        final_title = f"{base_title[:available_length]} {shorts_tag}"
    else:
        # Otherwise, just append the tag
        final_title = f"{base_title} {shorts_tag}"
else:
    final_title = base_title # The title already contains the tag

print(f"✅ Final video title set to: '{final_title}'")


# 4. Construct the request body for the YouTube API
request_body = {
    'snippet': {
        'title': final_title, # Use the modified title
        'description': metadata['description'],
        'tags': metadata['tags'],
        'categoryId': '25'  # 'News & Politics'
    },
    'status': {
        'privacyStatus': 'public' # Change to 'private' or 'unlisted' for testing
    }
}

# 5. Prepare the media file for upload
media = MediaFileUpload(VIDEO_FILE_TO_UPLOAD, mimetype='video/mp4', resumable=True)

# 6. Execute the upload
print(f"📤 Uploading '{VIDEO_FILE_TO_UPLOAD}' to YouTube...")
response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"✅ Upload successful! Video ID: {response['id']}")
print(f"🔗 Link: https://www.youtube.com/watch?v={response['id']}")