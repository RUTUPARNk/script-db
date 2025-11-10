""" script_manager.py
manual script indexer + automatic reproducible backups

Features:
- Add / Modify / Delete / List scripts (stores metadata in scripts.json)
- When adding/modifying, backups are created automatically into backups/<script_name>/
  - If script file is currently running, a pending backup is scheduled and processed
    quietly in the background once the process ends.
- Backups store compressed file(s) (.gz) + metadata.json + sha256 hash for integrity
- Reproduce (restore) to ./reproduced/<script_name>/ by default
- Open containing folder (select file)
- Execute script in a new window (Windows-friendly)
- Background thread checks pending backups periodically until done

"""
import os
import sys
import json
import time
import threading
import hashlib
import zlib
import subprocess
from datetime import datetime

try:
    from tkinter import Tk, filedialog
    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    PSUTIL_AVAILABLE = False

DATA_FILE = 'scripts.json'
BACKUPS_DIR = 'backups'
REPRODUCED_DIR = 'reproduced'
PENDING_POLL_INTERVAL = 5 # seconds Between pending backup checks

def load_scripts():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_scripts(scripts):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, indent=4, ensure_ascii=False)

def ensure_dirs():
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    os.makedirs(REPRODUCED_DIR, exist_ok=True)

def pick_file_dialog(title="Select file"):
    if not TK_AVAILABLE:
        print("tkinter not available — please paste full path manually.")
        return input("Enter full path: ").strip()
    root = Tk()
    root.withdraw()
    path = filedialog.askopenfilename(title=title)
    root.update()
    root.destroy()
    return path

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def compress_bytes(b: bytes) -> bytes:
    return zlib.compress(b)

def decompress_bytes(b: bytes) -> bytes:
    return zlib.decompress(b)

def is_running(path):
    """
    Try to detect whether the given script path is currently in use by any running process.
    This is heuristic: checks process cmdline and executable names for the basename or full path.
    Requires psutil; if not available, returns False (assume not running).
    """
    if not PSUTIL_AVAILABLE:
        return False

    target_name = os.path.basename(path)
    target_path = os.path.abspath(path)
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
        try:
            info = proc.info
            cmdline = info.get('cmdline') or []
            exe = info.get('exe') or ""
            # check full path in cmdline or exe
            if any(target_path == os.path.abspath(x) for x in cmdline if x):
                return True
            if exe and os.path.basename(exe).lower() == target_name.lower():
                return True
            # also check if basename appears in cmdline (heuristic)
            if any(target_name in x for x in cmdline if isinstance(x, str)):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def open_containing_folder_and_select(path):
    if not os.path.exists(path):
        print("File does not exist.")
        return
    system = sys.platform
    try:
        if system.startswith("win"):
            # explorer /select,"path"
            subprocess.run(f'explorer /select,"{os.path.abspath(path)}"', shell=True)
        elif system == "darwin":
            subprocess.run(["open", "-R", path])
        else:
            # Linux: open folder (can't select reliably with xdg-open)
            folder = os.path.dirname(path)
            subprocess.run(["xdg-open", folder])
    except Exception as e:
        print("Could not open folder:", e)

def launch_in_new_window(path):
    """Launch path in a new console/window if possible. Windows-friendly."""
    if not os.path.exists(path):
        print("File does not exist.")
        return
    system = sys.platform
    try:
        if system.startswith("win"):
            # 'start "" "<path>"' — start uses shell, so use subprocess.Popen with shell=True
            cmd = f'start "" "{os.path.abspath(path)}"'
            subprocess.Popen(cmd, shell=True)
        elif system == "darwin":
            # open with default application
            subprocess.Popen(["open", path])
        else:
            # Linux: try x-terminal-emulator -e <path> or just xdg-open
            try:
                subprocess.Popen(["x-terminal-emulator", "-e", path])
            except Exception:
                subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print("Could not launch script:", e)

# Backup / reproduce logic
def backup_script_to_folder(script):
    """
    Create compressed backup files under backups/<script_name>/
    - Writes <basename>.gz (zlib-compressed raw content)
    - Writes metadata.json with original_path, description, timestamp, sha256
    """
    name = script.get("name")
    src = script.get("path")
    if not name:
        print("Script has no name; cannot backup")
        return False
    folder = os.path.join(BACKUPS_DIR, name)
    os.makedirs(folder, exist_ok=True)

    if not src or not os.path.exists(src):
        # If source not present, still write metadata (if none)
        meta = {
            "original_path": src,
            "description": script.get("description", ""),
            "timestamp": datetime.now().isoformat(),
            "files": {}
        }
        meta_path = os.path.join(folder, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=4, ensure_ascii=False)
        print(f"Metadata saved for {name}, but source file not found.")
        return False

    try:
        with open(src, "rb") as f:
            raw = f.read()
        compressed = compress_bytes(raw)
        base = os.path.basename(src)
        out_file = os.path.join(folder, base + ".gz")
        with open(out_file, "wb") as out:
            out.write(compressed)

        meta = {
            "original_path": src,
            "description": script.get("description", ""),
            "timestamp": datetime.now().isoformat(),
            "files": {
                base: {
                    "backup_file": os.path.basename(out_file),
                    "sha256": sha256_bytes(raw),
                    "orig_size": len(raw)
                }
            }
        }

        meta_path = os.path.join(folder, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=4, ensure_ascii=False)

        print(f" Backup saved for '{name}' -> {out_file}")
        return True
    except Exception as e:
        print("Backup failed:", e)
        return False

def reproduce_script_to_default(script):
    """
    Recreate backed-up files into ./reproduced/<script_name>/ by default.
    """
    name = script.get("name")
    folder = os.path.join(BACKUPS_DIR, name)
    if not os.path.exists(folder):
        print("No backup folder found for:", name)
        return
    target_dir = os.path.join(REPRODUCED_DIR, name)
    os.makedirs(target_dir, exist_ok=True)

    # read metadata to know files
    meta_path = os.path.join(folder, "metadata.json")
    files_written = 0
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
            files_meta = meta.get("files", {})
            for orig_name, info in files_meta.items():
                gz_name = info.get("backup_file")
                gz_path = os.path.join(folder, gz_name)
                if not os.path.exists(gz_path):
                    print("Backup data missing for", orig_name)
                    continue
                with open(gz_path, "rb") as gz:
                    try:
                        data = decompress_bytes(gz.read())
                    except Exception:
                        print("Failed decompressing", gz_path)
                        continue
                out_path = os.path.join(target_dir, orig_name)
                with open(out_path, "wb") as out:
                    out.write(data)
                # optionally verify sha256
                sha = info.get("sha256", "")
                if sha and sha != sha256_bytes(data):
                    print("Warning: sha256 mismatch for", orig_name)
                files_written += 1
        except Exception as e:
            print("Failed reading metadata:", e)
    else:
        # fallback - find any *.gz files
        for f in os.listdir(folder):
            if f.endswith(".gz"):
                gz_path = os.path.join(folder, f)
                with open(gz_path, "rb") as gz:
                    try:
                        data = decompress_bytes(gz.read())
                    except Exception:
                        print("Failed decompressing", gz_path)
                        continue
                # try to derive original name by stripping .gz
                orig_name = f[:-3]
                out_path = os.path.join(target_dir, orig_name)
                with open(out_path, "wb") as out:
                    out.write(data)
                files_written += 1

    if files_written:
        print(f" Reproduced {files_written} file(s) to {target_dir}")
    else:
        print("No files reproduced.")

# Pending backup background thread
class PendingBackupWorker(threading.Thread):
    def __init__(self, poll_interval=PENDING_POLL_INTERVAL):
        super().__init__(daemon=True)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()

    def run(self):
        # Run until no pending backups remain; then exit quietly.
        while not self._stop_event.is_set():
            scripts = load_scripts()
            pending_any = False
            changed = False
            for s in scripts:
                if s.get("pending_backup"):
                    pending_any = True
                    path = s.get("path")
                    if not is_running(path):
                        print(f"[pending] backing up '{s.get('name')}' now...")
                        ok = backup_script_to_folder(s)
                        if ok:
                            s.pop("pending_backup", None)
                            changed = True
            if changed:
                save_scripts(scripts)
            if not pending_any:
                # nothing pending -> exit quietly
                return
            # wait for a short interval before re-checking
            time.sleep(self.poll_interval)

    def stop(self):
        self._stop_event.set()

# CLI menu actions
def list_scripts(scripts):
    if not scripts:
        print("No scripts registered yet.")
        return
    print("\nRegistered scripts:")
    for i, s in enumerate(scripts, start=1):
        name = s.get("name", "(no name)")
        desc = s.get("description", "")
        path = s.get("path", "")
        pending = " [PENDING BACKUP]" if s.get("pending_backup") else ""
        print(f"{i}. {name}{pending}\n    Path: {path}\n    Desc: {desc}")

def add_script_interactive(scripts):
    name = input("Enter script name: ").strip()
    if not name:
        print("Name is required.")
        return
    # choose file
    print("Select the script file (file picker will open if available).")
    path = pick_file_dialog("Select script file")
    if not path:
        print("No path selected.")
        return
    desc = input("Enter description (optional): ").strip()
    # create entry
    script = {"name": name, "path": path, "description": desc}
    # check running and backup
    if is_running(path):
        print("Script appears to be running. Scheduling pending backup.")
        script["pending_backup"] = True
    else:
        backup_script_to_folder(script)
    scripts.append(script)
    save_scripts(scripts)
    print(" Script added.")

def modify_script_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to modify: ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    s = scripts[idx]
    print(f"Modifying '{s.get('name')}' (leave blank to keep current value).")
    new_name = input(f"Name [{s.get('name')}]: ").strip() or s.get('name')
    print("Choose new file path (or cancel to keep current).")
    new_path = pick_file_dialog("Select new script file")
    if not new_path:
        new_path = s.get('path')
    new_desc = input(f"Description [{s.get('description','')}]: ").strip() or s.get('description')
    s['name'] = new_name
    s['path'] = new_path
    s['description'] = new_desc
    # trigger backup if path changed or if no backup exists
    folder = os.path.join(BACKUPS_DIR, new_name)
    meta_path = os.path.join(folder, "metadata.json")
    need_backup = True
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
            # if original path matches and file exists in backup, consider ok
            files_meta = meta.get("files", {})
            if files_meta:
                need_backup = False
        except Exception:
            need_backup = True
    if is_running(new_path):
        print("Script appears to be running. Scheduling pending backup.")
        s["pending_backup"] = True
    elif need_backup:
        backup_script_to_folder(s)
        s.pop("pending_backup", None)
    save_scripts(scripts)
    print(" Modified.")

def delete_script_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to delete: ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    to_del = scripts.pop(idx)
    save_scripts(scripts)
    print(f"Deleted entry: {to_del.get('name')}")
    # Note: backups are left intact in backups/<name>/ for safety

def execute_script_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to execute: ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    s = scripts[idx]
    path = s.get("path")
    if not path or not os.path.exists(path):
        print("File does not exist.")
        return
    print(f"Launching '{s.get('name')}' in a new window...")
    launch_in_new_window(path)

def open_folder_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to open containing folder: ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    s = scripts[idx]
    open_containing_folder_and_select(s.get("path"))

def backup_now_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to back up now: ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    s = scripts[idx]
    if is_running(s.get("path")):
        print("Script appears to be running. Scheduling pending backup.")
        s["pending_backup"] = True
    else:
        backup_script_to_folder(s)
        s.pop("pending_backup", None)
    save_scripts(scripts)

def reproduce_interactive(scripts):
    list_scripts(scripts)
    if not scripts:
        return
    try:
        idx = int(input("Enter script number to reproduce (restore): ").strip()) - 1
    except Exception:
        print("Invalid selection.")
        return
    if idx < 0 or idx >= len(scripts):
        print("Invalid index.")
        return
    s = scripts[idx]
    reproduce_script_to_default(s)



def main():
    ensure_dirs()
    scripts = load_scripts()

    # Start background worker that handles pending backups quietly
    worker = PendingBackupWorker()
    worker.start()

    while True:
        scripts = load_scripts()
        print("\n==== Script Manager ====")
        print("1. List scripts")
        print("2. Add new script")
        print("3. Modify script")
        print("4. Delete script")
        print("5. Execute script (new window)")
        print("6. Open containing folder")
        print("7. Backup now (force)")
        print("8. Reproduce script (restore to ./reproduced/<name>)")
        print("9. Exit")
        choice = input("Select option: ").strip()

        if choice == "1":
            list_scripts(scripts)
        elif choice == "2":
            add_script_interactive(scripts)
        elif choice == "3":
            modify_script_interactive(scripts)
        elif choice == "4":
            delete_script_interactive(scripts)
        elif choice == "5":
            execute_script_interactive(scripts)
        elif choice == "6":
            open_folder_interactive(scripts)
        elif choice == "7":
            backup_now_interactive(scripts)
        elif choice == "8":
            reproduce_interactive(scripts)
        elif choice == "9":
            print("Exiting. Background pending backup worker will stop if idle.")
            break
        else:
            print("Invalid selection.")

    # allow worker to finish if it's currently processing; otherwise stop it
    try:
        worker.join(timeout=1)
    except Exception:
        pass

if __name__ == "__main__":
    if not PSUTIL_AVAILABLE:
        print("Warning: psutil not installed. Process-detection for 'running' checks will be disabled.")
        print("Install with: pip install psutil")
    main()