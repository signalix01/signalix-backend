FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including TA-Lib
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    wget \
    postgresql-client \
    libta-lib0 \
    libta-lib-dev \
    libseccomp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib from source for better compatibility
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for algo builder
RUN pip install --no-cache-dir \
    TA-Lib \
    numpy \
    pandas \
    pydantic \
    fastapi \
    uvicorn[standard] \
    redis \
    celery

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8010/health')" || exit 1

# Run the algo builder service
CMD ["uvicorn", "services.algo_builder.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "2"]
