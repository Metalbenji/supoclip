"""
Utility functions for YouTube-related operations.
Optimized for high-quality downloads and better error handling.
"""

import re
from urllib.parse import urlparse, parse_qs
import yt_dlp
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import logging
import time

from .config import Config

logger = logging.getLogger(__name__)
config = Config()
YOUTUBE_AUTH_ERROR_MARKERS = (
    "sign in to confirm you're not a bot",
    "use --cookies-from-browser or --cookies",
    "login required",
    "confirm you're not a bot",
)


class YouTubeDownloadError(RuntimeError):
    """Raised when yt-dlp cannot access or download a YouTube video."""


def _build_ytdlp_cookie_hint() -> str:
    return (
        "YouTube requested sign-in verification. Upload a valid YouTube cookies.txt file for this account or use a "
        "configured shared server fallback."
    )


def _normalize_ytdlp_error_message(error: Exception | str) -> str:
    raw_message = str(error or "").strip()
    if not raw_message:
        return "yt-dlp failed to access the video."
    normalized = raw_message.lower()
    if any(marker in normalized for marker in YOUTUBE_AUTH_ERROR_MARKERS):
        return _build_ytdlp_cookie_hint()
    return raw_message


def _apply_ytdlp_auth_options(options: Dict[str, Any], cookie_file_path: Optional[str] = None) -> Dict[str, Any]:
    cookie_file = (cookie_file_path or "").strip() or (config.ytdlp_cookies_file or "").strip()
    if not cookie_file:
        return options

    cookie_path = Path(cookie_file)
    if cookie_path.is_file():
        options["cookiefile"] = str(cookie_path)
    else:
        logger.warning("YTDLP_COOKIES_FILE is set but file does not exist: %s", cookie_file)
    return options

class YouTubeDownloader:
    """Enhanced YouTube downloader with optimized settings."""

    def __init__(self):
        self.temp_dir = Path(config.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_optimal_download_options(self, video_id: str, cookie_file_path: Optional[str] = None) -> Dict[str, Any]:
        """Get optimal yt-dlp options for high-quality downloads with enhanced YouTube bypass."""
        output_path = self.temp_dir / f"{video_id}.%(ext)s"

        return _apply_ytdlp_auth_options({
            'outtmpl': str(output_path),
            # Prefer 1080p mp4 + m4a first, then gracefully fall back to lower resolutions.
            # Order is important: first match wins.
            'format': (
                'bestvideo[height=1080][ext=mp4]+bestaudio[ext=m4a]/'
                'best[height=1080][ext=mp4]/'
                'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/'
                'best[height<=1080][ext=mp4]/'
                'bestvideo[height<=1080]+bestaudio/'
                'best[height<=1080]'
            ),
            'merge_output_format': 'mp4',
            'writesubtitles': False,
            'writeautomaticsub': False,
            # Optimized for speed and reliability
            'socket_timeout': 30,
            'retries': 5,  # Increased retries
            'fragment_retries': 5,
            'http_chunk_size': 10485760,  # 10MB chunks
            # Quiet operation - only errors/warnings
            'quiet': True,
            'no_warnings': False,  # Show warnings but not info
            'ignoreerrors': False,
            # Enhanced headers to avoid 403 errors
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            },
            # Simplified YouTube bypass - use android client for better reliability
            'extractor_args': {
                'youtube': {
                    # Prefer android_vr; android often requires PO tokens for better formats.
                    'player_client': ['android_vr', 'android', 'web'],
                }
            },
            # Post-processing options
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            # Metadata extraction
            'extract_flat': False,
            'writeinfojson': False,
            # Additional bypass options
            'nocheckcertificate': True,
            'prefer_insecure': False,
            'age_limit': None,
        }, cookie_file_path=cookie_file_path)

def get_youtube_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.
    Supports standard, short, embed, and mobile URLs.
    """
    if not isinstance(url, str) or not url.strip():
        return None

    url = url.strip()

    # Comprehensive regex patterns for different YouTube URL formats
    patterns = [
        r"(?:youtube\.com/(?:.*v=|v/|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"youtube\.com/v/([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"m\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            video_id = match.group(1)
            # Validate video ID length (YouTube IDs are always 11 characters)
            if len(video_id) == 11:
                return video_id

    # Fallback: parse query parameters
    try:
        parsed_url = urlparse(url)
        if 'youtube.com' in parsed_url.netloc.lower():
            query = parse_qs(parsed_url.query)
            video_ids = query.get("v")
            if video_ids and len(video_ids[0]) == 11:
                return video_ids[0]
    except Exception as e:
        logger.warning(f"Error parsing URL query parameters: {e}")

    return None

def validate_youtube_url(url: str) -> bool:
    """Validate if URL is a proper YouTube URL."""
    video_id = get_youtube_video_id(url)
    return video_id is not None

def get_youtube_video_info(url: str, cookie_file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive video information without downloading.
    Returns title, duration, description, and other metadata.
    """
    video_id = get_youtube_video_id(url)
    if not video_id:
        logger.error(f"Invalid YouTube URL: {url}")
        return None

    try:
        ydl_opts = _apply_ytdlp_auth_options({
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'skip_download': True,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            },
            # Simplified extractor args for better compatibility
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
            'nocheckcertificate': True,
        }, cookie_file_path=cookie_file_path)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            return {
                'id': info.get('id'),
                'title': info.get('title'),
                'description': info.get('description', ''),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'upload_date': info.get('upload_date'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'thumbnail': info.get('thumbnail'),
                'format_id': info.get('format_id'),
                'resolution': info.get('resolution'),
                'fps': info.get('fps'),
                'filesize': info.get('filesize'),
            }

    except Exception as e:
        logger.error("Error extracting video info: %s", _normalize_ytdlp_error_message(e))
        return None

def get_youtube_video_title(url: str, cookie_file_path: Optional[str] = None) -> Optional[str]:
    """
    Get the title of a YouTube video from a URL.
    Enhanced with better error handling and validation.
    """
    video_info = get_youtube_video_info(url, cookie_file_path=cookie_file_path)
    return video_info.get('title') if video_info else None

def download_youtube_video(
    url: str,
    max_retries: int = 3,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cookie_file_path: Optional[str] = None,
) -> Optional[Path]:
    """
    Download YouTube video with optimized settings and retry logic.
    Returns the path to the downloaded file, or None if download fails.
    """
    logger.info(f"Starting YouTube download: {url}")

    video_id = get_youtube_video_id(url)
    if not video_id:
        logger.error(f"Could not extract video ID from URL: {url}")
        return None

    downloader = YouTubeDownloader()

    # Fast path: reuse an already-downloaded local file.
    for file_path in downloader.temp_dir.glob(f"{video_id}.*"):
        if file_path.is_file() and file_path.suffix.lower() in [".mp4", ".mkv", ".webm"]:
            file_size_mb = file_path.stat().st_size // 1024 // 1024
            logger.info(f"Using cached download: {file_path.name} ({file_size_mb}MB)")
            if progress_callback:
                progress_callback(100, f"Found existing download ({file_path.name}), skipping download.")
            return file_path

    # Get video info first to validate and get metadata
    video_info = get_youtube_video_info(url, cookie_file_path=cookie_file_path)
    if not video_info:
        message = f"Could not retrieve video information. {_build_ytdlp_cookie_hint()}"
        logger.error("%s URL=%s", message, url)
        raise YouTubeDownloadError(message)

    logger.info(f"Video: '{video_info.get('title')}' ({video_info.get('duration')}s)")

    # Check if video is too long (optional safeguard)
    duration = video_info.get('duration', 0)
    if duration > 3600:  # 1 hour limit
        logger.warning(f"Video duration ({duration}s) exceeds recommended limit")

    # Retry download with exponential backoff
    last_error_message: Optional[str] = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Download attempt {attempt + 1}/{max_retries}")

            ydl_opts = downloader.get_optimal_download_options(video_id, cookie_file_path=cookie_file_path)
            last_progress = -1

            def progress_hook(progress_data: Dict[str, Any]) -> None:
                nonlocal last_progress
                if not progress_callback:
                    return

                status = progress_data.get("status")
                if status != "downloading":
                    if status == "finished":
                        progress_callback(100, "Downloading video... 100%")
                    return

                downloaded = progress_data.get("downloaded_bytes") or 0
                total = progress_data.get("total_bytes") or progress_data.get("total_bytes_estimate") or 0

                if total <= 0:
                    return

                percent = int((downloaded / total) * 100)
                percent = max(0, min(100, percent))
                if percent <= last_progress:
                    return

                last_progress = percent
                progress_callback(percent, f"Downloading video... {percent}%")

            ydl_opts["progress_hooks"] = [progress_hook]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([url])

                # Find the downloaded file
                logger.info(f"Searching for downloaded file: {video_id}.*")
                for file_path in downloader.temp_dir.glob(f"{video_id}.*"):
                    if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.mkv', '.webm']:
                        file_size = file_path.stat().st_size
                        logger.info(f"Download successful: {file_path.name} ({file_size // 1024 // 1024}MB)")
                        return file_path

                logger.warning(f"No video file found after download attempt {attempt + 1}")

        except yt_dlp.utils.DownloadError as e:
            last_error_message = _normalize_ytdlp_error_message(e)
            logger.warning("Download attempt %s failed: %s", attempt + 1, last_error_message)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"All download attempts failed for: {url}")

        except Exception as e:
            last_error_message = _normalize_ytdlp_error_message(e)
            logger.error("Unexpected error during download attempt %s: %s", attempt + 1, last_error_message)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"All download attempts failed for: {url}")

    if last_error_message:
        raise YouTubeDownloadError(last_error_message)
    raise YouTubeDownloadError("Failed to download video from YouTube.")

def get_video_duration(url: str, cookie_file_path: Optional[str] = None) -> Optional[int]:
    """Get video duration in seconds without downloading."""
    video_info = get_youtube_video_info(url, cookie_file_path=cookie_file_path)
    return video_info.get('duration') if video_info else None

def is_video_suitable_for_processing(
    url: str,
    min_duration: int = 60,
    max_duration: int = 7200,
    cookie_file_path: Optional[str] = None,
) -> bool:
    """
    Check if video is suitable for processing based on duration and other factors.
    Default limits: 1 minute to 2 hours.
    """
    video_info = get_youtube_video_info(url, cookie_file_path=cookie_file_path)
    if not video_info:
        return False

    duration = video_info.get('duration', 0)

    # Check duration constraints
    if duration < min_duration or duration > max_duration:
        logger.warning(f"Video duration {duration}s outside allowed range ({min_duration}-{max_duration}s)")
        return False

    # Additional checks could go here (e.g., content type, quality, etc.)

    return True

def cleanup_downloaded_files(video_id: str):
    """Clean up downloaded files for a specific video ID."""
    temp_dir = Path(config.temp_dir)

    for file_path in temp_dir.glob(f"{video_id}.*"):
        try:
            if file_path.is_file():
                file_path.unlink()
                logger.info(f"Cleaned up: {file_path.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path.name}: {e}")

# Backward compatibility functions
def extract_video_id(url: str) -> Optional[str]:
    """Backward compatibility wrapper."""
    return get_youtube_video_id(url)
