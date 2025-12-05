FROM python:3.10-slim-bullseye

# Set working directory first
WORKDIR /app/plugins

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install system dependencies in a single layer with cleanup
RUN apt-get update \
    && apt-get install -y \
        build-essential \
        cmake \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        python3-dev \
        curl \
        libkrb5-dev \
        librocksdb-dev \
        libleveldb-dev \
        libsnappy-dev \
        liblz4-dev \
        libbz2-dev \
        zlib1g-dev \
        liblzma-dev \
        git \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && find /usr/share/man -type f -delete \
    && find /usr/share/doc -type f -delete

# Install Python dependencies with retry mechanism
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

# Copy application code after dependencies
COPY . .

ENV ALLOW_ROOT 1
ENV EVENT_LOOP_POLICY="uvloop"

EXPOSE 8000 9000

CMD ["python3", "/app/plugins/main.py"]
