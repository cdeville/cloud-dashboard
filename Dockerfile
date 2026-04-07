# Base stage - common dependencies
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Development stage - uses host UID/GID + AWS CLI
FROM base AS dev

# Install AWS CLI and additional tools for development
RUN apt-get update && apt-get install -y \
    unzip \
    groff \
    less \
    && rm -rf /var/lib/apt/lists/*

# Uncomment the following lines to install AWS CLI v2 in the dev stage
# Install AWS CLI v2
# RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
#     unzip awscliv2.zip && \
#     ./aws/install && \
#     rm -rf aws awscliv2.zip

ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd -r appuser -g ${USER_GID} && \
    useradd -r -g appuser -u ${USER_UID} -d /home/appuser -m appuser

# Change ownership of the app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose Streamlit default port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "Dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]

# AWS/Production stage - uses fixed UID/GID 1000
FROM base AS aws

RUN groupadd -r appuser -g 1000 && \
    useradd -r -g appuser -u 1000 -d /home/appuser -m appuser

# Change ownership of the app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose Streamlit default port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "Dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
