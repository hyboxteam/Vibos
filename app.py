import os
import re
import json
import tempfile
import time
import uuid
import shutil
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import requests
import validators
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Rate limiting with memory storage (no Redis needed)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Create temp directory
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'media_downloader')
os.makedirs(TEMP_DIR, exist_ok=True)
app.config['TEMP_DIR'] = TEMP_DIR

# HTML Template (simplified)
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Downloader Pro</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .loader { border-top-color: #3498db; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .format-btn.selected { background-color: #3b82f6; color: white; border-color: #2563eb; }
    </style>
</head>
<body class="bg-gray-50">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <!-- Header -->
        <div class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-800 mb-2">📥 Media Downloader Pro</h1>
            <p class="text-gray-600">Download from Instagram, TikTok, YouTube & more</p>
        </div>

        <!-- Main Card -->
        <div class="bg-white rounded-xl shadow-lg p-6 mb-6">
            <!-- URL Input -->
            <div class="mb-4">
                <input type="url" id="url" placeholder="Paste URL here..." 
                       class="w-full px-4 py-3 border rounded-lg focus:outline-none focus:border-blue-500">
                <button onclick="extractInfo()" 
                        class="mt-3 w-full bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 px-4 rounded-lg transition">
                    Extract Media Info
                </button>
            </div>

            <!-- Loading -->
            <div id="loading" class="hidden text-center py-8">
                <div class="loader rounded-full border-4 border-gray-200 h-12 w-12 mx-auto mb-4"></div>
                <p class="text-gray-600">Processing...</p>
            </div>

            <!-- Error -->
            <div id="error" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4"></div>

            <!-- Results -->
            <div id="results" class="hidden">
                <div class="border-t pt-4">
                    <!-- Media Info -->
                    <div class="flex flex-col md:flex-row gap-4 mb-4">
                        <div class="md:w-1/3">
                            <img id="thumbnail" src="" alt="Thumbnail" class="rounded-lg w-full">
                        </div>
                        <div class="md:w-2/3">
                            <h3 id="title" class="text-lg font-bold mb-2"></h3>
                            <p id="uploader" class="text-gray-600 text-sm mb-2"></p>
                            <p id="platform" class="text-sm bg-gray-100 inline-block px-2 py-1 rounded"></p>
                        </div>
                    </div>

                    <!-- Formats -->
                    <div class="mb-4">
                        <label class="block text-sm font-bold mb-2">Select Format:</label>
                        <div id="formats" class="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto p-2 border rounded"></div>
                    </div>

                    <!-- Options -->
                    <div class="mb-4">
                        <label class="flex items-center">
                            <input type="checkbox" id="downloadThumb" class="mr-2">
                            <span class="text-sm">Download thumbnail also</span>
                        </label>
                    </div>

                    <button onclick="downloadMedia()" 
                            class="w-full bg-green-500 hover:bg-green-600 text-white font-bold py-3 px-4 rounded-lg transition">
                        Download Selected
                    </button>
                </div>
            </div>
        </div>

        <!-- Supported Platforms -->
        <div class="bg-white rounded-xl shadow-lg p-6">
            <h2 class="text-lg font-bold mb-3">Supported Platforms:</h2>
            <div class="flex flex-wrap gap-2">
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">📷 Instagram</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">🎵 TikTok</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">▶️ YouTube</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">🐦 Twitter/X</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">📘 Facebook</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">🔴 Reddit</span>
                <span class="bg-gray-100 px-3 py-1 rounded-full text-sm">🖼️ Direct Images</span>
            </div>
        </div>
    </div>

    <script>
        let currentInfo = null;
        let selectedFormat = 'best';

        async function extractInfo() {
            const url = document.getElementById('url').value.trim();
            if (!url) {
                showError('Please enter a URL');
                return;
            }

            showLoading(true);
            hideError();
            document.getElementById('results').classList.add('hidden');

            try {
                const response = await fetch('/api/extract', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Extraction failed');
                }

                currentInfo = data;
                displayResults(data);
            } catch (error) {
                showError(error.message);
            } finally {
                showLoading(false);
            }
        }

        function displayResults(info) {
            document.getElementById('title').textContent = info.title || 'Untitled';
            document.getElementById('uploader').textContent = info.uploader ? `By: ${info.uploader}` : '';
            document.getElementById('platform').textContent = info.platform || 'Unknown';
            document.getElementById('thumbnail').src = info.thumbnail || 'https://via.placeholder.com/300';
            
            const formatsDiv = document.getElementById('formats');
            formatsDiv.innerHTML = '';
            
            if (info.formats && info.formats.length > 0) {
                info.formats.forEach(format => {
                    const quality = format.height ? `${format.height}p` : (format.format_note || 'Unknown');
                    const btn = document.createElement('button');
                    btn.className = 'format-btn p-2 text-left border rounded hover:bg-blue-50 text-sm';
                    btn.setAttribute('data-format-id', format.format_id);
                    btn.innerHTML = `${quality} - ${format.ext || 'mp4'}`;
                    btn.onclick = () => {
                        selectedFormat = format.format_id;
                        document.querySelectorAll('.format-btn').forEach(b => b.classList.remove('selected'));
                        btn.classList.add('selected');
                    };
                    formatsDiv.appendChild(btn);
                });
            }
            
            document.getElementById('results').classList.remove('hidden');
        }

        async function downloadMedia() {
            if (!currentInfo) return;

            const url = document.getElementById('url').value.trim();
            const downloadThumb = document.getElementById('downloadThumb').checked;

            try {
                showLoading(true);
                
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        url: url,
                        format_id: selectedFormat,
                        download_thumbnail: downloadThumb
                    })
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Download failed');
                }

                if (data.file) {
                    window.location.href = `/api/get_file/${data.file}`;
                    if (data.thumbnail) {
                        setTimeout(() => window.location.href = `/api/get_file/${data.thumbnail}`, 500);
                    }
                }
            } catch (error) {
                showError(error.message);
            } finally {
                showLoading(false);
            }
        }

        function showLoading(show) {
            document.getElementById('loading').classList.toggle('hidden', !show);
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.classList.remove('hidden');
            setTimeout(() => errorDiv.classList.add('hidden'), 5000);
        }

        function hideError() {
            document.getElementById('error').classList.add('hidden');
        }

        document.getElementById('url').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') extractInfo();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return INDEX_HTML

def detect_platform(url):
    url = url.lower()
    platforms = {
        'instagram': ['instagram.com', 'instagr.am'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com'],
        'youtube': ['youtube.com', 'youtu.be'],
        'twitter': ['twitter.com', 'x.com'],
        'facebook': ['facebook.com', 'fb.com'],
        'reddit': ['reddit.com']
    }
    
    for platform, domains in platforms.items():
        if any(domain in url for domain in domains):
            return platform
    
    if any(ext in url for ext in ['.jpg', '.jpeg', '.png', '.gif']):
        return 'direct_image'
    
    return 'unknown'

def get_media_info(url, platform):
    try:
        if platform == 'direct_image':
            return {
                'title': 'Image',
                'thumbnail': url,
                'formats': [{'format_id': 'direct', 'ext': 'jpg', 'quality': 'original'}],
                'platform': 'Image',
                'uploader': ''
            }
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('height') or f.get('format_note'):
                    formats.append({
                        'format_id': f.get('format_id', ''),
                        'ext': f.get('ext', 'mp4'),
                        'height': f.get('height', 0),
                        'format_note': f.get('format_note', ''),
                        'filesize': f.get('filesize', 0)
                    })
            
            return {
                'title': info.get('title', 'Video')[:100],
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats[:20],  # Limit to 20 formats
                'platform': platform,
                'uploader': info.get('uploader', '')
            }
    except Exception as e:
        print(f"Error: {e}")
        return None

def download_media(url, format_id, download_thumb):
    filename = str(uuid.uuid4())
    
    if format_id == 'direct':
        try:
            response = requests.get(url, stream=True, timeout=30)
            if response.status_code == 200:
                ext = 'jpg'
                filepath = os.path.join(TEMP_DIR, f"{filename}.{ext}")
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(8192):
                        f.write(chunk)
                return filepath, None
        except:
            return None, None
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(TEMP_DIR, f"{filename}.%(ext)s"),
            'format': format_id,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            
            thumb_path = None
            if download_thumb and info.get('thumbnail'):
                try:
                    thumb_response = requests.get(info['thumbnail'], timeout=10)
                    if thumb_response.status_code == 200:
                        thumb_path = os.path.join(TEMP_DIR, f"{filename}_thumb.jpg")
                        with open(thumb_path, 'wb') as f:
                            f.write(thumb_response.content)
                except:
                    pass
            
            return filepath, thumb_path
    except Exception as e:
        print(f"Download error: {e}")
        return None, None

@app.route('/api/extract', methods=['POST'])
@limiter.limit("10 per minute")
def extract():
    try:
        url = request.json.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        if not validators.url(url):
            return jsonify({'error': 'Invalid URL'}), 400
        
        platform = detect_platform(url)
        if platform == 'unknown':
            return jsonify({'error': 'Unsupported platform'}), 400
        
        info = get_media_info(url, platform)
        if not info:
            return jsonify({'error': 'Could not extract media info'}), 400
        
        session['last_url'] = url
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
@limiter.limit("10 per minute")
def download():
    try:
        url = request.json.get('url', session.get('last_url', ''))
        format_id = request.json.get('format_id', 'best')
        download_thumb = request.json.get('download_thumbnail', False)
        
        if not url:
            return jsonify({'error': 'No URL'}), 400
        
        filepath, thumbpath = download_media(url, format_id, download_thumb)
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'Download failed'}), 500
        
        # Cleanup old files
        for f in os.listdir(TEMP_DIR):
            fpath = os.path.join(TEMP_DIR, f)
            if os.path.getctime(fpath) < time.time() - 3600:
                try:
                    os.remove(fpath)
                except:
                    pass
        
        return jsonify({
            'success': True,
            'file': os.path.basename(filepath),
            'thumbnail': os.path.basename(thumbpath) if thumbpath else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_file/<filename>')
def get_file(filename):
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        return jsonify({'error': 'File not found'}), 404
    except:
        return jsonify({'error': 'Error serving file'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
