FROM python:3.12-slim

# Metadata
LABEL maintainer="auto-test-platform"
LABEL description="Automated test execution platform"

# Set working directory
WORKDIR /app

# Install dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create reports output directory
RUN mkdir -p reports

# Expose the dashboard / result-collection port
EXPOSE 5000

# Default command: run all tests
CMD ["python", "main.py"]
