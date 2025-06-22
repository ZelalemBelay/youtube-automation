FROM python:3.10

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg imagemagick libmagickwand-dev

# Set working dir
WORKDIR /app

# Copy files
COPY . /app

# Install Python packages
RUN pip install --no-cache-dir moviepy google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Default command
CMD ["sh", "-c", "mkdir -p video_output && python create_video.py && python upload_video.py"]
