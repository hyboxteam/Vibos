import os
import re
import json
import tempfile
import subprocess
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import requests
from PIL import Image
from io import BytesIO
import validators
from dotenv import load_dotenv
import uuid
import shutil
from urllib.parse import urlparse

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Create temp directory if not exists
TEMP_DIR = tempfile.mkdtemp()
app.config['TEMP_DIR'] = TEMP_DIR

def cleanup_temp_files():
    """Cleanup old temp files"""
    for filename in os.listdir(TEMP_DIR):
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.getctime(filepath) < time.time() - 3600:  # 1 hour old
            try:
                os.remove(filepath)
            except:
                pass

def detect_platform(url):
    """Detect platform from URL"""
    url_lower = url.lower()
    
    platforms = {
        'instagram': ['instagram.com', 'instagr.am'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com'],
        'youtube': ['youtube.com', 'youtu.be', 'm.youtube.com'],
        'twitter': ['twitter.com', 'x.com'],
        'facebook': ['facebook.com', 'fb.com', 'fb.watch'],
        'reddit': ['reddit.com', 'redd.it'],
        'pinterest': ['pinterest.com', 'pin.it'],
        'imgur': ['imgur.com']
    }
    
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    
    # Check if it's a direct image URL
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    if any(ext in url_lower for ext in image_extensions):
        return 'direct_image'
    
    return 'unknown'

def get_media_info(url, platform):
    """Get media information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'force_generic_extractor': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    format_info = {
                        'format_id': f.get('format_id', ''),
                        'ext': f.get('ext', ''),
                        'quality': f.get('quality', 0),
                        'filesize': f.get('filesize', 0),
                        'format_note': f.get('format_note', ''),
                        'vcodec': f.get('vcodec', 'none'),
                        'acodec': f.get('acodec', 'none'),
                        'height': f.get('height', 0),
                        'width': f.get('width', 0)
                    }
                    
                    # Skip audio-only formats for video display
                    if format_info['vcodec'] != 'none' or platform == 'youtube':
                        formats.append(format_info)
            
            # Get thumbnail
            thumbnail = info.get('thumbnail', '')
            if platform == 'instagram' and not thumbnail:
                # Try to get image from Instagram
                thumbnail = extract_instagram_image(url)
            
            return {
                'title': info.get('title', 'Media'),
                'duration': info.get('duration', 0),
                'thumbnail': thumbnail,
                'formats': formats,
                'platform': platform,
                'uploader': info.get('uploader', ''),
                'description': info.get('description', '')[:200]
            }
    except Exception as e:
        print(f"Error extracting info: {e}")
        # Fallback for direct images
        if platform == 'direct_image':
            return {
                'title': 'Image',
                'thumbnail': url,
                'formats': [{'format_id': 'direct', 'ext': 'jpg', 'quality': 'original'}],
                'platform': 'direct_image'
            }
        return None

def extract_instagram_image(url):
    """Extract image from Instagram post"""
    try:
        # This is a simplified approach - for production, consider using Instagram's API
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            # Look for og:image meta tag
            import re
            og_image = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
            if og_image:
                return og_image.group(1)
    except:
        pass
    return None

def download_media(url, format_id='best', download_thumbnail=False):
    """Download media using yt-dlp"""
    filename = str(uuid.uuid4())
    output_path = os.path.join(TEMP_DIR, f"{filename}.%(ext)s")
    thumb_path = os.path.join(TEMP_DIR, f"{filename}_thumb.jpg")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': output_path,
        'format': format_id if format_id != 'direct' else 'best',
    }
    
    try:
        if format_id == 'direct':
            # Direct image download
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                ext = url.split('.')[-1].split('?')[0]
                if ext.lower() not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                    ext = 'jpg'
                
                filepath = os.path.join(TEMP_DIR, f"{filename}.{ext}")
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                if download_thumbnail:
                    shutil.copy(filepath, thumb_path)
                
                return filepath, thumb_path if download_thumbnail else None
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
                if download_thumbnail and info.get('thumbnail'):
                    thumb_response = requests.get(info['thumbnail'])
                    if thumb_response.status_code == 200:
                        with open(thumb_path, 'wb') as f:
                            f.write(thumb_response.content)
                
                return downloaded_file, thumb_path if download_thumbnail else None
    except Exception as e:
        print(f"Download error: {e}")
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/extract', methods=['POST'])
@limiter.limit("10 per minute")
def extract():
    url = request.json.get('url', '').strip()
    
    if not url or not validators.url(url):
        return jsonify({'error': 'Invalid URL'}), 400
    
    platform = detect_platform(url)
    if platform == 'unknown':
        return jsonify({'error': 'Unsupported platform'}), 400
    
    info = get_media_info(url, platform)
    if not info:
        return jsonify({'error': 'Could not extract media info'}), 400
    
    # Store URL in session for download
    session['last_url'] = url
    
    return jsonify(info)

@app.route('/api/download', methods=['POST'])
@limiter.limit("10 per minute")
def download():
    url = request.json.get('url', session.get('last_url', ''))
    format_id = request.json.get('format_id', 'best')
    download_thumb = request.json.get('download_thumbnail', False)
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    filepath, thumbpath = download_media(url, format_id, download_thumb)
    
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Download failed'}), 500
    
    # Cleanup old files
    cleanup_temp_files()
    
    return jsonify({
        'success': True,
        'file': os.path.basename(filepath),
        'thumbnail': os.path.basename(thumbpath) if thumbpath and os.path.exists(thumbpath) else None
    })

@app.route('/api/get_file/<filename>')
def get_file(filename):
    """Serve downloaded file"""
    filepath = os.path.join(TEMP_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    import time
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
