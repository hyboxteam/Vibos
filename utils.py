import os
import re
import hashlib
import time
from urllib.parse import urlparse

def sanitize_filename(filename):
    """Remove unsafe characters from filename"""
    # Remove path separators
    filename = filename.replace('/', '_').replace('\\', '_')
    # Remove other unsafe characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:195] + ext
    return filename

def get_file_hash(filepath):
    """Generate MD5 hash of file"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def is_valid_image_url(url):
    """Check if URL points to an image"""
    image_patterns = [
        r'\.(jpg|jpeg|png|gif|webp|bmp)(\?.*)?$',
        r'(instagram\.com/p/|imgur\.com/)'
    ]
    return any(re.search(pattern, url.lower()) for pattern in image_patterns)

def get_domain(url):
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.netloc

def format_filesize(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

def cleanup_old_files(directory, max_age=3600):
    """Remove files older than max_age seconds"""
    current_time = time.time()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            file_age = current_time - os.path.getctime(filepath)
            if file_age > max_age:
                try:
                    os.remove(filepath)
                except:
                    pass
