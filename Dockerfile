FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick security policy (allows moviepy to use TextClip)
RUN sed -i 's/none/read|write/' /etc/ImageMagick-6/policy.xml || true

# Set workdir and copy files
WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    moviepy \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client

# Default command for test
CMD ["python", "create_video.py"]
