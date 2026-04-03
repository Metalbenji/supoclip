FROM python:3.11-slim AS builder

# Build-time dependencies only (compiler toolchain stays out of runtime image).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# MediaPipe face detector model (baked into image for deterministic runtime behavior)
ARG MEDIAPIPE_FACE_MODEL_URL=https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite
ARG MEDIAPIPE_FACE_MODEL_SHA256=b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f
ENV MEDIAPIPE_FACE_MODEL_PATH=/app/models/blaze_face_short_range.tflite
ENV MEDIAPIPE_FACE_MODEL_URL=${MEDIAPIPE_FACE_MODEL_URL}
ENV MEDIAPIPE_FACE_MODEL_SHA256=${MEDIAPIPE_FACE_MODEL_SHA256}
ENV MEDIAPIPE_FACE_MODEL_AUTO_DOWNLOAD=true

# Copy dependency metadata first to maximize cache hits.
COPY pyproject.toml uv.lock* ./

# Create virtual environment and install dependencies using uv sync.
# `UV_SYNC_EXTRA=worker` installs heavy video/ML deps for worker images.
ARG UV_SYNC_EXTRA=
RUN uv venv .venv \
    && if [ -n "${UV_SYNC_EXTRA}" ]; then \
        uv sync --extra "${UV_SYNC_EXTRA}"; \
    else \
        uv sync; \
    fi

# Torch now defaults to CUDA packages on Linux. For lean worker images, swap
# to the CPU wheel and remove CUDA-only Python packages.
ARG TORCH_VARIANT=default
RUN if [ "${UV_SYNC_EXTRA}" = "worker" ] && [ "${TORCH_VARIANT}" = "cpu" ]; then \
      uv pip uninstall \
        triton \
        nvidia-cublas-cu12 \
        nvidia-cuda-cupti-cu12 \
        nvidia-cuda-nvrtc-cu12 \
        nvidia-cuda-runtime-cu12 \
        nvidia-cudnn-cu12 \
        nvidia-cufft-cu12 \
        nvidia-cufile-cu12 \
        nvidia-curand-cu12 \
        nvidia-cusolver-cu12 \
        nvidia-cusparse-cu12 \
        nvidia-cusparselt-cu12 \
        nvidia-nccl-cu12 \
        nvidia-nvjitlink-cu12 \
        nvidia-nvshmem-cu12 \
        nvidia-nvtx-cu12 \
        torch || true; \
      uv pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.10.0+cpu"; \
    fi

ARG CUDA_NVCC_WHEEL_VERSION=
RUN if [ -n "${CUDA_NVCC_WHEEL_VERSION}" ]; then \
      uv pip install --python .venv/bin/python --no-cache-dir "nvidia-cuda-nvcc-cu12==${CUDA_NVCC_WHEEL_VERSION}"; \
    fi

# Keep yt-dlp at latest to handle upstream site/API changes.
RUN uv pip install --upgrade --force-reinstall --no-cache-dir "yt-dlp[default]"

# Fetch and verify MediaPipe face detector model.
RUN mkdir -p /app/models \
    && curl -fsSL "${MEDIAPIPE_FACE_MODEL_URL}" -o "${MEDIAPIPE_FACE_MODEL_PATH}" \
    && echo "${MEDIAPIPE_FACE_MODEL_SHA256}  ${MEDIAPIPE_FACE_MODEL_PATH}" | sha256sum -c -

COPY src/ ./src/
COPY fonts/ ./fonts/
COPY transitions/ ./transitions/

RUN mkdir -p /app/uploads /app/clips /app/logs /tmp

FROM python:3.11-slim AS runtime

# Runtime-only system packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG MEDIAPIPE_FACE_MODEL_URL=https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite
ARG MEDIAPIPE_FACE_MODEL_SHA256=b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f
ENV MEDIAPIPE_FACE_MODEL_PATH=/app/models/blaze_face_short_range.tflite
ENV MEDIAPIPE_FACE_MODEL_URL=${MEDIAPIPE_FACE_MODEL_URL}
ENV MEDIAPIPE_FACE_MODEL_SHA256=${MEDIAPIPE_FACE_MODEL_SHA256}
ENV MEDIAPIPE_FACE_MODEL_AUTO_DOWNLOAD=true

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/models /app/models
COPY --from=builder /app/src /app/src
COPY --from=builder /app/fonts /app/fonts
COPY --from=builder /app/transitions /app/transitions

ARG CUDA_NVCC_WHEEL_VERSION=
RUN if [ -n "${CUDA_NVCC_WHEEL_VERSION}" ]; then \
      mkdir -p /usr/local/cuda/bin \
      && CUDA_NVCC_BIN_DIR="$(dirname "$(find /app/.venv -path '*/site-packages/nvidia/cuda_nvcc/bin/ptxas' -print -quit)")" \
      && if [ -n "${CUDA_NVCC_BIN_DIR}" ] && [ -d "${CUDA_NVCC_BIN_DIR}" ]; then \
           for tool in "${CUDA_NVCC_BIN_DIR}"/*; do \
             ln -sf "${tool}" "/usr/local/cuda/bin/$(basename "${tool}")"; \
           done; \
         fi; \
    fi

ENV PATH=/usr/local/cuda/bin:${PATH}

RUN mkdir -p /app/uploads /app/clips /app/logs /tmp

EXPOSE 8000

CMD [".venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
