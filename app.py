import streamlit as st
import requests
import os
import base64
from dotenv import load_dotenv
import logging
from deep_translator import GoogleTranslator
from gtts import gTTS
from io import BytesIO
from PIL import Image
import hashlib

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="TimeLens – Monument Recognition",
    page_icon="🏛️",
    layout="wide"
)

# Load environment variables
load_dotenv()
os.environ["NO_PROXY"] = "api.mistral.ai"

# Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY missing in .env")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# IMAGE UTILS
# ---------------------------------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 800

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes))
        img_format = img.format if img.format in ['JPEG', 'PNG'] else 'JPEG'
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        output = BytesIO()
        if img_format == 'JPEG':
            img.save(output, format='JPEG', quality=85, optimize=True)
        else:
            img.save(output, format='PNG', optimize=True)
        return output.getvalue()
    except Exception as e:
        logger.error("Image compression error: %s", e)
        return image_bytes

# ---------------------------------------------------------
# API CALLS (UNCHANGED)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def process_monument_name(_hash, monument_name):
    try:
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "pixtral-large-latest",
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": f"Provide in depth historical information about {monument_name}. "
                            "Plain text only. No markdown."
                }]
            }]
        }
        resp = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "No details found.")
    except Exception as e:
        return f"Error: {e}"

@st.cache_data(show_spinner=False)
def process_image(_hash, image_bytes):
    try:
        cbytes = compress_image(image_bytes)
        if len(cbytes) > MAX_FILE_SIZE:
            return "Error: Image too large after compression."

        b64 = base64.b64encode(cbytes).decode()
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "pixtral-large-latest",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "Identify this monument and explain its history. Plain text only."}
                ]
            }]
        }
        resp = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "No details found.")
    except Exception as e:
        return f"Error: {e}"

@st.cache_data(show_spinner=False)
def translate_to_kannada(text):
    try:
        return GoogleTranslator(source='en', target='kn').translate(text)
    except Exception as e:
        return f"Translation failed: {e}"

@st.cache_data(show_spinner=False)
def generate_speech(_hash, text, lang):
    try:
        mp3 = BytesIO()
        gTTS(text=text, lang=lang).write_to_fp(mp3)
        mp3.seek(0)
        return mp3
    except Exception:
        return None

# ---------------------------------------------------------
# LANDING PAGE STYLES (IDENTICAL)
# ---------------------------------------------------------
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Marcellus&display=swap" rel="stylesheet">
<style>

body, .stApp {
    background-color: #f3ebd8 !important;
    font-family: 'Marcellus', serif;
    color: #3e3423;
}

/* HERO */
.hero {
    text-align: center;
    padding: 60px 20px 40px;
}

.hero-title {
    font-family: 'Cinzel', serif;
    font-size: 3.8rem;
    background: linear-gradient(90deg, #b18400, #f3d27c);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero-subtitle {
    font-size: 1.4rem;
    color: #5d4a2d;
    margin-top: -10px;
}

.hero-quote {
    font-style: italic;
    font-size: 1.2rem;
    margin-top: 12px;
    color: #705c3b;
}

/* ABOUT */
.about {
    text-align: center;
    font-size: 1.2rem;
    width: 70%;
    margin: 20px auto 40px;
    line-height: 1.6;
}

/* CARDS */
.card-container {
    display: flex;
    justify-content: center;
    gap: 35px;
    flex-wrap: wrap;
}

.card {
    background: #ffffff;
    width: 330px;
    text-align: center;
    padding: 25px;
    border-radius: 15px;
    border: 2px solid #d0b98a;
    box-shadow: 0 5px 15px rgba(0,0,0,0.15);
    transition: 0.3s ease;
}

.card:hover {
    transform: translateY(-8px);
    box-shadow: 0 12px 28px rgba(0,0,0,0.25);
}

.card-icon {
    font-size: 3rem;
}

.card-title {
    font-family: 'Cinzel', serif;
    font-size: 1.6rem;
    color: #a27800;
    margin-top: 8px;
}

.card-desc {
    font-size: 1rem;
    margin: 10px 0 20px;
    color: #4d3e2a;
}

/* BUTTON */
.card-button {
    display: inline-block;
    padding: 10px 18px;
    border-radius: 10px;
    background: linear-gradient(90deg, #a27800, #eecf82);
    color: white;
    font-weight: 600;
    text-decoration: none;
}

.card-button:hover {
    background: linear-gradient(90deg, #eecf82, #a27800);
}

/* INNER TOOL */
.inner-tool-box {
    margin-top: 20px;
    padding: 15px;
    border-radius: 12px;
    background: #fffaf1;
    border: 1px solid #e2c78e;
    text-align: left;
}

/* Inputs inside card */
.stTextInput>div>div>input {
    border-radius: 10px;
    border: 2px solid #d0b98a;
    padding: 10px 14px;
}

/* Buttons inside tool */
.stButton>button {
    background: linear-gradient(90deg, #a27800, #eecf82);
    color: white;
    font-weight: 600;
    border-radius: 10px;
    border: none;
    padding: 10px 18px;
    margin-top: 10px;
}

/* Footer */
.footer {
    text-align: center;
    padding: 18px;
    font-size: 0.9rem;
    background-color: #e8dbc0;
    color: #4b3a23;
    margin-top: 40px;
}

</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# HERO
# ---------------------------------------------------------
st.markdown("""
<div class="hero">
    <h1 class="hero-title">TimeLens</h1>
    <h2 class="hero-subtitle">AI-Powered Monument Recognition & Manuscript Revival</h2>
    <p class="hero-quote">“Where ancient worlds whisper — and AI listens.”</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# ABOUT SECTION
# ---------------------------------------------------------
st.markdown("""
<div class="about">
    TimeLens blends cutting-edge AI with the legacy of ancient civilizations. 
    Recognize monuments instantly, restore Sanskrit manuscripts, extract inscriptions, 
    and translate ancient texts — all in one unified platform.
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# CARDS WRAPPER
# ---------------------------------------------------------
st.markdown('<div class="card-container">', unsafe_allow_html=True)

# ========================================================
# CARD 1 — MONUMENT RECOGNITION (TOOL INSIDE)
# ========================================================
st.markdown("""
<div class="card">
    <div class="card-icon">🏛️</div>
    <div class="card-title">Monument Recognition</div>
    <p class="card-desc">
        Upload a monument image or enter a name — TimeLens identifies it and reveals its history instantly.
    </p>
""", unsafe_allow_html=True)

# Inner tool box
st.markdown('<div class="inner-tool-box">', unsafe_allow_html=True)

# ---------------------------------------------------------
# STREAMLIT TOOL WORKFLOW (UNCHANGED)
# ---------------------------------------------------------

# Session state
if "monument_info" not in st.session_state:
    st.session_state.monument_info = None
    st.session_state.translated_text = None
    st.session_state.audio_english = None
    st.session_state.audio_kannada = None
    st.session_state.last_mode = None

mode = st.radio("Choose input mode:", ["Enter Monument Name", "Upload Image"])

if st.session_state.last_mode != mode:
    st.session_state.monument_info = None
    st.session_state.translated_text = None
    st.session_state.audio_english = None
    st.session_state.audio_kannada = None
    st.session_state.last_mode = mode

if mode == "Enter Monument Name":
    name = st.text_input("Enter monument name")
    if st.button("Get Info"):
        if name.strip():
            h = hashlib.sha256(name.encode()).hexdigest()
            st.session_state.monument_info = process_monument_name(h, name)
        else:
            st.warning("Please enter a valid name.")

else:
    img = st.file_uploader("Upload image", type=["png", "jpg", "jpeg"])
    if img:
        st.image(img)
        if st.button("Analyze Image"):
            b = img.read()
            h = hashlib.sha256(b).hexdigest()
            st.session_state.monument_info = process_image(h, b)

# Display results
if st.session_state.monument_info:
    st.write("### Monument Information (English)")
    st.write(st.session_state.monument_info)

    # Narration buttons
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Generate English Narration"):
            h = hashlib.sha256(st.session_state.monument_info.encode()).hexdigest()
            st.session_state.audio_english = generate_speech(h, st.session_state.monument_info, "en")

    with col2:
        if st.button("Translate to Kannada"):
            st.session_state.translated_text = translate_to_kannada(st.session_state.monument_info)

    # English audio
    if st.session_state.audio_english:
        st.audio(st.session_state.audio_english)

    # Kannada text + audio
    if st.session_state.translated_text:
        st.write("### Kannada Translation")
        st.write(st.session_state.translated_text)

        if st.button("Generate Kannada Narration"):
            h = hashlib.sha256(st.session_state.translated_text.encode()).hexdigest()
            st.session_state.audio_kannada = generate_speech(h, st.session_state.translated_text, "kn")

        if st.session_state.audio_kannada:
            st.audio(st.session_state.audio_kannada)

# Close tool box + card
st.markdown("</div></div>", unsafe_allow_html=True)

# ========================================================
# CARD 2 — LINK TO SANSKRIT MANUSCRIPTS
# ========================================================
st.markdown("""
<div class="card">
    <div class="card-icon">📜</div>
    <div class="card-title">Sanskrit Manuscripts</div>
    <p class="card-desc">
        Clean old manuscripts, extract text, enhance with AI, and translate into 5 languages.
    </p>

    <a class="card-button" href="https://huggingface.co/spaces/premjavali05/Sanskrit_Manuscripts" target="_blank">
        Open Workspace
    </a>
</div>
""", unsafe_allow_html=True)

# Close card container
st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown('<div class="footer">Built with ❤️ · TimeLens © 2025</div>', unsafe_allow_html=True)
