#!/usr/bin/env python3
"""
Text-to-Speech and Voice Cloning Web Application
A comprehensive TTS tool with ElevenLabs and multilingual support
"""

from flask import Flask, render_template_string, request, send_file, jsonify, flash, redirect, url_for
import os
import tempfile
import uuid
from werkzeug.utils import secure_filename
import speech_recognition as sr
from pydub import AudioSegment
import io
import base64
import threading
import time
from datetime import datetime
import platform
import requests
import json

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create necessary directories
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# Supported languages for different engines
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'es': 'Spanish', 
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'nl': 'Dutch',
    'pl': 'Polish',
    'ru': 'Russian',
    'sv': 'Swedish',
    'da': 'Danish',
    'no': 'Norwegian',
    'fi': 'Finnish',
    'hu': 'Hungarian',
    'cs': 'Czech',
    'sk': 'Slovak',
    'ro': 'Romanian',
    'bg': 'Bulgarian',
    'hr': 'Croatian',
    'sl': 'Slovenian',
    'et': 'Estonian',
    'lv': 'Latvian',
    'lt': 'Lithuanian'
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg', 'm4a', 'flac'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class ElevenLabsAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = ELEVENLABS_API_URL
        self.headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
    
    def get_voices(self):
        """Get available ElevenLabs voices"""
        try:
            if not self.api_key:
                return []
            
            response = requests.get(f"{self.base_url}/voices", 
                                  headers={"xi-api-key": self.api_key})
            
            if response.status_code == 200:
                voices_data = response.json()
                voices = []
                for voice in voices_data.get('voices', []):
                    voices.append({
                        'id': voice['voice_id'],
                        'name': voice['name'],
                        'category': voice.get('category', 'Unknown'),
                        'description': voice.get('description', ''),
                        'preview_url': voice.get('preview_url', ''),
                        'labels': voice.get('labels', {})
                    })
                return voices
            else:
                print(f"Error fetching ElevenLabs voices: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error in get_voices: {e}")
            return []
    
    def text_to_speech(self, text, voice_id, stability=0.5, similarity_boost=0.5, style=0.0):
        """Generate speech using ElevenLabs API"""
        try:
            if not self.api_key:
                raise Exception("ElevenLabs API key not provided")
            
            url = f"{self.base_url}/text-to-speech/{voice_id}"
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",  # Supports multiple languages
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": True
                }
            }
            
            response = requests.post(url, json=data, headers=self.headers)
            
            if response.status_code == 200:
                # Save audio file
                filename = f"elevenlabs_{uuid.uuid4().hex[:8]}.mp3"
                filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return filepath
            else:
                error_msg = f"ElevenLabs API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f" - {error_data.get('detail', {}).get('message', 'Unknown error')}"
                except:
                    pass
                raise Exception(error_msg)
                
        except Exception as e:
            print(f"Error in ElevenLabs TTS: {e}")
            return None
    
    def clone_voice(self, audio_file_path, voice_name, description="Custom cloned voice"):
        """Clone a voice from audio sample"""
        try:
            if not self.api_key:
                raise Exception("ElevenLabs API key not provided")
            
            url = f"{self.base_url}/voices/add"
            
            # Read audio file
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()
            
            files = {
                'files': ('sample.mp3', audio_data, 'audio/mpeg')
            }
            
            data = {
                'name': voice_name,
                'description': description,
                'labels': json.dumps({"custom": "true"})
            }
            
            headers = {"xi-api-key": self.api_key}
            
            response = requests.post(url, files=files, data=data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('voice_id')
            else:
                error_msg = f"Voice cloning error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f" - {error_data.get('detail', {}).get('message', 'Unknown error')}"
                except:
                    pass
                raise Exception(error_msg)
                
        except Exception as e:
            print(f"Error in voice cloning: {e}")
            return None

class TTSEngine:
    def __init__(self):
        self.elevenlabs = ElevenLabsAPI(ELEVENLABS_API_KEY)
        self.custom_voices = {}
        
    def get_elevenlabs_voices(self):
        """Get available ElevenLabs voices"""
        return self.elevenlabs.get_voices()
    
    def text_to_speech_elevenlabs(self, text, voice_id, stability=0.5, similarity_boost=0.5, style=0.0):
        """Generate speech using ElevenLabs"""
        return self.elevenlabs.text_to_speech(text, voice_id, stability, similarity_boost, style)
    
    def speech_to_text(self, audio_file_path):
        """Convert speech to text"""
        try:
            r = sr.Recognizer()
            
            # Convert audio to WAV if needed
            audio = AudioSegment.from_file(audio_file_path)
            wav_path = audio_file_path.rsplit('.', 1)[0] + '_converted.wav'
            audio.export(wav_path, format="wav")
            
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                text = r.recognize_google(audio_data)
                
            # Clean up converted file
            if os.path.exists(wav_path):
                os.remove(wav_path)
                
            return text
        except Exception as e:
            print(f"Error in speech recognition: {e}")
            return None
    
    def clone_voice_from_audio(self, audio_file_path, voice_name, description=""):
        """Clone voice using ElevenLabs"""
        return self.elevenlabs.clone_voice(audio_file_path, voice_name, description)

# Initialize TTS engine
tts_engine = TTSEngine()

# HTML Templates
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Studio - ElevenLabs Edition</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
        }
        
        .container {
            background: white;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: #4facfe;
            padding: 30px;
            text-align: center;
            color: white;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .api-status {
            margin-top: 15px;
            padding: 10px;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        
        .api-connected {
            background: rgba(76, 175, 80, 0.2);
            border: 1px solid rgba(76, 175, 80, 0.5);
        }
        
        .api-disconnected {
            background: rgba(244, 67, 54, 0.2);
            border: 1px solid rgba(244, 67, 54, 0.5);
        }
        
        .content {
            padding: 40px;
        }
        
        .tabs {
            display: flex;
            margin-bottom: 30px;
            background: #f8f9fa;
            border-radius: 10px;
            padding: 5px;
        }
        
        .tab {
            flex: 1;
            padding: 15px 20px;
            text-align: center;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
        }
        
        .tab.active {
            background: #4facfe;
            color: white;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        
        .form-control {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #4facfe;
        }
        
        textarea.form-control {
            min-height: 120px;
            resize: vertical;
        }
        
        .btn {
            background: #4facfe;
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.3s ease;
        }
        
        .btn:hover {
            transform: translateY(-2px);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        
        .audio-player {
            margin-top: 20px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            text-align: center;
        }
        
        .upload-area {
            border: 2px dashed #4facfe;
            border-radius: 10px;
            padding: 40px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .upload-area:hover {
            background: #f8f9fa;
        }
        
        .upload-area.dragover {
            background: #ffebee;
            border-color: #e91e63;
        }
        
        .file-info {
            margin-top: 15px;
            padding: 10px;
            background: #e8f5e8;
            border-radius: 5px;
            display: none;
        }
        
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #4facfe;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .voice-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            max-height: 400px;
            overflow-y: auto;
            padding: 10px;
            border: 1px solid #e9ecef;
            border-radius: 8px;
        }
        
        .voice-card {
            padding: 15px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            background: white;
        }
        
        .voice-card:hover {
            border-color: #4facfe;
            transform: translateY(-2px);
        }
        
        .voice-card.selected {
            border-color: #4facfe;
            background: #4facfe26;
        }
        
        .voice-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }
        
        .voice-category {
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 8px;
        }
        
        .voice-description {
            font-size: 0.8rem;
            color: #888;
            line-height: 1.4;
        }
        
        .settings-row {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .range-group {
            text-align: center;
        }
        
        .range-group label {
            font-size: 0.9rem;
            margin-bottom: 5px;
        }
        
        .range-value {
            font-weight: 600;
            color: #4facfe;
        }
        
        @media (max-width: 768px) {
            .row {
                grid-template-columns: 1fr;
            }
            
            .settings-row {
                grid-template-columns: 1fr;
            }
            
            .voice-grid {
                grid-template-columns: 1fr;
            }
            
            .container {
                margin: 10px;
            }
            
            .content {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎤 Voice Studio</h1>
            <p>Professional Text-to-Speech with ElevenLabs AI</p>
            <div class="api-status {% if api_connected %}api-connected{% else %}api-disconnected{% endif %}">
                {% if api_connected %}
                    ElevenLabs API Connected - {{ voice_count }} voices available
                {% else %}
                    ElevenLabs API Key Required - Add ELEVENLABS_API_KEY to environment
                {% endif %}
            </div>
        </div>
        
        <div class="content">
            <div class="tabs">
                <div class="tab active" onclick="switchTab('tts')">Text to Speech</div>
                <div class="tab" onclick="switchTab('stt')">Speech to Text</div>
                <div class="tab" onclick="switchTab('voices')">Voice Library</div>
            </div>
            
            <!-- Text to Speech Tab -->
            <div id="tts-tab" class="tab-content active">
                <form id="tts-form" onsubmit="generateSpeech(event)">
                    <div class="form-group">
                        <label for="text-input">Enter Text to Convert:</label>
                        <textarea id="text-input" name="text" class="form-control" 
                                 placeholder="Type your text here..." required></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label>Select Voice:</label>
                        <div class="voice-grid" id="voice-selection">
                            {% for voice in elevenlabs_voices %}
                            <div class="voice-card" onclick="selectVoice('{{ voice.id }}', this)" data-voice-id="{{ voice.id }}">
                                <div class="voice-name">{{ voice.name }}</div>
                                <div class="voice-category">{{ voice.category }}</div>
                                <div class="voice-description">{{ voice.description[:100] }}...</div>
                            </div>
                            {% endfor %}
                        </div>
                        <input type="hidden" id="selected-voice" name="voice_id" required>
                    </div>
                    
                    <div class="settings-row">
                        <div class="range-group">
                            <label for="stability">Stability</label>
                            <input type="range" id="stability" name="stability" min="0" max="1" step="0.1" value="0.5" class="form-control">
                            <small>Current: <span id="stability-value" class="range-value">0.5</span></small>
                        </div>
                        
                        <div class="range-group">
                            <label for="similarity">Similarity Boost</label>
                            <input type="range" id="similarity" name="similarity" min="0" max="1" step="0.1" value="0.5" class="form-control">
                            <small>Current: <span id="similarity-value" class="range-value">0.5</span></small>
                        </div>
                        
                        <div class="range-group">
                            <label for="style">Style</label>
                            <input type="range" id="style" name="style" min="0" max="1" step="0.1" value="0.0" class="form-control">
                            <small>Current: <span id="style-value" class="range-value">0.0</span></small>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn">Generate Speech</button>
                </form>
                
                <div id="tts-loading" class="loading">
                    <div class="spinner"></div>
                    <p>Generating speech with ElevenLabs AI...</p>
                </div>
                
                <div id="tts-result" class="audio-player" style="display: none;">
                    <h3>Generated Audio:</h3>
                    <audio id="audio-player" controls style="width: 100%; margin: 10px 0;">
                        Your browser does not support the audio element.
                    </audio>
                    <br>
                    <a id="download-link" class="btn" style="display: inline-block; margin-top: 10px; text-decoration: none">📥 Download Audio</a>
                </div>
            </div>
            
            <!-- Speech to Text Tab -->
            <div id="stt-tab" class="tab-content">
                <form id="stt-form" onsubmit="convertSpeechToText(event)">
                    <div class="form-group">
                        <label>Upload Audio File:</label>
                        <div class="upload-area" onclick="document.getElementById('audio-file').click()">
                            <p>Click to select audio file or drag & drop</p>
                            <small>Supported formats: WAV, MP3, OGG, M4A, FLAC (Max 16MB)</small>
                            <input type="file" id="audio-file" name="audio_file" 
                                   accept=".wav,.mp3,.ogg,.m4a,.flac" style="display: none;" 
                                   onchange="handleFileSelect(this)">
                        </div>
                        <div id="file-info" class="file-info"></div>
                    </div>
                    
                    <button type="submit" class="btn" id="stt-btn" disabled>Convert to Text</button>
                </form>
                
                <div id="stt-loading" class="loading">
                    <div class="spinner"></div>
                    <p>Processing audio...</p>
                </div>
                
                <div id="stt-result" style="display: none;">
                    <h3>Transcribed Text:</h3>
                    <div id="transcribed-text" style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 10px;"></div>
                    <button onclick="copyToClipboard()" class="btn" style="margin-top: 10px;">Copy Text</button>
                </div>
            </div>
            
            <!-- Voice Library Tab -->
            <div id="voices-tab" class="tab-content">
                <h3>ElevenLabs Voice Library</h3>
                <div class="voice-grid">
                    {% for voice in elevenlabs_voices %}
                    <div class="voice-card" onclick="testVoice('{{ voice.id }}')">
                        <div class="voice-name">{{ voice.name }}</div>
                        <div class="voice-category">{{ voice.category }}</div>
                        <div class="voice-description">{{ voice.description }}</div>
                        <button type="button" class="btn" style="margin-top: 10px; padding: 8px 15px; font-size: 14px;">
                            Test Voice
                        </button>
                    </div>
                    {% endfor %}
                </div>
            </div>
            
            <!-- Voice Cloning Tab -->
            <div id="clone-tab" class="tab-content">
                <h3>Voice Cloning</h3>
                <p style="margin-bottom: 20px; color: #666;">Upload an audio sample to create a custom voice clone using ElevenLabs AI.</p>
                
                <form id="clone-form" onsubmit="cloneVoice(event)">
                    <div class="form-group">
                        <label for="voice-name">Voice Name:</label>
                        <input type="text" id="voice-name" name="voice_name" class="form-control" 
                               placeholder="Enter a name for your cloned voice" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="voice-description">Description (Optional):</label>
                        <input type="text" id="voice-description" name="voice_description" class="form-control" 
                               placeholder="Describe the voice characteristics">
                    </div>
                    
                    <div class="form-group">
                        <label>Upload Voice Sample:</label>
                        <div class="upload-area" onclick="document.getElementById('clone-audio-file').click()">
                            <p>Click to select audio file for voice cloning</p>
                            <small>High-quality audio recommended (1-5 minutes, clear speech)</small>
                            <input type="file" id="clone-audio-file" name="clone_audio_file" 
                                   accept=".wav,.mp3,.ogg,.m4a,.flac" style="display: none;" 
                                   onchange="handleCloneFileSelect(this)">
                        </div>
                        <div id="clone-file-info" class="file-info"></div>
                    </div>
                    
                    <button type="submit" class="btn" id="clone-btn" disabled>Clone Voice</button>
                </form>
                
                <div id="clone-loading" class="loading">
                    <div class="spinner"></div>
                    <p>Cloning voice with ElevenLabs AI...</p>
                </div>
                
                <div id="clone-result" style="display: none;">
                    <h3>Voice Cloning Result:</h3>
                    <div id="clone-message" style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 10px;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let selectedVoiceId = null;
        
        // Tab switching
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName + '-tab').classList.add('active');
        }
        
        // Voice selection
        function selectVoice(voiceId, element) {
            document.querySelectorAll('.voice-card').forEach(card => card.classList.remove('selected'));
            element.classList.add('selected');
            selectedVoiceId = voiceId;
            document.getElementById('selected-voice').value = voiceId;
        }
        
        // Range input updates
        ['stability', 'similarity', 'style'].forEach(id => {
            document.getElementById(id).oninput = function() {
                document.getElementById(id + '-value').textContent = this.value;
            }
        });
        
        // File handling for STT
        function handleFileSelect(input) {
            const file = input.files[0];
            if (file) {
                const fileInfo = document.getElementById('file-info');
                fileInfo.innerHTML = `
                    <strong>Selected:</strong> ${file.name}<br>
                    <strong>Size:</strong> ${(file.size / 1024 / 1024).toFixed(2)} MB<br>
                    <strong>Type:</strong> ${file.type}
                `;
                fileInfo.style.display = 'block';
                document.getElementById('stt-btn').disabled = false;
            }
        }
        
        // File handling for voice cloning
        function handleCloneFileSelect(input) {
            const file = input.files[0];
            if (file) {
                const fileInfo = document.getElementById('clone-file-info');
                fileInfo.innerHTML = `
                    <strong>Selected:</strong> ${file.name}<br>
                    <strong>Size:</strong> ${(file.size / 1024 / 1024).toFixed(2)} MB<br>
                    <strong>Type:</strong> ${file.type}
                `;
                fileInfo.style.display = 'block';
                document.getElementById('clone-btn').disabled = false;
            }
        }
        
        // TTS Form submission
        async function generateSpeech(event) {
            event.preventDefault();
            
            if (!selectedVoiceId) {
                alert('Please select a voice first.');
                return;
            }
            
            const form = event.target;
            const formData = new FormData(form);
            
            document.getElementById('tts-loading').style.display = 'block';
            document.getElementById('tts-result').style.display = 'none';
            
            try {
                const response = await fetch('/generate_speech', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    const audioPlayer = document.getElementById('audio-player');
                    const downloadLink = document.getElementById('download-link');
                    
                    audioPlayer.src = '/download/' + result.filename;
                    downloadLink.href = '/download/' + result.filename;
                    downloadLink.download = result.filename;
                    
                    document.getElementById('tts-result').style.display = 'block';
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error generating speech: ' + error.message);
            }
            
            document.getElementById('tts-loading').style.display = 'none';
        }
        
        // STT Form submission
        async function convertSpeechToText(event) {
            event.preventDefault();
            
            const form = event.target;
            const formData = new FormData(form);
            
            document.getElementById('stt-loading').style.display = 'block';
            document.getElementById('stt-result').style.display = 'none';
            
            try {
                const response = await fetch('/speech_to_text', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('transcribed-text').textContent = result.text;
                    document.getElementById('stt-result').style.display = 'block';
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error converting speech: ' + error.message);
            }
            
            document.getElementById('stt-loading').style.display = 'none';
        }
        
        // Voice cloning form submission
        async function cloneVoice(event) {
            event.preventDefault();
            
            const form = event.target;
            const formData = new FormData(form);
            
            document.getElementById('clone-loading').style.display = 'block';
            document.getElementById('clone-result').style.display = 'none';
            
            try {
                const response = await fetch('/clone_voice', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('clone-message').innerHTML = `
                        <strong>✅ Voice cloned successfully!</strong><br>
                        <strong>Voice ID:</strong> ${result.voice_id}<br>
                        <strong>Name:</strong> ${result.voice_name}<br>
                        <em>You can now use this voice in the Text-to-Speech tab.</em>
                    `;
                    
                    // Refresh the page to load the new voice
                    setTimeout(() => {
                        location.reload();
                    }, 3000);
                } else {
                    document.getElementById('clone-message').innerHTML = `
                        <strong>Voice cloning failed:</strong><br>
                        ${result.error}
                    `;
                }
                
                document.getElementById('clone-result').style.display = 'block';
            } catch (error) {
                document.getElementById('clone-message').innerHTML = `
                    <strong>Error:</strong><br>
                    ${error.message}
                `;
                document.getElementById('clone-result').style.display = 'block';
            }
            
            document.getElementById('clone-loading').style.display = 'none';
        }
        
        // Copy to clipboard
        function copyToClipboard() {
            const text = document.getElementById('transcribed-text').textContent;
            navigator.clipboard.writeText(text).then(() => {
                alert('Text copied to clipboard!');
            });
        }
        
        // Test voice
        function testVoice(voiceId) {
            const testText = "Hello, this is a voice test using ElevenLabs AI. How does this sound?";
            
            fetch('/test_voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: testText,
                    voice_id: voiceId
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    const audio = new Audio('/download/' + result.filename);
                    audio.play();
                } else {
                    alert('Error testing voice: ' + result.error);
                }
            });
        }
        
        // Drag and drop functionality
        const uploadAreas = document.querySelectorAll('.upload-area');
        
        uploadAreas.forEach(uploadArea => {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, preventDefaults, false);
            });
            
            ['dragenter', 'dragover'].forEach(eventName => {
                uploadArea.addEventListener(eventName, () => uploadArea.classList.add('dragover'), false);
            });
            
            ['dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, () => uploadArea.classList.remove('dragover'), false);
            });
            
            uploadArea.addEventListener('drop', handleDrop, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            
            // Determine which upload area this is
            if (e.target.closest('#stt-tab')) {
                document.getElementById('audio-file').files = files;
                handleFileSelect(document.getElementById('audio-file'));
            } else if (e.target.closest('#clone-tab')) {
                document.getElementById('clone-audio-file').files = files;
                handleCloneFileSelect(document.getElementById('clone-audio-file'));
            }
        }
        
        // Auto-select first voice if available
        document.addEventListener('DOMContentLoaded', function() {
            const firstVoice = document.querySelector('.voice-card');
            if (firstVoice) {
                firstVoice.click();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    elevenlabs_voices = tts_engine.get_elevenlabs_voices()
    api_connected = len(elevenlabs_voices) > 0
    
    return render_template_string(HTML_TEMPLATE, 
                                elevenlabs_voices=elevenlabs_voices,
                                api_connected=api_connected,
                                voice_count=len(elevenlabs_voices))

@app.route('/generate_speech', methods=['POST'])
def generate_speech():
    try:
        text = request.form.get('text', '').strip()
        voice_id = request.form.get('voice_id', '')
        stability = float(request.form.get('stability', 0.5))
        similarity = float(request.form.get('similarity', 0.5))
        style = float(request.form.get('style', 0.0))
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'})
        
        if not voice_id:
            return jsonify({'success': False, 'error': 'No voice selected'})
        
        filepath = tts_engine.text_to_speech_elevenlabs(text, voice_id, stability, similarity, style)
        
        if filepath and os.path.exists(filepath):
            filename = os.path.basename(filepath)
            return jsonify({'success': True, 'filename': filename})
        else:
            return jsonify({'success': False, 'error': 'Failed to generate speech'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/speech_to_text', methods=['POST'])
def speech_to_text():
    try:
        if 'audio_file' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'})
        
        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Convert speech to text
            text = tts_engine.speech_to_text(filepath)
            
            # Clean up uploaded file
            os.remove(filepath)
            
            if text:
                return jsonify({'success': True, 'text': text})
            else:
                return jsonify({'success': False, 'error': 'Could not recognize speech'})
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/test_voice', methods=['POST'])
def test_voice():
    try:
        data = request.get_json()
        text = data.get('text', 'Test voice with ElevenLabs AI')
        voice_id = data.get('voice_id', '')
        
        if not voice_id:
            return jsonify({'success': False, 'error': 'No voice ID provided'})
        
        filepath = tts_engine.text_to_speech_elevenlabs(text, voice_id)
        
        if filepath and os.path.exists(filepath):
            filename = os.path.basename(filepath)
            return jsonify({'success': True, 'filename': filename})
        else:
            return jsonify({'success': False, 'error': 'Failed to generate test audio'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/clone_voice', methods=['POST'])
def clone_voice():
    try:
        if 'clone_audio_file' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'})
        
        file = request.files['clone_audio_file']
        voice_name = request.form.get('voice_name', '').strip()
        voice_description = request.form.get('voice_description', '').strip()
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not voice_name:
            return jsonify({'success': False, 'error': 'Voice name is required'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Convert to MP3 if needed (ElevenLabs prefers MP3)
            if not filepath.endswith('.mp3'):
                audio = AudioSegment.from_file(filepath)
                mp3_path = filepath.rsplit('.', 1)[0] + '.mp3'
                audio.export(mp3_path, format="mp3")
                os.remove(filepath)
                filepath = mp3_path
            
            # Clone voice using ElevenLabs
            voice_id = tts_engine.clone_voice_from_audio(filepath, voice_name, voice_description)
            
            # Clean up uploaded file
            os.remove(filepath)
            
            if voice_id:
                return jsonify({
                    'success': True, 
                    'voice_id': voice_id,
                    'voice_name': voice_name,
                    'message': 'Voice cloned successfully!'
                })
            else:
                return jsonify({'success': False, 'error': 'Voice cloning failed'})
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

# Cleanup old files (run periodically)
def cleanup_old_files():
    """Remove files older than 1 hour"""
    import time
    current_time = time.time()
    
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getctime(filepath)
                if file_age > 3600:  # 1 hour
                    try:
                        os.remove(filepath)
                        print(f"Cleaned up old file: {filename}")
                    except:
                        pass

# Start cleanup thread
cleanup_thread = threading.Thread(target=lambda: [time.sleep(3600), cleanup_old_files()], daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🎤 VOICE STUDIO - ELEVENLABS EDITION")
    print("="*50)
    print("✅ Features Available:")
    print("   • Text-to-Speech (ElevenLabs AI)")
    print("   • Speech-to-Text recognition")
    print("   • Voice cloning with ElevenLabs")
    print("   • Professional voice library")
    print("   • Advanced voice settings")
    print("   • Web interface with drag & drop")
    print("   • Audio download functionality")
    
    if ELEVENLABS_API_KEY:
        voices = tts_engine.get_elevenlabs_voices()
        print(f"\n🎯 ElevenLabs API: Connected ({len(voices)} voices)")
    else:
        print("\n⚠️  ElevenLabs API: Not configured")
        print("   Set ELEVENLABS_API_KEY environment variable")
    
    print(f"\n🌐 Platform: {platform.system()}")
    print("\n📋 Installation Requirements:")
    print("   pip install flask speechrecognition pydub requests")
    print("\n🚀 Starting server...")
    print("   Open http://localhost:5000 in your browser")
    print("="*50)
    
    # Get port from environment (for cloud deployment)
    port = int(os.environ.get('PORT', 5000))
    # Run the Flask application
    app.run(debug=False, host='0.0.0.0', port=port)