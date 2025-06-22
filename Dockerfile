FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Patch ImageMagick security policy to allow TextClip
RUN sed -i 's/rights="none" pattern="MVG"/rights="read|write" pattern="MVG"/' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir \
    moviepy \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client

CMD ["python", "create_video.py"]
