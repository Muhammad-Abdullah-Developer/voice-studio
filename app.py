#!/usr/bin/env python3
"""
Text-to-Speech and Voice Cloning Web Application
A comprehensive TTS tool with voice upload and multilingual support
"""

from flask import Flask, render_template_string, request, send_file, jsonify, flash, redirect, url_for
import os
import tempfile
import uuid
from werkzeug.utils import secure_filename
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import io
import base64
import threading
import time
from datetime import datetime
import platform

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

# Supported languages for gTTS
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
# Check if running on cloud platform
IS_CLOUD_DEPLOYMENT = os.environ.get('RENDER') or os.environ.get('HEROKU') or platform.system() == 'Linux'

# Conditional import for pyttsx3
try:
    if not IS_CLOUD_DEPLOYMENT:
        import pyttsx3
        PYTTSX_AVAILABLE = True
    else:
        PYTTSX_AVAILABLE = False
        print("Running on cloud platform - pyttsx3 disabled, using Google TTS only")
except ImportError:
    PYTTSX_AVAILABLE = False
    print("pyttsx3 not available - using Google TTS only")

class TTSEngine:
    def __init__(self):
        if PYTTSX_AVAILABLE:
            try:
                self.pyttsx_engine = pyttsx3.init()
            except:
                self.pyttsx_engine = None
                print("Failed to initialize pyttsx3 engine")
        else:
            self.pyttsx_engine = None
        self.custom_voices = {}
        
    def get_system_voices(self):
        """Get available system voices"""
        if not PYTTSX_AVAILABLE or not self.pyttsx_engine:
            return [{'id': 0, 'name': 'Cloud TTS Only', 'lang': 'multiple'}]
        
        try:
            voices = self.pyttsx_engine.getProperty('voices')
            voice_list = []
            for i, voice in enumerate(voices):
                voice_list.append({
                    'id': i,
                    'name': voice.name,
                    'lang': getattr(voice, 'lang', 'unknown')
                })
            return voice_list
        except:
            return [{'id': 0, 'name': 'System TTS Unavailable', 'lang': 'error'}]
    
    def text_to_speech_pyttsx(self, text, voice_id=None, rate=200, volume=0.9):
        """Generate speech using pyttsx3 - fallback to gTTS on cloud"""
        if not PYTTSX_AVAILABLE or not self.pyttsx_engine:
            # Fallback to Google TTS
            print("pyttsx3 not available, falling back to Google TTS")
            return self.text_to_speech_gtts(text, 'en', False)
        
        try:
            if voice_id is not None:
                voices = self.pyttsx_engine.getProperty('voices')
                if voice_id < len(voices):
                    self.pyttsx_engine.setProperty('voice', voices[voice_id].id)
            
            self.pyttsx_engine.setProperty('rate', rate)
            self.pyttsx_engine.setProperty('volume', volume)
            
            # Create unique filename
            filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
            filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
            
            self.pyttsx_engine.save_to_file(text, filepath)
            self.pyttsx_engine.runAndWait()
            
            return filepath
        except Exception as e:
            print(f"Error in pyttsx TTS: {e}, falling back to Google TTS")
            return self.text_to_speech_gtts(text, 'en', False)
        
    def text_to_speech_gtts(self, text, lang='en', slow=False):
        """Generate speech using Google TTS"""
        try:
            tts = gTTS(text=text, lang=lang, slow=slow)
            filename = f"gtts_{uuid.uuid4().hex[:8]}.mp3"
            filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
            tts.save(filepath)
            return filepath
        except Exception as e:
            print(f"Error in gTTS: {e}")
            return None
    
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

# Initialize TTS engine
tts_engine = TTSEngine()

# HTML Templates
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Text-to-Speech & Voice Tools</title>
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
            background: #e3f2fd;
            border-color: #2196f3;
        }
        
        .file-info {
            margin-top: 15px;
            padding: 10px;
            background: #e8f5e8;
            border-radius: 5px;
            display: none;
        }
        
        .alert {
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
        }
        
        .alert-success {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        
        .alert-error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
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
        
        .voice-list {
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            padding: 10px;
        }
        
        .voice-item {
            padding: 8px;
            cursor: pointer;
            border-radius: 4px;
        }
        
        .voice-item:hover {
            background: #f8f9fa;
        }
        
        .voice-item.selected {
            background: #4facfe;
            color: white;
        }
        
        @media (max-width: 768px) {
            .row {
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
            <h1>Voice Studio</h1>
            <p>Professional Text-to-Speech & Voice Processing Tools</p>
        </div>
        
        <div class="content">
            <div class="tabs">
                <div class="tab active" onclick="switchTab('tts')">Text to Speech</div>
                <div class="tab" onclick="switchTab('stt')">Speech to Text</div>
                <div class="tab" onclick="switchTab('voices')">Voice Management</div>
            </div>
            
            <!-- Text to Speech Tab -->
            <div id="tts-tab" class="tab-content active">
                <form id="tts-form" onsubmit="generateSpeech(event)">
                    <div class="row">
                        <div>
                            <div class="form-group">
                                <label for="text-input">Enter Text to Convert:</label>
                                <textarea id="text-input" name="text" class="form-control" 
                                         placeholder="Type your text here..." required></textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="language">Language:</label>
                                <select id="language" name="language" class="form-control">
                                    {% for code, name in languages.items() %}
                                    <option value="{{ code }}" {% if code == 'en' %}selected{% endif %}>{{ name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label for="engine">TTS Engine:</label>
                                <select id="engine" name="engine" class="form-control">
                                    <option value="gtts">Google TTS (Online)</option>
                                    <option value="pyttsx">System TTS (Offline)</option>
                                </select>
                            </div>
                        </div>
                        
                        <div>
                            <div class="form-group">
                                <label for="voice">Voice (System TTS only):</label>
                                <select id="voice" name="voice" class="form-control">
                                    {% for voice in system_voices %}
                                    <option value="{{ voice.id }}">{{ voice.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label for="rate">Speech Rate:</label>
                                <input type="range" id="rate" name="rate" min="50" max="300" value="200" class="form-control">
                                <small>Current: <span id="rate-value">200</span> WPM</small>
                            </div>
                            
                            <div class="form-group">
                                <label for="volume">Volume:</label>
                                <input type="range" id="volume" name="volume" min="0" max="1" step="0.1" value="0.9" class="form-control">
                                <small>Current: <span id="volume-value">90</span>%</small>
                            </div>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn">Generate Speech</button>
                </form>
                
                <div id="tts-loading" class="loading">
                    <div class="spinner"></div>
                    <p>Generating speech...</p>
                </div>
                
                <div id="tts-result" class="audio-player" style="display: none;">
                    <h3>Generated Audio:</h3>
                    <audio id="audio-player" controls style="width: 100%; margin: 10px 0;">
                        Your browser does not support the audio element.
                    </audio>
                    <br>
                    <a id="download-link" class="btn" style="display: inline-block; margin-top: 10px; text-decoration: none">Download Audio</a>
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
                    <button onclick="copyToClipboard()" class="btn" style="margin-top: 10px;">📋 Copy Text</button>
                </div>
            </div>
            
            <!-- Voice Management Tab -->
            <div id="voices-tab" class="tab-content">
                <h3>Available System Voices</h3>
                <div class="voice-list">
                    {% for voice in system_voices %}
                    <div class="voice-item" onclick="testVoice({{ voice.id }})">
                        <strong>{{ voice.name }}</strong><br>
                        <small>Language: {{ voice.lang }}</small>
                    </div>
                    {% endfor %}
                </div>
                
                <div style="margin-top: 30px;">
                    <h3>Voice Upload (Coming Soon)</h3>
                    <p>Custom voice training and cloning features will be available in the next update.</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Tab switching
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName + '-tab').classList.add('active');
        }
        
        // Range input updates
        document.getElementById('rate').oninput = function() {
            document.getElementById('rate-value').textContent = this.value;
        }
        
        document.getElementById('volume').oninput = function() {
            document.getElementById('volume-value').textContent = Math.round(this.value * 100);
        }
        
        // File handling
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
        
        // Drag and drop
        const uploadArea = document.querySelector('.upload-area');
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, highlight, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, unhighlight, false);
        });
        
        function highlight(e) {
            uploadArea.classList.add('dragover');
        }
        
        function unhighlight(e) {
            uploadArea.classList.remove('dragover');
        }
        
        uploadArea.addEventListener('drop', handleDrop, false);
        
        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            document.getElementById('audio-file').files = files;
            handleFileSelect(document.getElementById('audio-file'));
        }
        
        // TTS Form submission
        async function generateSpeech(event) {
            event.preventDefault();
            
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
        
        // Copy to clipboard
        function copyToClipboard() {
            const text = document.getElementById('transcribed-text').textContent;
            navigator.clipboard.writeText(text).then(() => {
                alert('Text copied to clipboard!');
            });
        }
        
        // Test voice
        function testVoice(voiceId) {
            const testText = "Hello, this is a voice test. How does this sound?";
            
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
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    system_voices = tts_engine.get_system_voices()
    return render_template_string(HTML_TEMPLATE, 
                                languages=SUPPORTED_LANGUAGES,
                                system_voices=system_voices)

@app.route('/generate_speech', methods=['POST'])
def generate_speech():
    try:
        text = request.form.get('text', '').strip()
        language = request.form.get('language', 'en')
        engine = request.form.get('engine', 'gtts')
        voice_id = request.form.get('voice')
        rate = int(request.form.get('rate', 200))
        volume = float(request.form.get('volume', 0.9))
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'})
        
        if engine == 'gtts':
            filepath = tts_engine.text_to_speech_gtts(text, language)
        else:
            voice_id = int(voice_id) if voice_id else None
            filepath = tts_engine.text_to_speech_pyttsx(text, voice_id, rate, volume)
        
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
        text = data.get('text', 'Test voice')
        voice_id = data.get('voice_id', 0)
        
        filepath = tts_engine.text_to_speech_pyttsx(text, voice_id)
        
        if filepath and os.path.exists(filepath):
            filename = os.path.basename(filepath)
            return jsonify({'success': True, 'filename': filename})
        else:
            return jsonify({'success': False, 'error': 'Failed to generate test audio'})
            
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
    print("🎤 VOICE STUDIO - TEXT-TO-SPEECH APPLICATION")
    print("="*50)
    print("✅ Features Available:")
    print("   • Text-to-Speech (Google TTS + System voices)")
    print("   • Speech-to-Text recognition")
    print("   • Multiple European languages")
    print("   • Voice testing and management")
    print("   • Web interface with drag & drop")
    print("   • Audio download functionality")
    print("\n📋 Installation Requirements:")
    print("   pip install flask gtts pyttsx3 speechrecognition pydub")
    print("   pip install pyaudio")  # For microphone input
    print("\n🚀 Starting server...")
    print("   Open http://localhost:5000 in your browser")
    print("="*50)
    
    # Run the Flask application
    app.run(debug=True, host='0.0.0.0', port=5000)