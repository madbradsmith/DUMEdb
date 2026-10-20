import os
import paramiko

HOSTNAME = "88.223.84.40"
PORT = 65002
USERNAME = "u232544718"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")
LOCAL_DIR = r"c:\Users\c6182\Desktop\folders\DUMEdb-WORK\website"
REMOTE_BASE = "/home/u232544718/domains/developumaiengine.com/public_html/dumedb"

def ensure_remote_dir(sftp, remote_dir):
    dirs = remote_dir.strip("/").split("/")
    current = ""
    for d in dirs:
        current += "/" + d
        try:
            sftp.stat(current)
        except IOError:
            print(f"Creating remote dir: {current}")
            sftp.mkdir(current)

def deploy():
    print(f"Connecting to Hostinger {USERNAME}@{HOSTNAME}:{PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOSTNAME, port=PORT, username=USERNAME, key_filename=KEY_PATH, timeout=20)
    sftp = ssh.open_sftp()

    ensure_remote_dir(sftp, REMOTE_BASE)
    ensure_remote_dir(sftp, f"{REMOTE_BASE}/assets")

    # Check and remove default.php if present
    try:
        sftp.remove(f"{REMOTE_BASE}/default.php")
        print("Removed placeholder default.php from Hostinger")
    except IOError:
        pass

    # Walk local website folder
    for root, dirs, files in os.walk(LOCAL_DIR):
        for f in files:
            local_path = os.path.join(root, f)
            rel_path = os.path.relpath(local_path, LOCAL_DIR).replace("\\", "/")
            remote_path = f"{REMOTE_BASE}/{rel_path}"
            
            # Ensure parent remote dir exists
            parent_remote = os.path.dirname(remote_path)
            ensure_remote_dir(sftp, parent_remote)
            
            size = os.path.getsize(local_path)
            print(f"Uploading {rel_path} ({size:,} bytes) -> {remote_path}...")
            sftp.put(local_path, remote_path)

    # Write .htaccess ensuring DirectoryIndex index.html
    htaccess_content = """DirectoryIndex index.html index.php
<IfModule mod_rewrite.c>
    RewriteEngine On
</IfModule>
"""
    with sftp.file(f"{REMOTE_BASE}/.htaccess", "w") as f:
        f.write(htaccess_content)
    print("Configured remote .htaccess with DirectoryIndex index.html")

    sftp.close()
    ssh.close()
    print("DEPLOYMENT COMPLETE! Live at https://dumedb.developumaiengine.com/")

if __name__ == "__main__":
    deploy()
