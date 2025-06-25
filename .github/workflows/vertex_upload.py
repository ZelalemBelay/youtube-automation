import os
import pickle
import json # Import json for loading the config from a string
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ... (other imports and configurations) ...

# YouTube API Configuration
# CLIENT_SECRETS_FILE = "client_secrets.json" # Remove this line
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22" # Example: People & Blogs

# Define your client secrets directly in a dictionary
# **WARNING: DO NOT HARDCODE SENSITIVE CREDENTIALS IN PRODUCTION CODE**
# This is for demonstration of "inline" secrets only.
# Replace with your actual values from your client_secrets.json
YOUTUBE_CLIENT_CONFIG = {
    "installed": { # Or "web" if it's a Web Application type client
        "client_id": "381781776567-eoohs8g5arqj0psg7j53tfspqb09fph7.apps.googleusercontent.com",
        "project_id": "youtube-auto-uploader-463700", # This might not be strictly necessary for InstalledAppFlow, but good practice
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "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",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"] # Important for installed apps
    }
}


def authenticate_youtube():
    """Authenticates with YouTube Data API using OAuth 2.0."""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use from_client_config instead of from_client_secrets_file
            flow = InstalledAppFlow.from_client_config(
                YOUTUBE_CLIENT_CONFIG, SCOPES
            )
            # For GitHub Actions, you cannot run a local server or open a browser.
            # You *must* have a pre-authorized refresh token.
            # This part below handles the initial authorization, which needs to be done once manually.
            # For automation, you'll skip run_local_server and directly use a stored refresh token.
            print("Please perform initial authentication manually:")
            auth_url, _ = flow.authorization_url(prompt='consent')
            print(f"Please go to this URL and authorize the app: {auth_url}")
            # This will fail in GitHub Actions unless you provide the code via input/env, which is complex.
            # For automation, you usually pre-authorize and save the token.pickle.
            # We'll discuss this better approach next.
            # For now, if you are forced to run this interactively once to get a token.pickle:
            # code = input("Enter the authorization code: ")
            # flow.fetch_token(code=code)
            # creds = flow.credentials
            # print("Authentication successful. Credentials saved to token.pickle.")

            # IMPORTANT: For GitHub Actions, you NEED a pre-existing token.pickle
            # or a way to get the refresh token without user interaction.
            # This `flow.run_local_server()` will NOT work in a CI/CD environment.
            # You must generate `token.pickle` once locally and then securely pass
            # the refresh token, or the entire token.pickle content, as a secret.
            raise Exception("Initial YouTube OAuth flow requires user interaction. You must pre-generate `token.pickle` and store its refresh token securely, or use a Service Account for YouTube.")

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)

# ... (rest of your script) ...
