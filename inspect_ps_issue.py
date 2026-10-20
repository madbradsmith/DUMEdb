import os
import sys
import glob

output_lines = []

def log(msg):
    print(msg)
    output_lines.append(str(msg))

log("=== DIAGNOSING POWERSHELL HANG ===")

# 1. Check PSReadLine History File
appdata = os.getenv("APPDATA")
localappdata = os.getenv("LOCALAPPDATA")
userprofile = os.getenv("USERPROFILE")

history_paths = [
    os.path.join(appdata or "", "Microsoft", "Windows", "PowerShell", "PSReadLine", "ConsoleHost_history.txt"),
    os.path.join(appdata or "", "Microsoft", "PowerShell", "PSReadLine", "ConsoleHost_history.txt"),
]

for hp in history_paths:
    if os.path.exists(hp):
        size = os.path.getsize(hp)
        log(f"Found PSReadLine history file: {hp} (Size: {size} bytes)")
        if size > 10 * 1024 * 1024:
            log(f"WARNING: History file is very large ({size} bytes)!")
    else:
        log(f"PSReadLine history path not found or doesn't exist: {hp}")

# 2. Check PowerShell Profile Files
profile_locations = [
    os.path.join(userprofile or "", "Documents", "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1"),
    os.path.join(userprofile or "", "Documents", "WindowsPowerShell", "profile.ps1"),
    os.path.join(userprofile or "", "Documents", "PowerShell", "Microsoft.PowerShell_profile.ps1"),
    os.path.join(userprofile or "", "Documents", "PowerShell", "profile.ps1"),
    r"C:\Windows\System32\WindowsPowerShell\v1.0\profile.ps1",
    r"C:\Windows\System32\WindowsPowerShell\v1.0\Microsoft.PowerShell_profile.ps1"
]

for pl in profile_locations:
    if os.path.exists(pl):
        log(f"FOUND PROFILE FILE: {pl}")
        try:
            with open(pl, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                log(f"--- CONTENT OF {pl} ---")
                log(content)
                log("--- END CONTENT ---")
        except Exception as e:
            log(f"Error reading profile {pl}: {e}")

# 3. Check for any lock or leftover processes
import subprocess
try:
    res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq powershell.exe"], capture_output=True, text=True)
    log("Running powershell.exe processes:")
    log(res.stdout)
except Exception as e:
    log(f"Tasklist error: {e}")

with open("ps_diag_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

log("Saved report to ps_diag_result.txt")
