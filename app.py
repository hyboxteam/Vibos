import os
import re
import json
import tempfile
import subprocess
import time
import uuid
import shutil
import hashlib
import math
from flask import Flask, render_template, request, jsonify, send_file, session, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import requests
from PIL import Image
from io import BytesIO
import validators
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Create temp directory if not exists
TEMP_DIR = tempfile.mkdtemp()
app.config['TEMP_DIR'] = TEMP_DIR
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# HTML Template
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Downloader Pro - Download from Instagram, TikTok, YouTube & more</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        .loader {
            border-top-color: #3498db;
            animation: spin 1s linear infinite;
        }
        .format-btn {
            transition: all 0.2s;
        }
        .format-btn.selected {
            background-color: #3b82f6;
            color: white;
            border-color: #2563eb;
        }
        .format-btn.selected .text-gray-500 {
            color: #e0f2fe !important;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <!-- Header -->
        <header class="text-center mb-8">
            <div class="inline-block p-3 bg-white rounded-full shadow-lg mb-4">
                <svg class="w-12 h-12 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                </svg>
            </div>
            <h1 class="text-4xl font-bold text-gray-800 mb-2">Media Downloader Pro</h1>
            <p class="text-gray-600 text-lg">Download videos, images & thumbnails from social media platforms</p>
            
            <!-- Platform badges -->
            <div class="flex flex-wrap justify-center gap-2 mt-6">
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">📷 Instagram</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">🎵 TikTok</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">▶️ YouTube</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">🐦 Twitter/X</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">📘 Facebook</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">🤖 Reddit</span>
                <span class="px-4 py-2 bg-white shadow-sm rounded-full text-sm font-medium text-gray-700 border border-gray-200">🖼️ Direct Images</span>
            </div>
        </header>

        <!-- Main Card -->
        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 mb-8">
            <!-- URL Input Section -->
            <div class="mb-6">
                <label for="url" class="block text-gray-700 text-sm font-semibold mb-2">
                    📎 Paste URL here:
                </label>
                <div class="flex flex-col sm:flex-row gap-3">
                    <input type="url" id="url" 
                           placeholder="https://instagram.com/p/... or https://tiktok.com/@.../video/..." 
                           class="flex-1 px-4 py-3 border-2 border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 transition text-gray-700">
                    <button onclick="extractInfo()" 
                            class="bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-semibold py-3 px-8 rounded-xl transition transform hover:scale-105 shadow-md">
                        Extract
                    </button>
                </div>
                <p class="text-xs text-gray-400 mt-2">Supported: Instagram, TikTok, YouTube, Twitter, Facebook, Reddit, and direct images</p>
            </div>

            <!-- Loading Indicator -->
            <div id="loading" class="hidden text-center py-12">
                <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-16 w-16 mb-4 mx-auto"></div>
                <p class="text-gray-600 font-medium">Extracting media information...</p>
                <p class="text-sm text-gray-400 mt-2">This may take a few seconds</p>
            </div>

            <!-- Error Message -->
            <div id="error" class="hidden bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-3 rounded-lg mb-4">
            </div>

            <!-- Results Section -->
            <div id="results" class="hidden">
                <div class="border-t-2 border-gray-100 pt-6">
                    <!-- Media Info -->
                    <div class="flex flex-col md:flex-row gap-6 mb-6">
                        <!-- Thumbnail -->
                        <div class="md:w-1/3">
                            <div class="bg-gray-100 rounded-xl overflow-hidden shadow-lg">
                                <img id="thumbnail" src="" alt="Thumbnail" class="w-full h-auto object-cover">
                            </div>
                        </div>
                        
                        <!-- Details -->
                        <div class="md:w-2/3">
                            <h3 id="title" class="text-xl font-bold text-gray-800 mb-2"></h3>
                            <p id="uploader" class="text-gray-600 mb-2 flex items-center">
                                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                                </svg>
                                <span id="uploader-text"></span>
                            </p>
                            <p id="description" class="text-gray-500 text-sm mb-4"></p>
                            <div class="flex items-center gap-2">
                                <span id="platform-badge" class="bg-blue-100 text-blue-800 text-sm font-medium px-3 py-1 rounded-full"></span>
                                <span id="duration" class="text-sm text-gray-500"></span>
                            </div>
                        </div>
                    </div>

                    <!-- Formats Grid -->
                    <div class="mb-6">
                        <label class="block text-gray-700 text-sm font-semibold mb-3">
                            🎯 Available Formats (click to select):
                        </label>
                        <div id="formats" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-64 overflow-y-auto p-3 bg-gray-50 rounded-xl">
                            <!-- Formats will be populated here -->
                        </div>
                    </div>

                    <!-- Options -->
                    <div class="flex flex-wrap items-center gap-4 mb-6 p-4 bg-gray-50 rounded-xl">
                        <label class="flex items-center cursor-pointer">
                            <input type="checkbox" id="downloadThumb" class="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500">
                            <span class="ml-2 text-sm text-gray-700">📸 Also download thumbnail</span>
                        </label>
                        
                        <label class="flex items-center cursor-pointer">
                            <input type="checkbox" id="audioOnly" class="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500">
                            <span class="ml-2 text-sm text-gray-700">🎵 Audio only (MP3)</span>
                        </label>
                    </div>

                    <!-- Download Button -->
                    <button onclick="downloadMedia()" 
                            class="w-full bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white font-bold py-4 px-6 rounded-xl transition transform hover:scale-105 shadow-lg text-lg">
                        ⬇️ Download Selected Media
                    </button>
                </div>
            </div>
        </div>

        <!-- How to Use & Info -->
        <div class="grid md:grid-cols-2 gap-6">
            <div class="bg-white rounded-xl shadow-lg p-6">
                <h2 class="text-xl font-bold mb-4 flex items-center">
                    <span class="bg-blue-100 text-blue-800 w-8 h-8 rounded-full flex items-center justify-center mr-2">1</span>
                    How to use:
                </h2>
                <ol class="space-y-3 text-gray-700">
                    <li class="flex items-start">
                        <span class="text-blue-500 font-bold mr-2">•</span>
                        Copy the URL of any video/image
                    </li>
                    <li class="flex items-start">
                        <span class="text-blue-500 font-bold mr-2">•</span>
                        Paste it in the input box above
                    </li>
                    <li class="flex items-start">
                        <span class="text-blue-500 font-bold mr-2">•</span>
                        Click "Extract" to see available formats
                    </li>
                    <li class="flex items-start">
                        <span class="text-blue-500 font-bold mr-2">•</span>
                        Select your preferred quality/format
                    </li>
                    <li class="flex items-start">
                        <span class="text-blue-500 font-bold mr-2">•</span>
                        Click download and enjoy! 🎉
                    </li>
                </ol>
            </div>

            <div class="bg-white rounded-xl shadow-lg p-6">
                <h2 class="text-xl font-bold mb-4 flex items-center">
                    <span class="bg-purple-100 text-purple-800 w-8 h-8 rounded-full flex items-center justify-center mr-2">ℹ️</span>
                    Features:
                </h2>
                <ul class="space-y-3 text-gray-700">
                    <li class="flex items-center">
                        <svg class="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        Multiple quality options (120p - 4K)
                    </li>
                    <li class="flex items-center">
                        <svg class="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        Support for MP4, WebM, MP3 formats
                    </li>
                    <li class="flex items-center">
                        <svg class="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        Thumbnail download option
                    </li>
                    <li class="flex items-center">
                        <svg class="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        Direct image downloads
                    </li>
                </ul>
            </div>
        </div>

        <!-- Footer -->
        <footer class="text-center mt-8 text-sm text-gray-500">
            <p>⚠️ Please respect copyright and terms of service of respective platforms.</p>
            <p class="mt-2">Files are temporarily stored and automatically deleted after 1 hour.</p>
        </footer>
    </div>

    <script>
        let currentMediaInfo = null;
        let selectedFormatId = 'best';

        async function extractInfo() {
            const url = document.getElementById('url').value.trim();
            if (!url) {
                showError('Please enter a URL');
                return;
            }

            // Show loading, hide previous results
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
                    throw new Error(data.error || 'Failed to extract media info');
                }

                currentMediaInfo = data;
                displayResults(data);
            } catch (error) {
                showError(error.message);
            } finally {
                showLoading(false);
            }
        }

        function displayResults(info) {
            // Basic info
            document.getElementById('title').textContent = info.title || 'Untitled';
            document.getElementById('uploader-text').textContent = info.uploader ? `By: ${info.uploader}` : '';
            document.getElementById('description').textContent = info.description || '';
            document.getElementById('platform-badge').textContent = info.platform ? info.platform.charAt(0).toUpperCase() + info.platform.slice(1) : 'Unknown';
            
            // Duration
            if (info.duration) {
                const minutes = Math.floor(info.duration / 60);
                const seconds = info.duration % 60;
                document.getElementById('duration').textContent = `⏱️ ${minutes}:${seconds.toString().padStart(2, '0')}`;
            } else {
                document.getElementById('duration').textContent = '';
            }

            // Thumbnail
            if (info.thumbnail) {
                document.getElementById('thumbnail').src = info.thumbnail;
                document.getElementById('thumbnail').onerror = function() {
                    this.src = 'https://via.placeholder.com/300x200?text=No+Thumbnail';
                };
            } else {
                document.getElementById('thumbnail').src = 'https://via.placeholder.com/300x200?text=No+Thumbnail';
            }

            // Formats
            const formatsContainer = document.getElementById('formats');
            formatsContainer.innerHTML = '';

            if (info.formats && info.formats.length > 0) {
                // Sort formats by quality
                const sortedFormats = info.formats.sort((a, b) => (b.height || 0) - (a.height || 0));
                
                sortedFormats.forEach(format => {
                    const quality = format.height ? `${format.height}p` : 
                                   (format.format_note || format.quality || 'Unknown');
                    const ext = format.ext || 'mp4';
                    const isVideo = format.vcodec !== 'none';
                    const isAudio = format.acodec !== 'none' && format.vcodec === 'none';
                    
                    let qualityText = quality;
                    if (isAudio) qualityText = '🎵 Audio Only';
                    if (quality === 'Unknown' && isVideo) qualityText = '📹 Video';
                    
                    const filesize = format.filesize ? ` (${(format.filesize / 1024 / 1024).toFixed(2)} MB)` : '';
                    
                    const btn = document.createElement('button');
                    btn.className = 'format-btn p-3 border-2 rounded-lg hover:border-blue-500 transition text-sm text-left';
                    btn.setAttribute('data-format-id', format.format_id);
                    btn.innerHTML = `
                        <div class="font-semibold">${qualityText}</div>
                        <div class="text-xs ${isAudio ? 'text-green-600' : 'text-gray-500'}">${ext.toUpperCase()}${filesize}</div>
                    `;
                    
                    btn.onclick = () => selectFormat(format.format_id, btn);
                    formatsContainer.appendChild(btn);
                });
            } else {
                formatsContainer.innerHTML = '<p class="col-span-4 text-gray-500 text-center py-4">No formats available</p>';
            }

            // Show results
            document.getElementById('results').classList.remove('hidden');
            
            // Scroll to results
            document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function selectFormat(formatId, btn) {
            // Remove selected class from all
            document.querySelectorAll('.format-btn').forEach(b => {
                b.classList.remove('selected', 'bg-blue-600', 'text-white', 'border-blue-600');
            });
            
            // Add selected class to clicked
            btn.classList.add('selected', 'bg-blue-600', 'text-white', 'border-blue-600');
            
            selectedFormatId = formatId;
        }

        async function downloadMedia() {
            if (!currentMediaInfo) {
                showError('No media selected');
                return;
            }

            const url = document.getElementById('url').value.trim();
            const downloadThumb = document.getElementById('downloadThumb').checked;
            const audioOnly = document.getElementById('audioOnly').checked;

            try {
                showLoading(true);
                
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        url: url,
                        format_id: selectedFormatId,
                        download_thumbnail: downloadThumb,
                        audio_only: audioOnly
                    })
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Download failed');
                }

                if (data.file) {
                    // Trigger download
                    window.location.href = `/api/get_file/${data.file}`;
                    
                    // Download thumbnail if available
                    if (data.thumbnail) {
                        setTimeout(() => {
                            window.location.href = `/api/get_file/${data.thumbnail}`;
                        }, 500);
                    }

                    // Show success message
                    showSuccess('Download started!');
                }
            } catch (error) {
                showError(error.message);
            } finally {
                showLoading(false);
            }
        }

        function showLoading(show) {
            const loader = document.getElementById('loading');
            if (show) {
                loader.classList.remove('hidden');
            } else {
                loader.classList.add('hidden');
            }
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.classList.remove('hidden');
            
            // Auto hide after 5 seconds
            setTimeout(() => {
                errorDiv.classList.add('hidden');
            }, 5000);
        }

        function showSuccess(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.classList.remove('hidden');
            errorDiv.classList.remove('bg-red-50', 'border-red-500', 'text-red-700');
            errorDiv.classList.add('bg-green-50', 'border-green-500', 'text-green-700');
            
            setTimeout(() => {
                errorDiv.classList.add('hidden');
                errorDiv.classList.remove('bg-green-50', 'border-green-500', 'text-green-700');
                errorDiv.classList.add('bg-red-50', 'border-red-500', 'text-red-700');
            }, 3000);
        }

        function hideError() {
            document.getElementById('error').classList.add('hidden');
        }

        // Handle paste event
        document.getElementById('url').addEventListener('paste', (e) => {
            setTimeout(extractInfo, 100);
        });

        // Handle enter key
        document.getElementById('url').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                extractInfo();
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return INDEX_HTML

def detect_platform(url):
    """Detect platform from URL"""
    url_lower = url.lower()
    
    platforms = {
        'instagram': ['instagram.com', 'instagr.am'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com'],
        'youtube': ['youtube.com', 'youtu.be', 'm.youtube.com', 'youtube shorts'],
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
        'extract_flat': False,
        'force_generic_extractor': False,
        'socket_timeout': 30,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    # Skip unwanted formats
                    if f.get('format_note') in ['storyboard', 'sb0', 'sb1', 'sb2']:
                        continue
                    
                    format_info = {
                        'format_id': f.get('format_id', ''),
                        'ext': f.get('ext', ''),
                        'quality': f.get('quality', 0),
                        'filesize': f.get('filesize', 0) or f.get('filesize_approx', 0),
                        'format_note': f.get('format_note', ''),
                        'vcodec': f.get('vcodec', 'none'),
                        'acodec': f.get('acodec', 'none'),
                        'height': f.get('height', 0),
                        'width': f.get('width', 0),
                        'tbr': f.get('tbr', 0)
                    }
                    
                    # Include if it has video or audio
                    if format_info['vcodec'] != 'none' or format_info['acodec'] != 'none':
                        formats.append(format_info)
            
            # If no formats found, create a basic one
            if not formats:
                formats.append({
                    'format_id': 'best',
                    'ext': 'mp4',
                    'quality': 'best',
                    'filesize': 0,
                    'format_note': 'Best quality',
                    'vcodec': 'h264',
                    'acodec': 'aac',
                    'height': 1080
                })
            
            # Get thumbnail
            thumbnail = info.get('thumbnail', '')
            if not thumbnail and info.get('thumbnails'):
                thumbnail = info['thumbnails'][-1].get('url', '')
            
            return {
                'title': info.get('title', 'Media')[:100],
                'duration': info.get('duration', 0),
                'thumbnail': thumbnail,
                'formats': formats,
                'platform': platform,
                'uploader': info.get('uploader', info.get('channel', '')),
                'description': info.get('description', '')[:200]
            }
    except Exception as e:
        print(f"Error extracting info: {e}")
        # Fallback for direct images
        if platform == 'direct_image':
            return {
                'title': 'Image',
                'thumbnail': url,
                'formats': [{
                    'format_id': 'direct',
                    'ext': url.split('.')[-1].split('?')[0] if '.' in url else 'jpg',
                    'quality': 'original',
                    'filesize': 0,
                    'format_note': 'Original Image',
                    'vcodec': 'none',
                    'acodec': 'none',
                    'height': 0
                }],
                'platform': 'direct_image',
                'uploader': '',
                'description': 'Direct image download'
            }
        return None

def download_media(url, format_id='best', download_thumbnail=False, audio_only=False):
    """Download media using yt-dlp"""
    filename = str(uuid.uuid4())
    
    # Prepare output template
    if audio_only:
        output_path = os.path.join(TEMP_DIR, f"{filename}.%(ext)s")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_path,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        output_path = os.path.join(TEMP_DIR, f"{filename}.%(ext)s")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_path,
            'format': format_id if format_id != 'direct' else 'best',
        }
    
    thumb_path = os.path.join(TEMP_DIR, f"{filename}_thumb.jpg")
    
    try:
        if format_id == 'direct':
            # Direct image download
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            if response.status_code == 200:
                # Get extension from content-type or URL
                content_type = response.headers.get('content-type', '')
                ext = 'jpg'
                if 'jpeg' in content_type or 'jpg' in content_type:
                    ext = 'jpg'
                elif 'png' in content_type:
                    ext = 'png'
                elif 'gif' in content_type:
                    ext = 'gif'
                elif 'webp' in content_type:
                    ext = 'webp'
                
                filepath = os.path.join(TEMP_DIR, f"{filename}.{ext}")
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                if download_thumbnail and os.path.exists(filepath):
                    shutil.copy2(filepath, thumb_path)
                
                return filepath, thumb_path if download_thumbnail and os.path.exists(thumb_path) else None
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if audio_only:
                    # For audio, find the converted mp3 file
                    base_path = os.path.join(TEMP_DIR, filename)
                    downloaded_file = f"{base_path}.mp3"
                else:
                    downloaded_file = ydl.prepare_filename(info)
                    # Ensure file exists (handle different extensions)
                    if not os.path.exists(downloaded_file):
                        # Try common extensions
                        for ext in ['mp4', 'webm', 'mkv']:
                            test_path = os.path.join(TEMP_DIR, f"{filename}.{ext}")
                            if os.path.exists(test_path):
                                downloaded_file = test_path
                                break
                
                if download_thumbnail and info.get('thumbnail'):
                    try:
                        thumb_response = requests.get(info['thumbnail'], timeout=10)
                        if thumb_response.status_code == 200:
                            with open(thumb_path, 'wb') as f:
                                f.write(thumb_response.content)
                    except:
                        pass
                
                return downloaded_file, thumb_path if download_thumbnail and os.path.exists(thumb_path) else None
    except Exception as e:
        print(f"Download error: {e}")
        return None, None
    
    return None, None

@app.route('/api/extract', methods=['POST'])
@limiter.limit("10 per minute")
def extract():
    try:
        url = request.json.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'Please enter a URL'}), 400
        
        if not validators.url(url):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        platform = detect_platform(url)
        if platform == 'unknown':
            return jsonify({'error': 'Unsupported platform or invalid URL'}), 400
        
        info = get_media_info(url, platform)
        if not info:
            return jsonify({'error': 'Could not extract media info. The URL might be private or unavailable.'}), 400
        
        # Store URL in session for download
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
        audio_only = request.json.get('audio_only', False)
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        filepath, thumbpath = download_media(url, format_id, download_thumb, audio_only)
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'Download failed. Please try again.'}), 500
        
        # Cleanup old files (older than 1 hour)
        cleanup_old_files()
        
        return jsonify({
            'success': True,
            'file': os.path.basename(filepath),
            'thumbnail': os.path.basename(thumbpath) if thumbpath and os.path.exists(thumbpath) else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_file/<filename>')
def get_file(filename):
    """Serve downloaded file"""
    try:
        # Security check - prevent path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            response = send_file(filepath, as_attachment=True)
            
            # Schedule file deletion after sending
            @response.call_on_close
            def cleanup():
                try:
                    os.remove(filepath)
                except:
                    pass
            
            return response
        return jsonify({'error': 'File not found or expired'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'temp_dir': TEMP_DIR})

def cleanup_old_files():
    """Remove files older than 1 hour"""
    current_time = time.time()
    for filename in os.listdir(TEMP_DIR):
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.isfile(filepath):
            file_age = current_time - os.path.getctime(filepath)
            if file_age > 3600:  # 1 hour
                try:
                    os.remove(filepath)
                except:
                    pass

if __name__ == '__main__':
    print(f"* Starting Media Downloader Pro")
    print(f"* Temporary files directory: {TEMP_DIR}")
    print(f"* Visit http://localhost:5000 to use the app")
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
