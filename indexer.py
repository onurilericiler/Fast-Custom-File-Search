import os
import sys
import time
from db import get_connection, init_db

# Configure UTF-8 output to prevent Windows console encoding crashes (e.g. cp1254)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BATCH_SIZE = 10000

# Directories to skip entirely during indexing
IGNORED_DIRS = {
    # Python & environments
    '__pycache__', '.pytest_cache', '.mypy_cache', '.tox', '.nox', '.venv', 'venv', 'env', '.env', 'virtualenv',
    # JavaScript / Node / Web frameworks
    'node_modules', '.next', '.nuxt', '.turbo', '.svelte-kit', '.cache', 'bower_components',
    # PHP & CMS Internal Framework Trees (WordPress, Drupal, Joomla, CodeIgniter, Opencart, etc.)
    'vendor', 'vendors', 'wp-admin', 'wp-includes', 'wp-snapshots', 'system', 'system_cache',
    'libraries', 'vqcache', 'vqmod', 'views_simplecache', 'w3tc', 'aspnet_client',
    # Caches, Logs, Temp & Sessions
    'cache', 'caches', '.cache', 'tmp', 'temp', 'temporary', 'logs', 'sessions', 'session',
    # Version control & IDEs
    '.git', '.svn', '.hg', '.idea', '.vscode', '.vs',
    # Build outputs & packages
    'dist', 'build', 'out', 'target', 'bin', 'obj', 'pkg', 'eggs', '.eggs', 'wheels',
    # Windows system & trash
    '$recycle.bin', 'system volume information', 'msocache', '$windows.~bt', '$windows.~ws'
}

# Individual junk files to skip
IGNORED_FILES = {
    'thumbs.db', 'desktop.ini', '.ds_store'
}

# File extensions to skip
IGNORED_EXTENSIONS = {
    '.pyc', '.pyo', '.pyd'
}

def index_directory(root_path):
    init_db()
    root_path = os.path.abspath(root_path)
    if not os.path.exists(root_path):
        print(f"Path does not exist: {root_path}")
        return

    conn = get_connection(timeout=60.0)
    # Optimizations for high-throughput bulk indexing
    conn.execute('PRAGMA synchronous = OFF')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA cache_size = -128000')
    conn.execute('PRAGMA temp_store = MEMORY')
    
    cursor = conn.cursor()
    
    print(f"Indexing {root_path} (skipping cache, venv, node_modules, etc.)...")
    start_time = time.time()
    
    files_to_insert = []
    total_indexed = 0

    # Collect top-level items in root_path for real-time percentage progress
    root_items = []
    try:
        with os.scandir(root_path) as it:
            for e in it:
                name_lower = e.name.lower()
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if name_lower not in IGNORED_DIRS and not name_lower.endswith('_dosyalar') and not name_lower.endswith('_files'):
                        root_items.append((e.name, e.path, True))
                else:
                    ext = os.path.splitext(name_lower)[1]
                    if name_lower not in IGNORED_FILES and ext not in IGNORED_EXTENSIONS:
                        root_items.append((e.name, e.path, False))
    except Exception as e:
        print(f"Error accessing root path: {e}")
        conn.close()
        return

    total_root = max(len(root_items), 1)
    current_root_idx = 0
    current_root_name = ""

    def get_percent():
        return (current_root_idx / total_root) * 100
    
    def flush(current_item=""):
        nonlocal total_indexed
        if not files_to_insert:
            return
        
        # Retry with backoff in case of transient Windows filesystem locks
        for attempt in range(5):
            try:
                cursor.executemany('''
                    INSERT OR IGNORE INTO files (filename, filepath, is_directory)
                    VALUES (?, ?, ?)
                ''', files_to_insert)
                conn.commit()
                total_indexed += len(files_to_insert)
                pct = get_percent()
                if current_item:
                    print(f"[{pct:5.1f}%] 📁 {current_root_name} > {current_item}")
                files_to_insert.clear()
                break
            except Exception as e:
                if attempt == 4:
                    raise
                print(f"Transient DB lock encountered ({e}), retrying {attempt + 1}/5...")
                time.sleep(0.5 * (attempt + 1))

    def scan_dir(path):
        try:
            with os.scandir(path) as it:
                for entry in it:
                    name_lower = entry.name.lower()
                    
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    
                    prefix = '📁' if is_dir else '📄'
                    
                    if is_dir:
                        # Skip ignored directories and web scraped folders
                        if name_lower in IGNORED_DIRS or name_lower.endswith('_dosyalar') or name_lower.endswith('_files'):
                            continue
                        files_to_insert.append((entry.name, entry.path, True))
                        if len(files_to_insert) >= BATCH_SIZE:
                            flush(f"{prefix} {entry.name}")
                        scan_dir(entry.path)
                    else:
                        # Skip ignored files and extensions
                        ext = os.path.splitext(name_lower)[1]
                        if name_lower in IGNORED_FILES or ext in IGNORED_EXTENSIONS:
                            continue
                        files_to_insert.append((entry.name, entry.path, False))
                        if len(files_to_insert) >= BATCH_SIZE:
                            flush(f"{prefix} {entry.name}")
        except PermissionError:
            pass # Skip folders without permission
        except Exception:
            pass # Skip other errors

    try:
        for idx, (name, path, is_dir) in enumerate(root_items, 1):
            current_root_name = name
            current_root_idx = idx - 1
            files_to_insert.append((name, path, is_dir))
            if is_dir:
                scan_dir(path)
            current_root_idx = idx
            pct = get_percent()
            prefix = '📁' if is_dir else '📄'
            print(f"[{pct:5.1f}%] ({idx}/{total_root}) {prefix} {name}")
            if len(files_to_insert) >= BATCH_SIZE:
                flush()

        flush() # Flush remaining
    finally:
        try:
            conn.execute('PRAGMA synchronous = NORMAL')
        except Exception:
            pass
        conn.close()
    
    end_time = time.time()
    print(f"[100.0%] Indexing completed in {end_time - start_time:.2f} seconds. Total items indexed: {total_indexed:,}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        index_directory(sys.argv[1])
    else:
        print("Usage: python indexer.py <directory_path>")
