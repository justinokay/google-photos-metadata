import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from pathlib import Path
from PIL import Image
from piexif import load as piexif_load, dump as piexif_dump, insert as piexif_insert
from colorama import init; init()

BASE_FOLDER = "/Volumes/BLACKED/Takeout"
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                  ".dng", ".heic", ".heif", ".webp", ".raw", ".cr2", ".cr3",
                  ".nef", ".nrw", ".arw", ".orf", ".sr2", ".rw2", ".pef", ".raf",
                  ".3fr", ".x3f", ".srf", ".kdc", ".mrw", ".mef", ".rwl",
                  ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".3gp", ".3g2",
                  ".mts", ".m2ts", ".mxf", ".rm", ".rmvb", ".webm", ".mpg",
                  ".mpeg", ".vob", ".mod", ".tod", ".dv", ".ts", ".m4v"}

MAX_WORKERS = 4
json_cache = {}

def strip_copy_suffix(name: str) -> str:
    return re.sub(r'\(\d+\)$', '', name)

def build_json_cache():
    print("📦 Indexing metadata JSON files...")
    for root, _, files in os.walk(BASE_FOLDER):
        for file in files:
            if file.endswith(".json") and not file.startswith("._"):
                base = Path(file).stem
                base = re.sub(r'\.supplemental-metadata$', '', base)
                key = strip_copy_suffix(base)
                json_cache.setdefault(key, []).append(os.path.join(root, file))

def match_metadata(media_path: str) -> str | None:
    name = Path(media_path).stem
    key = strip_copy_suffix(name)
    for candidate in json_cache.get(key, []):
        if Path(candidate).startswith(Path(media_path).parent):
            return candidate
    return None

def update_jpeg(path, dt):
    try:
        img = Image.open(path)
        img.verify()  # Validate integrity
        formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict = piexif_load(path)
        exif_dict["Exif"][36867] = formatted.encode()
        piexif_insert(piexif_dump(exif_dict), path)
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "✅ JPEG EXIF + file mtime updated"
    except Exception as e:
        return False, f"❌ JPEG error: {e}"

def update_exiftool(path, dt):
    try:
        formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
        subprocess.run([
            "exiftool", "-overwrite_original",
            f"-DateTimeOriginal={formatted}",
            f"-CreateDate={formatted}",
            f"-ModifyDate={formatted}",
            f"-TrackCreateDate={formatted}",
            f"-TrackModifyDate={formatted}",
            f"-MediaCreateDate={formatted}",
            f"-MediaModifyDate={formatted}",
            path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "✅ Metadata + file mtime updated via exiftool"
    except subprocess.CalledProcessError:
        return False, f"❌ Exiftool failed for {path}"

def fallback_timestamp(path, dt):
    try:
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "⚠️ Only file mtime set (fallback)"
    except Exception as e:
        return False, f"❌ Fallback failed: {e}"

def maybe_fix_extension(path):
    try:
        Image.open(path).verify()
        return True
    except:
        try:
            fixed_path = str(Path(path).with_suffix(".jpg"))
            backup = fixed_path + ".backup"
            shutil.copy2(path, backup)
            os.rename(path, fixed_path)
            Image.open(fixed_path).verify()
            os.remove(backup)
            return fixed_path
        except:
            shutil.move(backup, path)
            return None

def process_file(media_path: str):
    ext = Path(media_path).suffix.lower()
    if ext not in SUPPORTED_EXTS or media_path.startswith("._") or not os.path.getsize(media_path):
        return  # Skip unsupported, 0-byte, or AppleDot files

    meta_path = match_metadata(media_path)
    if not meta_path:
        print(f"⚠️ {media_path} → No matching metadata JSON")
        return

    try:
        with open(meta_path) as f:
            data = json.load(f)
        ts = int(data.get("photoTakenTime", {}).get("timestamp") or data.get("creationTime", {}).get("timestamp"))
        dt = datetime.fromtimestamp(ts)
    except Exception as e:
        print(f"⚠️ {media_path} → Failed to read timestamp: {e}")
        return

    if ext in {".jpg", ".jpeg"}:
        success, msg = update_jpeg(media_path, dt)
    else:
        success, msg = update_exiftool(media_path, dt)
        if not success:
            success, msg = fallback_timestamp(media_path, dt)

    if success:
        print(f"✅ {media_path} → {msg}")
    else:
        print(f"⚠️ {media_path} → {msg}")

if __name__ == "__main__":
    build_json_cache()
    all_media = [os.path.join(r, f)
                 for r, _, fs in os.walk(BASE_FOLDER)
                 for f in fs
                 if Path(f).suffix.lower() in SUPPORTED_EXTS and not f.startswith("._")]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(tqdm(executor.map(process_file, all_media), total=len(all_media), desc="📂 Processing", ncols=100))
