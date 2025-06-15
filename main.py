import os
import json
import subprocess
from datetime import datetime
import piexif

# 📍 SET THIS TO YOUR EXTRACTED TAKEOUT FOLDER
BASE_FOLDER = "/path/to/unzipped_takeout"

# Media types
photo_exts = [".jpg", ".jpeg", ".dng", ".png"]
video_exts = [".mp4", ".mov"]
all_exts = photo_exts + video_exts

# Logs
updated = []
skipped = []

def update_jpeg(path, dt):
    formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
    try:
        exif_dict = piexif.load(path)
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = formatted.encode()
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, path)
        return True, "JPEG EXIF updated"
    except Exception as e:
        return False, f"JPEG error: {e}"

def update_exiftool(path, dt):
    formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
    try:
        subprocess.run([
            "exiftool",
            "-overwrite_original",
            f"-DateTimeOriginal={formatted}",
            f"-CreateDate={formatted}",
            f"-ModifyDate={formatted}",
            path
        ], check=True)
        return True, "Updated with exiftool"
    except subprocess.CalledProcessError as e:
        return False, f"Exiftool error: {e}"

# Scan folders
for root, _, files in os.walk(BASE_FOLDER):
    for file in files:
        name, ext = os.path.splitext(file)
        ext = ext.lower()
        if ext not in all_exts:
            continue

        media_path = os.path.join(root, file)

        # Find matching metadata JSON
        matching_json = None
        for f in files:
            if f.startswith(file) and f.endswith(".json"):
                matching_json = os.path.join(root, f)
                break

        if not matching_json:
            skipped.append((file, "No matching JSON file"))
            continue

        # Read timestamp
        try:
            with open(matching_json, "r") as f:
                data = json.load(f)
                ts = int(data["photoTakenTime"]["timestamp"])
                dt = datetime.fromtimestamp(ts)
        except Exception as e:
            skipped.append((file, f"Failed to read JSON: {e}"))
            continue

        # Apply timestamp
        if ext in [".jpg", ".jpeg"]:
            ok, msg = update_jpeg(media_path, dt)
        else:
            ok, msg = update_exiftool(media_path, dt)

        if ok:
            updated.append((file, msg))
        else:
            skipped.append((file, msg))

# ✅ Summary
print("\n✅ Updated files:")
for name, status in updated:
    print(f"  {name} — {status}")

print("\n⚠️ Skipped files:")
for name, reason in skipped:
    print(f"  {name} — {reason}")