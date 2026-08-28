import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'index.db')

# Supported file type extensions for filtering
FILE_TYPE_EXTENSIONS = {
    'documents': ('.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.md', '.log'),
    'images': ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff', '.heic', '.raw', '.psd'),
    'videos': ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'),
    'audio': ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'),
    'code': ('.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.json', '.yaml', '.yml', '.xml', '.sql', '.c', '.cpp', '.h', '.hpp', '.cs', '.java', '.rs', '.go', '.php', '.sh', '.bat', '.ps1', '.rb', '.swift', '.kt', '.lua', '.vue'),
    'archives': ('.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.cab', '.dmg'),
    'executables': ('.exe', '.msi', '.apk', '.jar'),
}

def get_connection(timeout=30.0):
    # Ensure directory exists before connecting
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    # Use check_same_thread=False since FastAPI runs on multiple threads
    conn = sqlite3.connect(DB_PATH, timeout=timeout, check_same_thread=False)
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn

def init_db():
    db_existed = os.path.exists(DB_PATH)
    if not db_existed:
        print(f"Database not found. Auto-creating '{DB_PATH}'...")
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrency, stability on Windows, and write speed
    cursor.execute('PRAGMA journal_mode = WAL')
    cursor.execute('PRAGMA synchronous = NORMAL')
    cursor.execute('PRAGMA temp_store = MEMORY')
    cursor.execute('PRAGMA cache_size = -64000')
    
    # Create main table to store file paths
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT COLLATE NOCASE,
            filepath TEXT UNIQUE,
            is_directory BOOLEAN
        )
    ''')
    
    # Indexes to speed up queries and exact matches
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_directory ON files(is_directory)')
    
    conn.commit()
    conn.close()
    
    if not db_existed:
        print("Database schema and indexes initialized successfully.")

def clear_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM files')
    conn.commit()
    conn.close()

def search_files(query, file_type='all', limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    
    wildcard_query = f'%{query}%'
    prefix_query = f'{query}%'
    params = [wildcard_query, wildcard_query]
    
    where_clauses = ["(filename LIKE ? OR filepath LIKE ?)"]
    
    file_type = (file_type or 'all').lower()
    
    if file_type in ('folders', 'folder', 'dir', 'directory'):
        where_clauses.append("is_directory = 1")
    elif file_type in ('files', 'file'):
        where_clauses.append("is_directory = 0")
    elif file_type in FILE_TYPE_EXTENSIONS:
        extensions = FILE_TYPE_EXTENSIONS[file_type]
        ext_conditions = " OR ".join(["filename LIKE ?" for _ in extensions])
        where_clauses.append(f"is_directory = 0 AND ({ext_conditions})")
        for ext in extensions:
            params.append(f"%{ext}")
            
    where_sql = " AND ".join(where_clauses)
    
    # Sorting: Folders first (is_directory DESC), then prefix matches, then alphabetical
    sql = f'''
        SELECT filename, filepath, is_directory
        FROM files
        WHERE {where_sql}
        ORDER BY is_directory DESC,
                 CASE WHEN filename LIKE ? THEN 0 ELSE 1 END,
                 filename ASC
        LIMIT ?
    '''
    
    params.append(prefix_query)
    params.append(limit)
    
    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    
    return [
        {'filename': r[0], 'filepath': r[1], 'is_directory': bool(r[2])}
        for r in results
    ]

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
