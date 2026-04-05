from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    def __init__(self):
        def env_bool(name: str, default: str = "false") -> bool:
            return (os.getenv(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}

        # Backward compatible env handling:
        # - prefer the documented vars (LLM, WHISPER_MODEL_SIZE)
        # - still accept legacy names used in older revisions
        self.whisper_model = os.getenv("WHISPER_MODEL_SIZE") or os.getenv("WHISPER_MODEL", "medium")
        self.whisper_device = (os.getenv("WHISPER_DEVICE", "auto") or "auto").strip().lower()
        raw_whisper_gpu_index = os.getenv("WHISPER_GPU_INDEX")
        if raw_whisper_gpu_index is None or not raw_whisper_gpu_index.strip():
            self.whisper_gpu_index = None
        else:
            try:
                parsed_gpu_index = int(raw_whisper_gpu_index)
            except ValueError:
                parsed_gpu_index = None
            self.whisper_gpu_index = parsed_gpu_index if parsed_gpu_index is None or parsed_gpu_index >= 0 else None
        self.whisper_chunking_enabled = env_bool("WHISPER_CHUNKING_ENABLED", "true")
        self.whisper_chunk_duration_seconds = int(os.getenv("WHISPER_CHUNK_DURATION_SECONDS", "1200"))
        self.whisper_chunk_overlap_seconds = int(os.getenv("WHISPER_CHUNK_OVERLAP_SECONDS", "8"))
        self.transcription_provider = (os.getenv("TRANSCRIPTION_PROVIDER", "local") or "local").strip().lower()
        self.llm = os.getenv("LLM") or os.getenv("LLM_MODEL") or "openai:gpt-5-mini"
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.zai_api_key = os.getenv("ZAI_API_KEY")
        raw_ollama_base_url = os.getenv("OLLAMA_BASE_URL")
        self.ollama_base_url = raw_ollama_base_url.strip() if isinstance(raw_ollama_base_url, str) and raw_ollama_base_url.strip() else None
        self.ollama_timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "15"))
        self.ollama_max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))
        self.ollama_retry_backoff_ms = int(os.getenv("OLLAMA_RETRY_BACKOFF_MS", "400"))
        self.assembly_ai_api_key = os.getenv("ASSEMBLY_AI_API_KEY")
        self.admin_api_key = os.getenv("ADMIN_API_KEY")
        self.secret_encryption_key = os.getenv("SECRET_ENCRYPTION_KEY")

        self.max_video_duration = int(os.getenv("MAX_VIDEO_DURATION", "3600"))
        self.output_dir = os.getenv("OUTPUT_DIR", "outputs")

        self.max_clips = int(os.getenv("MAX_CLIPS", "10"))
        self.clip_duration = int(os.getenv("CLIP_DURATION", "30"))  # seconds
        self.clip_diversity_enabled = env_bool("CLIP_DIVERSITY_ENABLED", "true")
        self.clip_diversity_min_gap_seconds = max(0, int(os.getenv("CLIP_DIVERSITY_MIN_GAP_SECONDS", "600")))
        self.clip_diversity_buckets = max(1, int(os.getenv("CLIP_DIVERSITY_BUCKETS", "4")))

        self.temp_dir = os.getenv("TEMP_DIR", "temp")
        raw_ytdlp_cookies_file = os.getenv("YTDLP_COOKIES_FILE")
        self.ytdlp_cookies_file = (
            raw_ytdlp_cookies_file.strip()
            if isinstance(raw_ytdlp_cookies_file, str) and raw_ytdlp_cookies_file.strip()
            else None
        )

        # Redis configuration
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.worker_max_jobs = int(os.getenv("WORKER_MAX_JOBS", "2"))
        self.worker_job_timeout_seconds = int(os.getenv("WORKER_JOB_TIMEOUT_SECONDS", "21600"))
        self.enable_gpu_worker = env_bool("ENABLE_GPU_WORKER", "false")
        self.arq_queue_name = (os.getenv("ARQ_QUEUE_NAME", "arq:queue:local") or "arq:queue:local").strip()
        self.arq_local_queue_name = (os.getenv("ARQ_QUEUE_NAME_LOCAL", "arq:queue:local") or "arq:queue:local").strip()
        self.arq_local_gpu_queue_name = (
            os.getenv("ARQ_QUEUE_NAME_LOCAL_GPU", "arq:queue:local-gpu") or "arq:queue:local-gpu"
        ).strip()
        self.arq_assembly_queue_name = (os.getenv("ARQ_QUEUE_NAME_ASSEMBLY", "arq:queue:assembly") or "arq:queue:assembly").strip()

        backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.mediapipe_face_model_path = (
            os.getenv("MEDIAPIPE_FACE_MODEL_PATH")
            or os.path.join(backend_root, "models", "blaze_face_short_range.tflite")
        )
        self.mediapipe_face_model_url = (
            os.getenv("MEDIAPIPE_FACE_MODEL_URL")
            or "https://storage.googleapis.com/mediapipe-models/face_detector/"
               "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
        )
        self.mediapipe_face_model_sha256 = (
            os.getenv("MEDIAPIPE_FACE_MODEL_SHA256")
            or "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f"
        ).strip().lower()
        self.mediapipe_face_model_auto_download = (
            os.getenv("MEDIAPIPE_FACE_MODEL_AUTO_DOWNLOAD", "true") or "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
