# VaakMitra: AI OTT Platform for Real-Time Dubbing

VaakMitra is an intelligent video processing platform that automates the translation and dubbing of English video content into Malayalam. By leveraging Google Speech-to-Text, Neural Translation, and Malayalam TTS, it provides a seamless "OTT-like" experience for localized content.

## ✨ Features
- **Automated Transcription:** Extracts and recognizes English speech using Google STT.
- **Contextual Translation:** Converts text to Malayalam using deep-learning translators.
- **AI Dubbing:** Generates natural Malayalam speech and overlays it onto the original video.
- **FFmpeg Integration:** High-performance video/audio merging and synchronization.

## 🚀 Tech Stack
- **Backend:** Flask (Python)
- **Speech & Translation:** SpeechRecognition, Google Translator, gTTS
- **Media Processing:** FFmpeg
- **Frontend:** HTML5, CSS3 (Modern Classy UI), JavaScript

## 🛠️ Setup
1. Clone the repository.
2. Install FFmpeg on your system.
3. Create a virtual environment: `python -m venv .venv`
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `python app.py`
