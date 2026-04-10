"""
VaakMitra Backend
"""
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os, json, uuid, shutil, traceback, subprocess, math

app = Flask(__name__, static_folder=".")
CORS(app)

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR   = os.path.join(BASE_DIR, "videos")
OUTPUTS_DIR  = os.path.join(BASE_DIR, "outputs")
WORK_DIR     = os.path.join(BASE_DIR, "workdir")
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")

for d in [VIDEOS_DIR, OUTPUTS_DIR, WORK_DIR]:
    os.makedirs(d, exist_ok=True)


def load_library():
    if os.path.exists(LIBRARY_FILE):
        with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"videos": []}


def save_library(lib):
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(lib, f, indent=2, ensure_ascii=False)


def find_video(vid_id):
    return next((v for v in load_library()["videos"] if v["id"] == vid_id), None)


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def transcribe_audio(wav_path):
    import speech_recognition as sr
    import wave

    rec = sr.Recognizer()
    rec.pause_threshold = 1.0

    with wave.open(wav_path, "r") as wf:
        duration_s = wf.getnframes() / float(wf.getframerate())

    CHUNK_SEC = 30

    if duration_s <= CHUNK_SEC:
        with sr.AudioFile(wav_path) as source:
            rec.adjust_for_ambient_noise(source, duration=0.2)
            audio_data = rec.record(source) # Use record instead of listen for files
        return rec.recognize_google(audio_data)

    print(f"[VaakMitra] Audio {duration_s:.1f}s — chunking into {CHUNK_SEC}s pieces...")
    transcripts = []
    num_chunks = math.ceil(duration_s / CHUNK_SEC)

    with sr.AudioFile(wav_path) as source:
        rec.adjust_for_ambient_noise(source, duration=0.2)
        for i in range(num_chunks):
            start_t = i * CHUNK_SEC
            length = min(CHUNK_SEC, duration_s - start_t)
            if length <= 0:
                break
            print(f"[VaakMitra]   chunk {i+1}/{num_chunks} at {start_t:.1f}s")
            try:
                chunk_audio = rec.record(source, duration=length)
                text = rec.recognize_google(chunk_audio)
                if text:
                    transcripts.append(text)
                    print(f"[VaakMitra]     Success: {text[:60]}...")
            except sr.UnknownValueError:
                print(f"[VaakMitra]     (Chunk {i+1}: No speech detected)")
            except sr.RequestError as e:
                print(f"[VaakMitra]     (Chunk {i+1}: API Error: {e})")

    if not transcripts:
        raise RuntimeError("Could not transcribe any audio. Make sure the video has clear English speech.")

    return " ".join(transcripts)


def translate_text_chunked(text, target_lang="ml"):
    """
    Splits long text into chunks for the translator to avoid length limits.
    """
    if not text:
        return ""
        
    from deep_translator import GoogleTranslator
    MAX_CHARS = 4500
    translator = GoogleTranslator(source="en", target=target_lang)
    
    if len(text) <= MAX_CHARS:
        return translator.translate(text)
        
    print(f"[VaakMitra] Text too long ({len(text)} chars) — splitting for translation...")
    
    # Split by sentence or space
    segments = text.split(". ")
    chunks = []
    current_chunk = ""
    
    for seg in segments:
        if not seg: continue
        # Add period back if it wasn't the last empty segment
        seg_with_period = seg + ". "
        if len(current_chunk) + len(seg_with_period) <= MAX_CHARS:
            current_chunk += seg_with_period
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = seg_with_period
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    translated_parts = []
    for idx, chunk in enumerate(chunks):
        print(f"[VaakMitra]   Translating block {idx+1}/{len(chunks)}...")
        translated_parts.append(translator.translate(chunk))
        
    return " ".join(translated_parts)


def sync_from_add_videos():
    add_videos_path = os.path.join(BASE_DIR, "add_videos.py")
    if not os.path.exists(add_videos_path):
        print("[VaakMitra] add_videos.py not found — skipping.")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("add_videos", add_videos_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    videos_to_add = getattr(mod, "VIDEOS", [])
    if not videos_to_add:
        print("[VaakMitra] No VIDEOS entries in add_videos.py.")
        return

    lib          = load_library()
    existing_ids = {v["id"] for v in lib["videos"]}
    added = skipped = errors = 0

    for entry in videos_to_add:
        vid_id = entry.get("id") or str(uuid.uuid4())[:8]
        if vid_id in existing_ids:
            skipped += 1
            continue

        src_path = os.path.abspath(entry.get("path", ""))
        if not os.path.exists(src_path):
            print(f"[VaakMitra] NOT FOUND: {src_path}")
            errors += 1
            continue

        ext       = os.path.splitext(src_path)[1] or ".mp4"
        dest_name = f"{vid_id}{ext}"
        dest_path = os.path.join(VIDEOS_DIR, dest_name)

        try:
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            print(f"[VaakMitra] Copy error: {e}")
            errors += 1
            continue

        lib["videos"].append({
            "id":             vid_id,
            "title":          entry.get("title", os.path.splitext(os.path.basename(src_path))[0]),
            "genre":          entry.get("genre", ""),
            "year":           entry.get("year", ""),
            "thumb":          entry.get("thumb", "🎬"),
            "desc":           entry.get("desc", ""),
            "videoPath":      dest_name,
            "translatedPath": None,
            "hasTranslation": False,
            "englishText":    "",
            "malayalamText":  "",
            "duration":       entry.get("duration", ""),
        })
        existing_ids.add(vid_id)
        added += 1
        print(f"[VaakMitra] Added: {entry.get('title', vid_id)}")

    save_library(lib)
    print(f"[VaakMitra] Sync done — {added} added, {skipped} skipped, {errors} errors.")


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/library")
def get_library():
    return jsonify(load_library())


@app.route("/translate/<vid_id>", methods=["POST"])
def translate_video(vid_id):
    entry = find_video(vid_id)
    if not entry:
        return jsonify({"error": f"Video '{vid_id}' not found. Check add_videos.py and restart."}), 404

    video_path = os.path.join(VIDEOS_DIR, entry["videoPath"])
    if not os.path.exists(video_path):
        return jsonify({"error": f"Video file missing on disk: {video_path}"}), 404

    if not check_ffmpeg():
        return jsonify({"error": "ffmpeg not found. Install it and add to PATH.\n  macOS: brew install ffmpeg\n  Ubuntu: sudo apt install ffmpeg\n  Windows: https://ffmpeg.org/download.html"}), 500

    audio_wav = os.path.join(WORK_DIR, f"{vid_id}.wav")
    tts_mp3   = os.path.join(WORK_DIR, f"{vid_id}_ml.mp3")
    out_name  = f"{vid_id}_translated.mp4"
    out_path  = os.path.join(OUTPUTS_DIR, out_name)

    # STEP 1 — extract audio via ffmpeg directly (no moviepy needed here)
    print(f"[VaakMitra] Step 1 — extracting audio...")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", audio_wav],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            return jsonify({"error": f"Step 1 failed (audio extract):\n{r.stderr[-500:]}"}), 500
        if not os.path.exists(audio_wav):
            return jsonify({"error": "Step 1 failed: wav file not created. Video may have no audio."}), 422
    except Exception as e:
        return jsonify({"error": f"Step 1 failed: {e}"}), 500

    # STEP 2 — transcribe
    print(f"[VaakMitra] Step 2 — transcribing...")
    try:
        english_text = transcribe_audio(audio_wav)
        print(f"[VaakMitra]   EN: {english_text[:100]}")
    except Exception as e:
        return jsonify({"error": f"Step 2 failed (transcription): {e}"}), 422

    # STEP 3 — translate EN -> ML
    print(f"[VaakMitra] Step 3 — translating...")
    try:
        malayalam_text = translate_text_chunked(english_text, target_lang="ml")
        print(f"[VaakMitra]   ML: {malayalam_text[:100]}")
    except Exception as e:
        return jsonify({"error": f"Step 3 failed (translation): {e}"}), 500

    # STEP 4 — Malayalam TTS
    print(f"[VaakMitra] Step 4 — generating Malayalam voice...")
    try:
        from gtts import gTTS
        gTTS(text=malayalam_text, lang="ml", slow=False).save(tts_mp3)
    except Exception as e:
        return jsonify({"error": f"Step 4 failed (TTS): {e}"}), 500

    # STEP 5 — replace audio using ffmpeg directly (no moviepy at all)
    print(f"[VaakMitra] Step 5 — composing final video...")
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", tts_mp3,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                out_path
            ],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            return jsonify({"error": f"Step 5 failed (ffmpeg merge):\n{r.stderr[-500:]}"}), 500
    except Exception as e:
        return jsonify({"error": f"Step 5 failed: {e}"}), 500

    # Update library
    lib = load_library()
    for v in lib["videos"]:
        if v["id"] == vid_id:
            v["translatedPath"]  = out_name
            v["hasTranslation"]  = True
            v["englishText"]     = english_text
            v["malayalamText"]   = malayalam_text
    save_library(lib)
    print(f"[VaakMitra] Done: {out_name}")

    return jsonify({
        "success":         True,
        "english_text":    english_text,
        "malayalam_text":  malayalam_text,
        "translated_path": out_name,
    })


@app.route("/video/<path:filename>")
def serve_video(filename):
    for folder in [OUTPUTS_DIR, VIDEOS_DIR]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return send_file(path, mimetype="video/mp4")
    return "Not found", 404


if __name__ == "__main__":
    print("=" * 54)
    print("  VaakMitra — English to Malayalam OTT Platform")
    print("=" * 54)
    sync_from_add_videos()
    print("[VaakMitra] Server -> http://localhost:5000")
    print("=" * 54)
    app.run(debug=True, port=5000)