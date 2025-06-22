FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick security policy to allow 'TextClip'
RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml || true \
 && sed -i 's/rights="none" pattern="PS"/rights="read|write" pattern="PS"/' /etc/ImageMagick-6/policy.xml || true \
 && sed -i 's/rights="none" pattern="EPI"/rights="read|write" pattern="EPI"/' /etc/ImageMagick-6/policy.xml || true \
 && sed -i 's/rights="none" pattern="XPS"/rights="read|write" pattern="XPS"/' /etc/ImageMagick-6/policy.xml || true \
 && sed -i 's/rights="none" pattern="MVG"/rights="read|write" pattern="MVG"/' /etc/ImageMagick-6/policy.xml || true

# Set working directory
WORKDIR /app

# Copy all code
COPY . .

# Install Python packages
RUN pip install --no-cache-dir \
    moviepy \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client

# Run script by default (optional)
CMD ["python", "create_video.py"]
