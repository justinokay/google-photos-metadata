import os
import json
import subprocess
from datetime import datetime
import piexif

BASE_FOLDER = "/Volumes/SD/Takeout/"

photo_exts = [
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".dng", ".heic", ".heif", ".webp", ".raw", ".cr2", ".cr3",
    ".nef", ".nrw", ".arw", ".orf", ".sr2", ".rw2", ".pef", ".raf",
    ".3fr", ".x3f", ".srf", ".kdc", ".mrw", ".mef", ".rwl"
]
video_exts = [
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".3gp", ".3g2",
    ".mts", ".m2ts", ".mxf", ".rm", ".rmvb", ".webm", ".mpg",
    ".mpeg", ".vob", ".mod", ".tod", ".dv", ".ts", ".m4v"
]
supported_exts = photo_exts + video_exts

updated = []
skipped = []
renamed_log = []

def detect_actual_type(filepath):
    try:
        return imghdr.what(filepath)
    except Exception:
        return None

def detect_mime_type(path):
    try:
        result = subprocess.run(['file', '--mime-type', path], capture_output=True, text=True)
        return result.stdout.strip().split(': ')[-1]
    except Exception:
        return None

def update_jpeg(path, dt):
    try:
        formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict = piexif.load(path)
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = formatted.encode()
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, path)
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "✅ JPEG EXIF + file mtime updated"
    except Exception as e:
        return False, f"❌ JPEG error: {e}"

def update_exiftool(path, dt):
    formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
    try:
        subprocess.run([
            "exiftool",
            "-overwrite_original",
            f"-DateTimeOriginal={formatted}",
            f"-CreateDate={formatted}",
            f"-ModifyDate={formatted}",
            f"-TrackCreateDate={formatted}",
            f"-TrackModifyDate={formatted}",
            f"-MediaCreateDate={formatted}",
            f"-MediaModifyDate={formatted}",
            path
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "✅ Metadata + file mtime updated via exiftool"
    except FileNotFoundError:
        return False, "❌ Exiftool not found. Install with `brew install exiftool`."
    except subprocess.CalledProcessError as e:
        return False, f"❌ Exiftool error: {e.stderr.decode().strip()}"

def fallback_timestamp(path, dt):
    try:
        os.utime(path, (dt.timestamp(), dt.timestamp()))
        return True, "⚠️ Only file mtime set (fallback)"
    except Exception as e:
        return False, f"❌ Fallback failed: {e}"

# 🔁 Main loop
for root, _, files in os.walk(BASE_FOLDER):
    for file in files:
        name, ext = os.path.splitext(file)
        ext = ext.lower()
        media_path = os.path.join(root, file)

        if ext not in supported_exts:
            skipped.append((media_path, "❌ Unsupported file extension"))
            continue

        # 🧪 Handle mislabeled .dng
        if ext == ".dng":
            mime = detect_mime_type(media_path)
            if mime and not mime.endswith("dng"):
                actual_type = detect_actual_type(media_path)
                if actual_type:
                    new_ext = f".{actual_type}"
                    new_path = os.path.splitext(media_path)[0] + new_ext
                    try:
                        os.rename(media_path, new_path)
                        recheck = detect_actual_type(new_path)
                        if not recheck:
                            skipped.append((new_path, "❌ Renamed file is not a valid image"))
                            continue
                        renamed_log.append(f"{media_path} -> {new_path}")
                        print(f"🔄 Renamed {media_path} to {new_path}")
                        media_path = new_path
                        file = os.path.basename(new_path)
                        ext = new_ext
                    except Exception as e:
                        skipped.append((media_path, f"❌ Rename failed: {e}"))
                        continue
                else:
                    skipped.append((media_path, "❌ Tried to rename but not a valid image"))
                    continue

        # 🧩 Match JSON
        matching_json = None
        for f in files:
            if f.startswith(file) and f.endswith(".json"):
                matching_json = os.path.join(root, f)
                break

        if not matching_json:
            skipped.append((media_path, "No matching metadata JSON"))
            continue

        # 🕒 Read timestamp
        try:
            with open(matching_json, "r") as f:
                data = json.load(f)
                ts = int(data.get("photoTakenTime", {}).get("timestamp") or data.get("creationTime", {}).get("timestamp"))
                dt = datetime.fromtimestamp(ts)
        except Exception as e:
            skipped.append((media_path, f"Failed to read timestamp: {e}"))
            continue

        print(f"\n📂 Processing: {media_path}")
        print(f"  └ JSON: {os.path.basename(matching_json)}")
        print(f"  └ Timestamp: {dt.isoformat()}")

        # 🛠 Apply timestamp
        if ext in [".jpg", ".jpeg"]:
            ok, msg = update_jpeg(media_path, dt)
        else:
            ok, msg = update_exiftool(media_path, dt)
            if not ok and "Exiftool not found" in msg:
                ok, msg = fallback_timestamp(media_path, dt)

        print(f"  └ Result: {msg}")
        if ok:
            updated.append((media_path, msg))
        else:
            skipped.append((media_path, msg))

# ✅ Write renamed.log
if renamed_log:
    with open(os.path.join(BASE_FOLDER, "renamed.log"), "w") as logf:
        for entry in renamed_log:
            logf.write(entry + "\n")
    print(f"\n📝 Saved renamed files log to: {os.path.join(BASE_FOLDER, 'renamed.log')}")

# ✅ Final summary
print("\n\n✅ Updated Files:")
for path, status in updated:
    print(f"  - {path} → {status}")

print("\n⚠️ Skipped Files:")
for path, reason in skipped:
    print(f"  - {path} → {reason}")
