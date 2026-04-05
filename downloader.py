import yt_dlp
import os
import re
import tempfile
import shutil
import subprocess
from typing import Optional, List, Dict

# ── FFmpeg detection ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _find_ffmpeg_dir() -> Optional[str]:
    """
    Return the directory that contains the ffmpeg binary, or None.
    yt-dlp's ffmpeg_location must point to the *directory*, not the binary.
    """
    # Check common locations for ffmpeg
    common_paths = [
        # Windows
        r"C:\projects\Universal_downloader\ffmpeg\bin",
        r"C:\projects\Universal_downloader\ffmpeg\bin",
        # macOS
        "/usr/local/bin",
        "/opt/homebrew/bin",
        # Linux
        "/usr/bin",
        "/usr/local/bin",
    ]
    
    # Check each common path
    for path in common_paths:
        ffmpeg_exe = os.path.join(path, "ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
        if os.path.isfile(ffmpeg_exe) and os.access(ffmpeg_exe, os.X_OK):
            return path
    
    # Check bundled binary next to this file
    local_bin = os.path.join(BASE_DIR, "ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
    if os.path.isfile(local_bin) and os.access(local_bin, os.X_OK):
        return BASE_DIR
    
    # Check system PATH using shutil
    found = shutil.which("ffmpeg")
    if found:
        return os.path.dirname(os.path.abspath(found))
    
    # Check using subprocess
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if result.returncode == 0:
            found = shutil.which("ffmpeg")
            if found:
                return os.path.dirname(os.path.abspath(found))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return None


FFMPEG_DIR = _find_ffmpeg_dir()
HAS_FFMPEG = FFMPEG_DIR is not None

if HAS_FFMPEG:
    print(f"[VidGet] ✓ FFmpeg found at: {FFMPEG_DIR}")
else:
    print("[VidGet] ✗ FFmpeg NOT found — MP3 downloads disabled, video may be limited")

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be", "www.youtube.com",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "fb.watch",
]

MAX_FILE_BYTES = 500 * 1024 * 1024   # 500 MB
MAX_AUDIO_BYTES = 200 * 1024 * 1024   # 200 MB

QUALITY_HEIGHT = {
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,  # 4K
    "4320p": 4320,  # 8K
}

QUALITY_LABELS = {
    "144p": "144p (Low)",
    "240p": "240p",
    "360p": "360p",
    "480p": "480p",
    "720p": "720p (HD)",
    "1080p": "1080p (Full HD)",
    "1440p": "1440p (2K)",
    "2160p": "2160p (4K Ultra HD)",
    "4320p": "4320p (8K Ultra HD)",
}

AUDIO_BITRATE = {
    "MP3 64": "64",
    "MP3 128": "128",
    "MP3 192": "192",
    "MP3 256": "256",
    "MP3 320": "320",
    "MP3 384": "384",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_valid_url(url: str) -> bool:
    pat = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}|'
        r'localhost|\d{1,3}(?:\.\d{1,3}){3})'
        r'(?::\d+)?(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(pat.match(url.strip()))


def _is_supported(url: str) -> bool:
    return any(d in url for d in SUPPORTED_DOMAINS)


def _detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube Shorts" if "shorts" in url else "YouTube"
    if "instagram.com" in url:
        return "Instagram"
    if "facebook.com" in url or "fb.watch" in url:
        return "Facebook"
    return "Unknown"


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nooverwrites": True,
    }
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    return opts


def _size_check(path: str, max_bytes: int = MAX_FILE_BYTES) -> str:
    """Check file size and raise error if too large."""
    if os.path.getsize(path) > max_bytes:
        parent = os.path.dirname(path)
        shutil.rmtree(parent, ignore_errors=True)
        raise ValueError(f"File too large ({max_bytes // (1024*1024)}MB max). Please choose a lower quality.")
    return path


def _find_mp4_file(raw_path: str, temp_dir: str) -> Optional[str]:
    """Find the actual mp4 file (yt-dlp may add suffixes)."""
    base = os.path.splitext(raw_path)[0]
    for ext in ['mp4', 'mkv', 'webm', 'mov']:
        candidate = f"{base}.{ext}"
        if os.path.exists(candidate):
            return candidate
    return None


def get_available_formats(url: str) -> List[Dict]:
    """Get all available formats for a video with detailed information."""
    if not _is_valid_url(url):
        raise ValueError("Invalid URL format.")
    if not _is_supported(url):
        raise ValueError("Unsupported platform.")

    opts = {**_base_opts(), "skip_download": True}
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    formats = []
    seen_qualities = set()
    
    for f in info.get("formats", []):
        height = f.get("height")
        width = f.get("width")
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        fps = f.get("fps")
        filesize = f.get("filesize") or f.get("filesize_approx") or 0
        
        if height and vcodec != "none":
            quality_label = f"{height}p"
            if quality_label not in seen_qualities:
                seen_qualities.add(quality_label)
                formats.append({
                    "quality": quality_label,
                    "display_name": QUALITY_LABELS.get(quality_label, quality_label),
                    "height": height,
                    "width": width or 0,
                    "fps": fps or 0,
                    "codec": vcodec.split('.')[0] if vcodec else "unknown",
                    "has_audio": acodec != "none",
                    "filesize_mb": round(filesize / (1024 * 1024), 2) if filesize else 0,
                    "format_id": f.get("format_id"),
                })
    
    # Sort by height (highest first)
    formats.sort(key=lambda x: x["height"], reverse=True)
    
    return formats


# ── Public API ────────────────────────────────────────────────────────────────

def get_video_info(url: str) -> dict:
    if not _is_valid_url(url):
        raise ValueError("Invalid URL format.")
    if not _is_supported(url):
        raise ValueError("Unsupported platform. Use YouTube, Instagram, or Facebook URLs.")

    opts = {**_base_opts(), "skip_download": True}
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        error_msg = str(e).lower()
        if "private" in error_msg:
            raise ValueError("This video is private or unavailable.")
        elif "unavailable" in error_msg or "not found" in error_msg:
            raise ValueError("Video not found. Please check the URL.")
        else:
            raise ValueError(f"Could not fetch video info: {str(e)}")

    if not info:
        raise ValueError("Could not retrieve video information.")

    # Get available video heights
    heights = set()
    max_height = 0
    for f in info.get("formats", []):
        h = f.get("height")
        if h and f.get("vcodec", "none") != "none":
            heights.add(h)
            if h > max_height:
                max_height = h
    
    # Determine available qualities based on actual heights
    available_qualities = []
    for lbl, cap in QUALITY_HEIGHT.items():
        if any(h >= cap for h in heights) or cap <= max_height:
            available_qualities.append(lbl)
    
    # Ensure we have at least some qualities
    if not available_qualities:
        available_qualities = ["360p", "480p", "720p"]
    
    # Get highest available quality
    highest_quality = max(available_qualities, key=lambda x: QUALITY_HEIGHT[x]) if available_qualities else "1080p"
    
    # Get format details for highest quality
    formats = get_available_formats(url)
    
    dur = info.get("duration") or 0
    duration_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "Unknown"
    
    # Calculate video bitrate if available
    video_bitrate = info.get("bitrate") or 0
    if video_bitrate:
        video_bitrate = round(video_bitrate / 1000, 0)  # Convert to kbps
    
    return {
        "title": info.get("title", "Unknown Title"),
        "thumbnail": info.get("thumbnail", ""),
        "duration": duration_str,
        "duration_seconds": dur,
        "platform": _detect_platform(url),
        "uploader": info.get("uploader", ""),
        "uploader_url": info.get("uploader_url", ""),
        "view_count": info.get("view_count", 0),
        "like_count": info.get("like_count", 0),
        "available_qualities": available_qualities,
        "available_audio": ["MP3 64", "MP3 128", "MP3 192", "MP3 256", "MP3 320", "MP3 384"],
        "ffmpeg_available": HAS_FFMPEG,
        "highest_quality": highest_quality,
        "highest_quality_display": QUALITY_LABELS.get(highest_quality, highest_quality),
        "max_resolution": f"{max_height}p" if max_height else "Unknown",
        "formats": formats,
        "video_bitrate_kbps": video_bitrate,
        "filesize_estimate": round(info.get("filesize_approx", 0) / (1024 * 1024), 2) if info.get("filesize_approx") else 0,
    }


def download_video(url: str, quality: str, prefer_highest: bool = True) -> str:
    """
    Download video with specified quality.
    
    Args:
        url: Video URL
        quality: Quality string (e.g., '1080p')
        prefer_highest: If True and requested quality not available, download highest available
    
    Returns:
        Path to downloaded file
    """
    if not _is_valid_url(url):
        raise ValueError("Invalid URL format.")
    if not _is_supported(url):
        raise ValueError("Unsupported platform.")
    
    # If prefer_highest is True, try to get best available quality
    target_height = QUALITY_HEIGHT.get(quality)
    if not target_height:
        raise ValueError(f"Unsupported quality '{quality}'.")
    
    # Create a unique temp directory for this download
    temp_dir = tempfile.mkdtemp(prefix="vidget_video_")
    output_template = os.path.join(temp_dir, "%(title).80s.%(ext)s")

    opts = {**_base_opts(), "outtmpl": output_template}

    if HAS_FFMPEG:
        # Build format selector for best quality
        if prefer_highest:
            # Try to get exact quality, then fallback to best available
            format_selector = (
                f"bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={target_height}]+bestaudio"
                f"/bestvideo[height<={target_height}][ext=mp4]"
                f"/bestvideo[height<={target_height}]"
                f"/bestvideo+bestaudio"
                f"/best"
            )
        else:
            format_selector = (
                f"bestvideo[height={target_height}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height={target_height}]+bestaudio"
                f"/best[height={target_height}][ext=mp4]"
                f"/best[height={target_height}]"
            )
        
        opts["format"] = format_selector
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ]
    else:
        # No FFmpeg → single-file stream only
        if prefer_highest:
            format_selector = (
                f"best[height<={target_height}][ext=mp4]"
                f"/best[height<={target_height}]"
                f"/best[ext=mp4]"
                f"/best"
            )
        else:
            format_selector = (
                f"best[height={target_height}][ext=mp4]"
                f"/best[height={target_height}]"
                f"/best[ext=mp4]"
                f"/best"
            )
        opts["format"] = format_selector

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        error_msg = str(e).lower()
        if "requested format not available" in error_msg and prefer_highest:
            # Try downloading without quality restriction
            try:
                opts["format"] = "bestvideo+bestaudio/best"
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    raw_path = ydl.prepare_filename(info)
            except Exception as e2:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise RuntimeError(f"Download failed: {str(e2)}")
        else:
            raise RuntimeError(f"Download failed: {str(e)}")

    # Find the actual downloaded file
    if os.path.exists(raw_path):
        final_path = _find_mp4_file(raw_path, temp_dir)
        if final_path:
            return _size_check(final_path)
    
    # Fallback: scan temp directory for any video file
    for file in os.listdir(temp_dir):
        if file.endswith(('.mp4', '.mkv', '.webm', '.mov')):
            final_path = os.path.join(temp_dir, file)
            return _size_check(final_path)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise RuntimeError("Download produced no output file.")


def download_best_quality(url: str) -> str:
    """Download the best available quality of a video."""
    return download_video(url, "2160p", prefer_highest=True)


def download_audio(url: str, quality: str) -> str:
    """
    Download audio and convert to MP3 at requested bitrate.
    Raises ValueError for bad input, RuntimeError if download fails.
    Returns path to the .mp3 file.
    """
    if not _is_valid_url(url):
        raise ValueError("Invalid URL format.")
    if not _is_supported(url):
        raise ValueError("Unsupported platform. Use YouTube, Instagram, or Facebook URLs.")
    if quality not in AUDIO_BITRATE:
        raise ValueError(f"Unsupported audio quality '{quality}'.")
    if not HAS_FFMPEG:
        raise RuntimeError(
            "FFmpeg is required for MP3 conversion but was not found on this server. "
            "Please install FFmpeg and restart the application."
        )

    bitrate = AUDIO_BITRATE[quality]
    
    # Create a unique temp directory for this download
    temp_dir = tempfile.mkdtemp(prefix="vidget_audio_")
    output_template = os.path.join(temp_dir, "%(title).80s.%(ext)s")

    opts = {
        **_base_opts(),
        "outtmpl": output_template,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Audio download failed: {str(e)}")

    # yt-dlp renames the file to .mp3 after post-processing
    base = os.path.splitext(raw_path)[0]
    mp3_path = base + ".mp3"

    if os.path.exists(mp3_path):
        return _size_check(mp3_path, MAX_AUDIO_BYTES)

    # Fallback scan for any mp3 file
    for file in os.listdir(temp_dir):
        if file.endswith(".mp3"):
            mp3_path = os.path.join(temp_dir, file)
            return _size_check(mp3_path, MAX_AUDIO_BYTES)

    shutil.rmtree(temp_dir, ignore_errors=True)
    raise RuntimeError("Audio conversion produced no output file.")