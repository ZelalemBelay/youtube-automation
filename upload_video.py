import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Load credentials from saved refresh token
client_id = os.environ['YT_CLIENT_ID']
client_secret = os.environ['YT_CLIENT_SECRET']
refresh_token = os.environ['YT_REFRESH_TOKEN']

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
        'title': 'Funny microwave fall 😂',
        'description': 'Auto-generated video',
        'tags': ['funny', 'microwave', 'fall', 'AI'],
        'categoryId': '23'
    },
    'status': {
        'privacyStatus': 'public'
    }
}

media = MediaFileUpload('video_output/generated_video.mp4', mimetype='video/mp4', resumable=True)

response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"Uploaded Video ID: {response['id']}")
