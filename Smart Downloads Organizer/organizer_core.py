"""
organizer_core.py
------------------
Core logic for the Smart Downloads Organizer.
No GUI dependencies here on purpose - keeps it testable and reusable
(e.g. from a CLI, a cron job, or the Tkinter GUI in gui.py).
"""

import os
import json
import shutil
import hashlib
import time
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "categories": {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic", ".tiff"],
        "Documents": [".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".xls", ".xlsx",
                      ".ppt", ".pptx", ".csv", ".md"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2"],
        "Installers": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".appimage"],
        "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
        "Video": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"],
        "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".cpp", ".c",
                 ".sh", ".yml", ".yaml"],
    },
    "other_category": "Other",
    "duplicates_folder": "Duplicates",
    "stale_folder": "Archive/Stale",
    "stale_days": 90,
    "ignore_names": [".DS_Store", "desktop.ini", "Thumbs.db"],
    "hash_chunk_size": 65536,
}


def load_config(path):
    """Load config from a JSON file, falling back to defaults for any missing keys."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        config.update(user_config)
    return config


def save_config(config, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def categorize_extension(ext, config):
    ext = ext.lower()
    for category, extensions in config["categories"].items():
        if ext in extensions:
            return category
    return config["other_category"]


def compute_hash(filepath, chunk_size=65536):
    """SHA-256 hash of file contents, read in chunks so large files don't blow up memory."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def list_scannable_files(folder, config):
    """Top-level files only (not already-organized subfolders), skipping ignored names."""
    known_folders = set(config["categories"].keys())
    known_folders.add(config["other_category"])
    known_folders.add(config["duplicates_folder"].split("/")[0])
    known_folders.add(config["stale_folder"].split("/")[0])

    files = []
    for entry in os.scandir(folder):
        if entry.is_dir():
            continue
        if entry.name in config["ignore_names"]:
            continue
        if entry.name.startswith("."):
            continue
        files.append(entry.path)
    return files


def scan_folder(folder, config):
    """
    Scans `folder` and returns a report dict:
        {
            "categorized": {category: [filepaths]},
            "duplicates": [[filepath, filepath, ...], ...]  # groups of identical files
            "stale": [filepaths]  # untouched for >= stale_days
        }
    This does NOT move anything - it's a read-only preview.
    """
    files = list_scannable_files(folder, config)

    categorized = {}
    hashes = {}
    stale = []
    now = time.time()
    stale_seconds = config["stale_days"] * 86400

    for path in files:
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1]
        category = categorize_extension(ext, config)
        categorized.setdefault(category, []).append(path)

        try:
            file_hash = compute_hash(path, config["hash_chunk_size"])
            hashes.setdefault(file_hash, []).append(path)
        except OSError:
            pass  # unreadable file, skip hashing but still categorize it

        try:
            mtime = os.path.getmtime(path)
            if now - mtime >= stale_seconds:
                stale.append(path)
        except OSError:
            pass

    duplicates = [group for group in hashes.values() if len(group) > 1]

    return {
        "categorized": categorized,
        "duplicates": duplicates,
        "stale": stale,
    }


# ---------------------------------------------------------------------------
# Planning + executing moves
# ---------------------------------------------------------------------------

def plan_categorize_actions(scan_report, folder, config):
    """Build a list of planned moves: {"src": ..., "dst": ..., "reason": "categorize"}"""
    actions = []
    for category, paths in scan_report["categorized"].items():
        dest_dir = os.path.join(folder, category)
        for src in paths:
            dst = os.path.join(dest_dir, os.path.basename(src))
            if os.path.abspath(dst) == os.path.abspath(src):
                continue
            actions.append({"src": src, "dst": dst, "reason": "categorize"})
    return actions


def plan_duplicate_actions(scan_report, folder, config):
    """
    For each duplicate group, keep the oldest file in place and move the rest
    into the duplicates folder (never deletes automatically).
    """
    actions = []
    dest_dir = os.path.join(folder, config["duplicates_folder"])
    for group in scan_report["duplicates"]:
        group_sorted = sorted(group, key=lambda p: os.path.getmtime(p))
        keeper = group_sorted[0]
        for src in group_sorted[1:]:
            dst = os.path.join(dest_dir, os.path.basename(src))
            actions.append({"src": src, "dst": dst, "reason": f"duplicate-of:{keeper}"})
    return actions


def plan_stale_actions(scan_report, folder, config):
    actions = []
    dest_dir = os.path.join(folder, config["stale_folder"])
    for src in scan_report["stale"]:
        dst = os.path.join(dest_dir, os.path.basename(src))
        actions.append({"src": src, "dst": dst, "reason": "stale"})
    return actions


def _unique_destination(dst):
    """Avoid overwriting an existing file by appending (1), (2), etc."""
    if not os.path.exists(dst):
        return dst
    base, ext = os.path.splitext(dst)
    n = 1
    while True:
        candidate = f"{base} ({n}){ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def execute_actions(actions, log_path, dry_run=True):
    """
    Executes (or just previews, if dry_run) a list of planned actions.
    Every real move is appended to a JSON log file so it can be undone later.
    Returns the list of actions actually performed (with final destination paths).
    """
    performed = []
    log_entries = []
    if not dry_run and os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            log_entries = json.load(f)

    for action in actions:
        src, dst, reason = action["src"], action["dst"], action["reason"]
        final_dst = _unique_destination(dst)

        if dry_run:
            performed.append({"src": src, "dst": final_dst, "reason": reason})
            continue

        os.makedirs(os.path.dirname(final_dst), exist_ok=True)
        shutil.move(src, final_dst)
        entry = {
            "src": src,
            "dst": final_dst,
            "reason": reason,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        log_entries.append(entry)
        performed.append(entry)

    if not dry_run:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entries, f, indent=2)

    return performed


def undo_last_run(log_path, since_timestamp=None):
    """
    Reverts moves recorded in the log. If since_timestamp is given, only
    reverts entries at or after that ISO timestamp (i.e. "undo the last run"
    rather than "undo everything ever"). Returns list of reverted entries.
    """
    if not os.path.exists(log_path):
        return []

    with open(log_path, "r", encoding="utf-8") as f:
        log_entries = json.load(f)

    to_revert = []
    to_keep = []
    for entry in log_entries:
        if since_timestamp is None or entry["timestamp"] >= since_timestamp:
            to_revert.append(entry)
        else:
            to_keep.append(entry)

    reverted = []
    for entry in reversed(to_revert):  # revert most recent first
        dst, src = entry["dst"], entry["src"]
        if os.path.exists(dst):
            os.makedirs(os.path.dirname(src), exist_ok=True)
            final_src = _unique_destination(src)
            shutil.move(dst, final_src)
            reverted.append({"restored_to": final_src, "was_at": dst})

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(to_keep, f, indent=2)

    return reverted


def last_run_timestamp(log_path):
    """Returns the timestamp of the most recent batch of actions (for the undo button)."""
    if not os.path.exists(log_path):
        return None
    with open(log_path, "r", encoding="utf-8") as f:
        log_entries = json.load(f)
    if not log_entries:
        return None
    # A "run" = every entry sharing the same timestamp-minute as the latest one.
    latest = log_entries[-1]["timestamp"]
    latest_minute = latest[:16]  # YYYY-MM-DDTHH:MM
    for entry in reversed(log_entries):
        if entry["timestamp"][:16] != latest_minute:
            return entry["timestamp"]
    return log_entries[0]["timestamp"]
