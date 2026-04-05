import os
import threading
import time
import tempfile
import shutil

from flask import Flask, render_template, request, jsonify, send_file, abort
from downloader import (
    get_video_info, download_video, download_audio, download_best_quality,
    get_available_formats, HAS_FFMPEG, QUALITY_LABELS
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024   # 2 MB request cap

VALID_VIDEO = {"144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p", "4320p"}
VALID_AUDIO = {"MP3 64", "MP3 128", "MP3 192", "MP3 256", "MP3 320", "MP3 384"}


def _delete_later(file_path: str, delay: int = 120) -> None:
    """Delete a file after `delay` seconds in a daemon thread."""
    def _worker():
        time.sleep(delay)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            parent = os.path.dirname(file_path)
            if parent and os.path.isdir(parent) and parent.startswith(tempfile.gettempdir()):
                try:
                    if not os.listdir(parent):
                        os.rmdir(parent)
                except OSError:
                    pass
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


def cleanup_temp_files(directory: str, delay: int = 300):
    """Schedule cleanup of entire temp directory."""
    def _cleanup():
        time.sleep(delay)
        try:
            if os.path.exists(directory) and os.path.isdir(directory):
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass
    threading.Thread(target=_cleanup, daemon=True).start()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API Routes ─────────────────────────────────────────────────────────────────

@app.route("/fetch", methods=["POST"])
def fetch():
    url = (request.form.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Please enter a video URL."}), 400

    try:
        info = get_video_info(url)
        return jsonify(info)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        msg = str(exc).lower()
        if "private" in msg:
            return jsonify({"error": "This video is private or unavailable."}), 400
        if "not found" in msg or "unavailable" in msg:
            return jsonify({"error": "Video not found. Please check the URL."}), 400
        return jsonify({"error": "Could not fetch video info. Please try again."}), 500


@app.route("/formats", methods=["POST"])
def get_formats():
    """Get detailed format information for a video."""
    url = (request.form.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Please enter a video URL."}), 400
    
    try:
        formats = get_available_formats(url)
        return jsonify({"formats": formats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/download", methods=["POST"])
def download():
    url = (request.form.get("url") or "").strip()
    quality = (request.form.get("quality") or "").strip()
    mp3 = request.form.get("mp3")
    best = request.form.get("best")  # Download best available quality

    if not url:
        return jsonify({"error": "Missing URL."}), 400

    try:
        if mp3:
            # Audio download
            if quality not in VALID_AUDIO:
                return jsonify({"error": f"Invalid audio quality: {quality}"}), 400
            if not HAS_FFMPEG:
                return jsonify({"error": "FFmpeg is required for MP3 conversion but not installed."}), 400
            file_path = download_audio(url, quality)
            mime = "audio/mpeg"
        elif best:
            # Download best available quality
            file_path = download_best_quality(url)
            mime = "video/mp4"
        else:
            # Video download with specified quality
            if quality not in VALID_VIDEO:
                return jsonify({"error": f"Invalid video quality: {quality}"}), 400
            file_path = download_video(url, quality, prefer_highest=True)
            mime = "video/mp4"

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        msg = str(exc).lower()
        if "private" in msg:
            return jsonify({"error": "This video is private or unavailable."}), 400
        if "too large" in msg:
            return jsonify({"error": "File too large. Try a lower quality."}), 400
        return jsonify({"error": "Download failed. Please try again."}), 500

    filename = os.path.basename(file_path)
    response = send_file(
        file_path, 
        as_attachment=True,
        download_name=filename, 
        mimetype=mime
    )

    @response.call_on_close
    def _cleanup():
        _delete_later(file_path, delay=10)
        parent_dir = os.path.dirname(file_path)
        if parent_dir and parent_dir.startswith(tempfile.gettempdir()):
            cleanup_temp_files(parent_dir, delay=30)

    return response


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Not found."}), 404

@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Request too large."}), 413

@app.errorhandler(500)
def server_err(_):
    return jsonify({"error": "Server error. Please try again later."}), 500


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print(" VidGet Server Starting...")
    print("="*50)
    print(f" FFmpeg Available: {HAS_FFMPEG}")
    print(f" Supported Video Qualities: {', '.join(VALID_VIDEO)}")
    print(f" Supported Audio Bitrates: {', '.join(VALID_AUDIO)}")
    print(f" Temp Directory: {tempfile.gettempdir()}")
    print("="*50 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)