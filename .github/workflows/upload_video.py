import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Define the YouTube upload scope
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Get secrets from environment variables (you should store these in GitHub Actions secrets)
client_id = os.environ['YT_CLIENT_ID']
client_secret = os.environ['YT_CLIENT_SECRET']
refresh_token = os.environ['YT_REFRESH_TOKEN']

# Authenticate using refresh token
creds = Credentials(
    None,
    refresh_token=refresh_token,
    token_uri='https://oauth2.googleapis.com/token',
    client_id=client_id,
    client_secret=client_secret,
    scopes=SCOPES,
)

# Build YouTube API client
youtube = build('youtube', 'v3', credentials=creds)

# Define the video metadata
request_body = {
    'snippet': {
        'title': 'Funny microwave fall 😂',
        'description': 'Auto-generated video',
        'tags': ['funny', 'microwave', 'fall', 'AI'],
        'categoryId': '23'  # 23 = Comedy
    },
    'status': {
        'privacyStatus': 'public'
    }
}

# Load the video file
media = MediaFileUpload('final_news.mp4', mimetype='video/mp4', resumable=True)

# Upload to YouTube
response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"✅ Uploaded Video ID: {response['id']}")