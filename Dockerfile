FROM python:3.10

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

# Set policy for ImageMagick (fixes security restrictions)
RUN echo 'policy.xml fix' && \
    sed -i 's/none/read|write/' /etc/ImageMagick-6/policy.xml || true

# Set working directory
WORKDIR /app

# Copy code
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    moviepy \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client

# Default command to run video creation and upload
CMD ["sh", "-c", "mkdir -p video_output && python create_video.py && python upload_video.py"]
