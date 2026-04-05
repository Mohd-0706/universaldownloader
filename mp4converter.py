import os
import subprocess
import tempfile
import shutil
from typing import Optional, Dict, Tuple
from pathlib import Path

# Try to import from downloader, if not available, define FFMPEG detection locally
try:
    from downloader import HAS_FFMPEG, FFMPEG_DIR
except ImportError:
    # Fallback FFmpeg detection
    def _find_ffmpeg() -> Optional[str]:
        import shutil
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",
            "/usr/bin/ffmpeg",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        return None
    
    FFMPEG_PATH = _find_ffmpeg()
    HAS_FFMPEG = FFMPEG_PATH is not None

AUDIO_QUALITIES = {
    "low": {"bitrate": "96k", "sample_rate": "22050"},
    "medium": {"bitrate": "128k", "sample_rate": "44100"},
    "high": {"bitrate": "192k", "sample_rate": "44100"},
    "ultra": {"bitrate": "320k", "sample_rate": "48000"},
}


class MP4ToMP3Converter:
    """Convert MP4 video files to MP3 audio format."""
    
    def __init__(self, ffmpeg_path: Optional[str] = None):
        """
        Initialize the converter.
        
        Args:
            ffmpeg_path: Path to ffmpeg executable (auto-detected if not provided)
        """
        if ffmpeg_path:
            self.ffmpeg_path = ffmpeg_path
        elif HAS_FFMPEG:
            if FFMPEG_DIR:
                self.ffmpeg_path = os.path.join(FFMPEG_DIR, "ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
            else:
                self.ffmpeg_path = "ffmpeg"
        else:
            self.ffmpeg_path = None
            
        self.has_ffmpeg = self.ffmpeg_path is not None and self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        if not self.ffmpeg_path:
            return False
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def convert_file(self, 
                     input_path: str, 
                     output_path: Optional[str] = None,
                     quality: str = "high",
                     delete_original: bool = False,
                     custom_bitrate: Optional[str] = None,
                     custom_sample_rate: Optional[int] = None) -> str:
        """
        Convert an MP4 file to MP3.
        
        Args:
            input_path: Path to the input MP4 file
            output_path: Path for the output MP3 file (auto-generated if None)
            quality: Quality preset ('low', 'medium', 'high', 'ultra')
            delete_original: Whether to delete the original MP4 after conversion
            custom_bitrate: Custom bitrate (e.g., '192k')
            custom_sample_rate: Custom sample rate in Hz (e.g., 44100)
            
        Returns:
            Path to the converted MP3 file
            
        Raises:
            RuntimeError: If FFmpeg is not available or conversion fails
            FileNotFoundError: If input file doesn't exist
            ValueError: If input is not an MP4 file
        """
        if not self.has_ffmpeg:
            raise RuntimeError("FFmpeg is not available. Please install FFmpeg to use this converter.")
        
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        if not input_path.lower().endswith('.mp4'):
            raise ValueError(f"Input file must be an MP4 file: {input_path}")
        
        # Generate output path if not provided
        if output_path is None:
            output_path = input_path.rsplit('.', 1)[0] + '.mp3'
        
        # Get quality settings
        if custom_bitrate:
            bitrate = custom_bitrate
            sample_rate = custom_sample_rate or 44100
        else:
            if quality not in AUDIO_QUALITIES:
                raise ValueError(f"Unknown quality preset: {quality}. Use: {list(AUDIO_QUALITIES.keys())}")
            bitrate = AUDIO_QUALITIES[quality]["bitrate"]
            sample_rate = AUDIO_QUALITIES[quality]["sample_rate"]
        
        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-vn",  # No video
            "-acodec", "libmp3lame",
            "-b:a", bitrate,
            "-ar", str(sample_rate),
            "-ac", "2",  # Stereo
            "-y",  # Overwrite output file
            output_path
        ]
        
        try:
            # Run conversion
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"FFmpeg conversion failed: {error_msg[:200]}")
            
            # Verify output file was created
            if not os.path.exists(output_path):
                raise RuntimeError("Output file was not created")
            
            # Delete original if requested
            if delete_original:
                os.remove(input_path)
            
            return output_path
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Conversion timed out after 5 minutes")
        except Exception as e:
            raise RuntimeError(f"Conversion failed: {str(e)}")
    
    def convert_with_progress(self, 
                              input_path: str,
                              output_path: Optional[str] = None,
                              quality: str = "high",
                              progress_callback=None) -> str:
        """
        Convert MP4 to MP3 with progress callback.
        
        Args:
            input_path: Path to the input MP4 file
            output_path: Path for the output MP3 file
            quality: Quality preset
            progress_callback: Function called with progress (0-100)
            
        Returns:
            Path to the converted MP3 file
        """
        if not self.has_ffmpeg:
            raise RuntimeError("FFmpeg is not available")
        
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        if output_path is None:
            output_path = input_path.rsplit('.', 1)[0] + '.mp3'
        
        if quality not in AUDIO_QUALITIES:
            quality = "high"
        
        bitrate = AUDIO_QUALITIES[quality]["bitrate"]
        sample_rate = AUDIO_QUALITIES[quality]["sample_rate"]
        
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", bitrate,
            "-ar", str(sample_rate),
            "-ac", "2",
            "-progress", "pipe:1",  # Output progress to stdout
            "-y",
            output_path
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Parse progress output
        duration = None
        current_time = 0
        
        for line in process.stdout:
            if line.startswith("out_time_ms="):
                try:
                    time_ms = int(line.split("=")[1])
                    current_time = time_ms / 1000000  # Convert to seconds
                except:
                    pass
            elif line.startswith("duration="):
                try:
                    duration_str = line.split("=")[1].strip()
                    if ":" in duration_str:
                        parts = duration_str.split(":")
                        duration = int(float(parts[0])) * 3600 + int(float(parts[1])) * 60 + float(parts[2])
                except:
                    pass
            
            if duration and duration > 0 and progress_callback:
                progress = min(100, int((current_time / duration) * 100))
                progress_callback(progress)
        
        process.wait()
        
        if process.returncode != 0:
            raise RuntimeError("Conversion failed")
        
        if progress_callback:
            progress_callback(100)
        
        return output_path
    
    def batch_convert(self, 
                      input_dir: str,
                      output_dir: Optional[str] = None,
                      quality: str = "high",
                      recursive: bool = False) -> Dict[str, str]:
        """
        Convert multiple MP4 files to MP3.
        
        Args:
            input_dir: Directory containing MP4 files
            output_dir: Directory for output MP3 files (same as input if None)
            quality: Quality preset
            recursive: Whether to search subdirectories recursively
            
        Returns:
            Dictionary mapping input paths to output paths
        """
        if not os.path.exists(input_dir):
            raise FileNotFoundError(f"Input directory not found: {input_dir}")
        
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Find all MP4 files
        mp4_files = []
        if recursive:
            for root, _, files in os.walk(input_dir):
                for file in files:
                    if file.lower().endswith('.mp4'):
                        mp4_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(input_dir):
                if file.lower().endswith('.mp4'):
                    mp4_files.append(os.path.join(input_dir, file))
        
        results = {}
        for input_path in mp4_files:
            if output_dir:
                # Preserve relative path structure
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path.rsplit('.', 1)[0] + '.mp3')
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
            else:
                output_path = None
            
            try:
                output = self.convert_file(input_path, output_path, quality)
                results[input_path] = output
            except Exception as e:
                results[input_path] = f"Error: {str(e)}"
        
        return results
    
    def get_file_info(self, file_path: str) -> Dict:
        """Get information about an MP4 file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        cmd = [
            self.ffmpeg_path,
            "-i", file_path,
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        info = {"path": file_path, "size_bytes": os.path.getsize(file_path)}
        
        # Parse duration
        for line in result.stderr.split('\n'):
            if "Duration:" in line:
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                info["duration"] = duration_str
                # Calculate duration in seconds
                parts = duration_str.split(":")
                info["duration_seconds"] = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif "Audio:" in line:
                info["audio_info"] = line.strip()
            elif "Video:" in line:
                info["video_info"] = line.strip()
        
        return info


# Convenience functions
def convert_mp4_to_mp3(input_path: str, 
                       output_path: Optional[str] = None,
                       quality: str = "high",
                       delete_original: bool = False) -> str:
    """
    Convenience function to convert MP4 to MP3.
    
    Args:
        input_path: Path to MP4 file
        output_path: Path for MP3 output (auto-generated if None)
        quality: Quality preset ('low', 'medium', 'high', 'ultra')
        delete_original: Whether to delete original MP4 file
        
    Returns:
        Path to converted MP3 file
    """
    converter = MP4ToMP3Converter()
    return converter.convert_file(input_path, output_path, quality, delete_original)


def estimate_output_size(input_path: str, quality: str = "high") -> int:
    """
    Estimate the output MP3 file size in bytes.
    
    Args:
        input_path: Path to MP4 file
        quality: Quality preset
        
    Returns:
        Estimated file size in bytes
    """
    bitrates = {
        "low": 96,
        "medium": 128,
        "high": 192,
        "ultra": 320
    }
    
    if quality not in bitrates:
        quality = "high"
    
    # Get duration using ffprobe or ffmpeg
    converter = MP4ToMP3Converter()
    if not converter.has_ffmpeg:
        return 0
    
    info = converter.get_file_info(input_path)
    duration_seconds = info.get("duration_seconds", 0)
    
    # Estimate: bitrate (kbps) * duration (seconds) / 8 (bytes)
    estimated_bytes = (bitrates[quality] * 1000 * duration_seconds) // 8
    
    return estimated_bytes


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mp4converter.py <input_mp4_file> [quality]")
        print("Quality options: low, medium, high, ultra")
        sys.exit(1)
    
    input_file = sys.argv[1]
    quality = sys.argv[2] if len(sys.argv) > 2 else "high"
    
    try:
        output_file = convert_mp4_to_mp3(input_file, quality=quality)
        print(f"✅ Successfully converted: {output_file}")
        
        # Get file info
        converter = MP4ToMP3Converter()
        info = converter.get_file_info(output_file)
        size_mb = info["size_bytes"] / (1024 * 1024)
        print(f"📁 Output size: {size_mb:.2f} MB")
        print(f"⏱️  Duration: {info.get('duration', 'Unknown')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)