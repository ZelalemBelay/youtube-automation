import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Load YouTube OAuth credentials from environment
client_id = os.environ['YT_CLIENT_ID']
client_secret = os.environ['YT_CLIENT_SECRET']
refresh_token = os.environ['YT_REFRESH_TOKEN']

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Load video metadata
with open("video_metadata.json", "r") as f:
    metadata = json.load(f)

creds = Credentials(
    None,
    refresh_token=refresh_token,
    token_uri='https://oauth2.googleapis.com/token',
    client_id=client_id,
    client_secret=client_secret,
    scopes=SCOPES,
)

youtube = build('youtube', 'v3', credentials=creds)

request_body = {
    'snippet': {
        'title': metadata['title'],
        'description': metadata['description'],
        'tags': metadata['tags'],
        'categoryId': '25'  # 'News & Politics'
    },
    'status': {
        'privacyStatus': 'public'
    }
}

media = MediaFileUpload('final_news_with_intro.mp4', mimetype='video/mp4', resumable=True)

print(f"📤 Uploading video: {metadata['title']}")
response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"✅ Uploaded Video ID: {response['id']}")