#  Script Manager — Local Automation Indexer & Backup Tool

A simple yet powerful **Python-based script manager** that helps you **index, describe, back up, and reproduce** your automation scripts — all from a clean command-line interface.

This tool was built for developers who have **lots of small utility scripts** scattered across their system and want a **centralized, reproducible index** without relying on heavy frameworks or version control for every one of them.

---

##  Features

 **Manual Indexing**
- Add scripts one by one, with name, path, and description.  
- Keep all metadata in a single JSON file: `scripts.json`.

 **Automatic Backups**
- Every time you add or modify a script, the tool automatically:
  - Creates a compressed backup (`.gz`) under `./backups/<script_name>/`
  - Stores metadata (hash, timestamp, description)
  - Checks if the script is currently running:
    - If **running**, schedules a backup automatically after completion.
    - If **idle**, backs up immediately.

 **Reproducibility**
- Easily restore any backed-up script with one option:
  - Recreates files under `./reproduced/<script_name>/`.

 **Quiet Background Mode**
- Runs a background worker that periodically checks for pending backups (scripts that were busy earlier).

 **Interactive Menu**
- CLI options for:
  - Listing all scripts  
  - Adding / modifying / deleting  
  - Executing scripts in a new window  
  - Opening the containing folder  
  - Forcing backups  
  - Reproducing files

 **Cross-Platform**
- Works on **Windows, macOS, and Linux**  
- Uses the OS-native method to open folders or launch files.

---

## 📁 Directory Structure

