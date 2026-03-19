import os
import sys
import tempfile
import uuid
import time
import json
from flask import Flask, request, jsonify, send_file
import yt_dlp
import requests
from urllib.parse import urlparse
import traceback

# Create Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# Use /tmp for temporary files (Vercel's writable directory)
TEMP_DIR = '/tmp/media_downloads'
os.makedirs(TEMP_DIR, exist_ok=True)

# HTML Template (embedded)
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
    </style>
</head>
<body class="bg-gray-50">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <div class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-800 mb-2">📥 Media Downloader Pro</h1>
            <p class="text-gray-600">Download from Instagram, TikTok, YouTube & more</p>
        </div>

        <div class="bg-white rounded-xl shadow-lg p-6 mb-6">
            <div class="mb-4">
                <input type="url" id="url" placeholder="Paste URL here (Instagram, TikTok, YouTube, etc.)" 
                       class="w-full px-4 py-3 border rounded-lg focus:outline-none focus:border-blue-500">
                <button onclick="extractInfo()" 
                        class="mt-3 w-full bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 px-4 rounded-lg transition">
                    Extract Media Info
                </button>
            </div>

            <div id="loading" class="hidden text-center py-8">
                <div class="loader rounded-full border-4 border-gray-200 h-12 w-12 mx-auto mb-4"></div>
                <p class="text-gray-600">Processing...</p>
            </div>

            <div id="error" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4"></div>

            <div id="results" class="hidden">
                <div class="border-t pt-4">
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

                    <div class="mb-4">
                        <label class="block text-sm font-bold mb-2">Select Quality:</label>
                        <select id="formatSelect" class="w-full p-2 border rounded">
                            <option value="best">Best Quality</option>
                        </select>
                    </div>

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
    </div>

    <script>
        let currentInfo = null;

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
            
            const select = document.getElementById('formatSelect');
            select.innerHTML = '';
            
            if (info.formats && info.formats.length > 0) {
                info.formats.forEach(format => {
                    const quality = format.height ? `${format.height}p` : (format.format_note || 'Unknown');
                    const option = document.createElement('option');
                    option.value = format.format_id;
                    option.textContent = `${quality} - ${format.ext || 'mp4'}`;
                    select.appendChild(option);
                });
            }
            
            document.getElementById('results').classList.remove('hidden');
        }

        async function downloadMedia() {
            if (!currentInfo) return;

            const url = document.getElementById('url').value.trim();
            const formatId = document.getElementById('formatSelect').value;
            const downloadThumb = document.getElementById('downloadThumb').checked;

            try {
                showLoading(true);
                
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        url: url,
                        format_id: formatId,
                        download_thumbnail: downloadThumb
                    })
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Download failed');
                }

                if (data.url) {
                    window.location.href = data.url;
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
    return 'unknown'

@app.route('/api/extract', methods=['POST'])
def extract():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        platform = detect_platform(url)
        
        # Simplified yt-dlp options for Vercel
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
                if info.get('formats'):
                    for f in info['formats'][:10]:  # Limit formats
                        if f.get('height') or f.get('format_note'):
                            formats.append({
                                'format_id': f.get('format_id', ''),
                                'ext': f.get('ext', 'mp4'),
                                'height': f.get('height', 0),
                                'format_note': f.get('format_note', ''),
                            })
                
                return jsonify({
                    'title': info.get('title', 'Media'),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': formats,
                    'platform': platform,
                    'uploader': info.get('uploader', '')
                })
        except Exception as e:
            return jsonify({'error': str(e)}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id', 'best')
        
        filename = f"{uuid.uuid4()}.%(ext)s"
        output_path = os.path.join(TEMP_DIR, filename)
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_path,
            'format': format_id,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            
            if os.path.exists(file_path):
                # Return a download URL
                download_id = str(uuid.uuid4())
                temp_link = f"/api/file/{download_id}"
                
                # Store file path temporarily
                global _temp_files
                if '_temp_files' not in globals():
                    _temp_files = {}
                _temp_files[download_id] = file_path
                
                return jsonify({'url': temp_link})
            
        return jsonify({'error': 'Download failed'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<file_id>')
def serve_file(file_id):
    if '_temp_files' in globals() and file_id in _temp_files:
        file_path = _temp_files[file_id]
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

# This is critical for Vercel - don't run the app when imported
if __name__ != '__main__':
    # For Vercel serverless
    pass

if __name__ == '__main__':
    app.run(debug=True, port=5000)
