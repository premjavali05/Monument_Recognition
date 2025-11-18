# app.py
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

# Page configuration
st.set_page_config(
    page_title="TimeLens – Monument Recognition",
    page_icon="🏛️",
    layout="wide"
)

# Load environment variables
load_dotenv()

# Set NO_PROXY to bypass proxies for Mistral API
os.environ["NO_PROXY"] = "api.mistral.ai"

# Mistral API Key and Endpoint
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY not found in environment variables. Please set it in .env file.")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for image processing
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024 # 5MB
MAX_IMAGE_DIMENSION = 800 # Max width/height for resizing

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_bytes):
    """Compress and resize image to reduce payload size."""
    try:
        img = Image.open(BytesIO(image_bytes))
        img_format = img.format if img.format in ['JPEG', 'PNG'] else 'JPEG'
        # Resize while maintaining aspect ratio
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        # Save to BytesIO with compression
        output = BytesIO()
        if img_format == 'JPEG':
            img.save(output, format='JPEG', quality=85, optimize=True)
        else:
            img.save(output, format='PNG', optimize=True)
        return output.getvalue()
    except Exception as e:
        logger.error("Image compression error: %s", e)
        return image_bytes # Fallback to original

@st.cache_data(show_spinner=False)
def process_monument_name(_monument_hash, monument_name):
    try:
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "pixtral-large-latest",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Provide in depth historical information about {monument_name}. Provide the response in plain text without any markdown formatting (e.g., no asterisks, hashes, or other symbols)."
                        }
                    ]
                }
            ]
        }
        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()
        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get("content", "Sorry, no details found for this monument.")
        logger.info("API Response for name: %s", result)
        return info
    except Exception as e:
        logger.error("Error during name processing: %s", e)
        return f"Error: {str(e)}"

@st.cache_data(show_spinner=False)
def process_image(_image_hash, image_bytes):
    try:
        # Compress image
        compressed_bytes = compress_image(image_bytes)
        if len(compressed_bytes) > MAX_FILE_SIZE:
            return f"Error: Compressed file too large. Max size is 5MB"
        # Convert to base64
        image_base64 = base64.b64encode(compressed_bytes).decode('utf-8')
        # Mistral API request
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "pixtral-large-latest",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "What monument is this? Please provide in depth historical information. Provide the response in plain text without any markdown formatting (e.g., no asterisks, hashes, or other symbols)."
                        }
                    ]
                }
            ]
        }
        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()
        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get("content", "Sorry, no details found in the response.")
        logger.info("API Response for image: %s", result)
        return info
    except Exception as e:
        logger.error("Error during image processing: %s", e)
        return f"Error: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_to_kannada(text):
    try:
        translator = GoogleTranslator(source='en', target='kn')
        translated = translator.translate(text)
        if not translated:
            return "Translation failed: No output from translator."
        return translated
    except Exception as e:
        logger.error("Translation error: %s", e)
        return f"Translation failed: {str(e)}"

@st.cache_data(show_spinner=False)
def generate_speech(_text_hash, text, lang='kn'):
    try:
        mp3_fp = BytesIO()
        tts = gTTS(text=text, lang=lang)
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        return mp3_fp
    except Exception as e:
        logger.error("gTTS error for lang %s: %s", lang, e)
        return None

# ---------------------------
# UI: Premium theme (replaces only the UI)
# ---------------------------

# Custom CSS (fresh premium design)
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Marcellus&display=swap" rel="stylesheet">
    <style>
    :root{
        --bg: #f3ebd8;
        --paper: #ffffff;
        --accent1: #a27800;
        --accent2: #eecf82;
        --muted: #5d4a2d;
        --text: #3e3423;
        --card-border: #d0b98a;
        --glass: rgba(255,255,255,0.85);
    }
    /* Reset container spacing for wide layout */
    .block-container{
        padding-top: 28px;
        padding-bottom: 40px;
        max-width: 1150px;
    }
    /* Global background */
    .stApp {
        background: radial-gradient(circle at 10% 10%, rgba(245,236,210,0.4), transparent 10%),
                    linear-gradient(180deg, var(--bg), #f4ead0 60%);
        color: var(--text);
        font-family: 'Marcellus', serif;
    }
    /* Hero */
    .hero-wrap {
        text-align: center;
        padding: 28px 12px 8px;
        margin-bottom: 18px;
    }
    .hero-title {
        font-family: 'Cinzel', serif;
        font-size: 3.6rem;
        margin: 0;
        background: linear-gradient(90deg, #b18400, var(--accent2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 0.6px;
    }
    .hero-sub {
        font-size: 1.15rem;
        color: var(--muted);
        margin-top: 6px;
    }
    .hero-quote {
        font-style: italic;
        color: #6f5539;
        margin-top: 8px;
    }

    /* Grid sections */
    .section {
        background: var(--paper);
        padding: 22px;
        border-radius: 14px;
        border: 2px solid var(--card-border);
        box-shadow: 0 8px 28px rgba(46,40,34,0.08);
        transition: transform .22s ease, box-shadow .22s ease;
    }
    .section:hover { transform: translateY(-6px); box-shadow: 0 20px 48px rgba(46,40,34,0.12); }
    .section h3 { font-family: 'Cinzel', serif; color: var(--accent1); margin-bottom: 8px; }
    .section p { color: var(--text); line-height: 1.65; }

    /* Controls column */
    .controls-col { padding: 8px; }
    .result-col { padding: 8px; }

    /* File uploader styling */
    .stFileUploader>div { border-radius: 12px; padding: 6px; }
    .stFileUploader label { font-family: 'Marcellus', serif; color: var(--text); }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(90deg, var(--accent1), var(--accent2));
        color: white;
        font-weight: 700;
        border-radius: 10px;
        padding: 10px 18px;
        border: none;
        box-shadow: 0 6px 18px rgba(0,0,0,0.12);
        font-family: 'Marcellus', serif;
    }
    .stButton>button:active { transform: translateY(1px); }

    /* Text inputs */
    .stTextInput>div>div>input {
        border-radius: 10px; padding: 10px 14px; border: 2px solid var(--card-border);
        font-family: 'Marcellus', serif; color: var(--text);
    }

    /* Cards inside */
    .mini-card { background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,255,255,0.95)); padding: 14px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.03); }
    .mini-title { font-family: 'Cinzel', serif; color: var(--accent1); margin-bottom: 6px; }

    /* Image display */
    .stImage>img { border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }

    /* Audio */
    .stAudio { border-radius: 10px; padding: 6px; background: var(--glass); border: 1px solid var(--card-border); }

    /* Result text formatting */
    .result-text { white-space: pre-wrap; line-height: 1.7; color: var(--text); font-family: 'Marcellus', serif; }

    /* Footer */
    .footer {
        text-align: center;
        padding: 18px;
        margin-top: 28px;
        border-radius: 12px;
        background: linear-gradient(180deg, rgba(232,219,192,0.6), rgba(232,219,192,0.9));
        border: 1px solid var(--card-border);
        color: var(--muted);
    }

    /* Responsive tweaks */
    @media (max-width: 880px) {
        .hero-title { font-size: 2.6rem; }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# HERO
st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)
st.markdown('<div style="max-width:980px;margin:0 auto;">', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">TimeLens</h1>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Monument Recognition & Historical Narration — AI that listens to stones.</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-quote">“Where ancient worlds whisper — and AI listens.”</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Initialize session state (unchanged logic)
if 'monument_info' not in st.session_state:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = None

# Top-level layout: left = inputs, right = results
left_col, right_col = st.columns([1, 1.4], gap="large")

# LEFT: Inputs
with left_col:
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<h3>Choose Input</h3>', unsafe_allow_html=True)
    st.markdown('<p>Provide a monument name or upload an image to discover detailed historical narratives.</p>', unsafe_allow_html=True)

    input_method = st.radio(
        "Input method",
        ("Enter Monument Name", "Upload Monument Image"),
        key="input_radio",
        horizontal=False
    )

    # Reset when input method changes (keeps logic identical)
    if st.session_state['last_input_method'] != input_method:
        st.session_state['monument_info'] = None
        st.session_state['translated_text'] = None
        st.session_state['audio_kannada'] = None
        st.session_state['audio_english'] = None
        st.session_state['last_input_method'] = input_method

    if input_method == "Enter Monument Name":
        st.markdown('<div style="margin-top:10px;" class="mini-card">', unsafe_allow_html=True)
        monument_name = st.text_input("Monument name", key="monument_name_input", placeholder="e.g., Hampi Virupaksha Temple")
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("Get Monument Information", key="get_name_info"):
            if monument_name and monument_name.strip():
                with st.spinner("Contacting the archive..."):
                    monument_hash = hashlib.sha256(monument_name.encode()).hexdigest()
                    result = process_monument_name(monument_hash, monument_name)
                    st.session_state['monument_info'] = result
                    st.session_state['translated_text'] = None
                    st.session_state['audio_kannada'] = None
                    st.session_state['audio_english'] = None
                    st.session_state['last_input_method'] = input_method
            else:
                st.warning("Please enter a monument name first.")

    else:
        st.markdown('<div style="margin-top:10px;" class="mini-card">', unsafe_allow_html=True)
        uploaded_image = st.file_uploader("Upload image (PNG/JPG/JPEG)", type=['png','jpg','jpeg'], key="file_uploader")
        st.markdown('</div>', unsafe_allow_html=True)

        if uploaded_image is not None:
            if not allowed_file(uploaded_image.name):
                st.error("Invalid file type. Allowed: PNG, JPG, JPEG.")
            else:
                st.image(uploaded_image, caption="Preview", use_column_width=True)
                if st.button("Analyze Monument", key="analyze_image"):
                    with st.spinner("Analyzing image..."):
                        image_bytes = uploaded_image.read()
                        image_hash = hashlib.sha256(image_bytes).hexdigest()
                        result = process_image(image_hash, image_bytes)
                        st.session_state['monument_info'] = result
                        st.session_state['translated_text'] = None
                        st.session_state['audio_kannada'] = None
                        st.session_state['audio_english'] = None
                        st.session_state['last_input_method'] = input_method

    st.markdown('</div>', unsafe_allow_html=True)

    # A small about / quick links card
    st.markdown('<div style="margin-top:18px;" class="section">', unsafe_allow_html=True)
    st.markdown('<h3>Quick Links</h3>', unsafe_allow_html=True)
    st.markdown('<p>Open other TimeLens tools and resources.</p>', unsafe_allow_html=True)
    col_q1, col_q2 = st.columns([1,1])
    with col_q1:
        st.markdown('<a class="stButton" href="https://monument-recognition1.streamlit.app/" target="_blank"><button style="width:100%;">Open Recognition</button></a>', unsafe_allow_html=True)
    with col_q2:
        st.markdown('<a class="stButton" href="https://huggingface.co/spaces/premjavali05/Sanskrit_Manuscripts" target="_blank"><button style="width:100%;">Open Manuscripts</button></a>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# RIGHT: Results & translation & audio (preserves all workflows)
with right_col:
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<h3>Results</h3>', unsafe_allow_html=True)
    if st.session_state['monument_info']:
        st.markdown('<div class="mini-card">', unsafe_allow_html=True)
        st.markdown('<div class="mini-title">Monument Information — English</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="result-text">{st.session_state["monument_info"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Buttons row: generate audio / translate
        btn_col1, btn_col2, btn_col3 = st.columns([1,1,1])
        with btn_col1:
            if st.button("Generate English Narration", key="gen_en"):
                with st.spinner("Generating English audio..."):
                    text_hash = hashlib.sha256(st.session_state['monument_info'].encode()).hexdigest()
                    audio_english = generate_speech(text_hash, st.session_state['monument_info'], lang='en')
                    if audio_english:
                        st.session_state['audio_english'] = audio_english
                    else:
                        st.error("English narration generation failed.")
        with btn_col2:
            if st.button("Translate to Kannada", key="translate"):
                with st.spinner("Translating to Kannada..."):
                    translated = translate_to_kannada(st.session_state['monument_info'])
                    st.session_state['translated_text'] = translated
        with btn_col3:
            if st.button("Copy Text", key="copy_text"):
                # Copy to clipboard via JS (best-effort; some hosts disable)
                js = f"navigator.clipboard && navigator.clipboard.writeText({repr(st.session_state['monument_info'])})"
                st.components.v1.html(f"<script>{js}</script>", height=10)

        # Audio player for English if available
        if st.session_state.get('audio_english'):
            st.markdown('<div style="margin-top:10px;">', unsafe_allow_html=True)
            st.markdown('<div class="mini-title">English Narration</div>', unsafe_allow_html=True)
            st.audio(st.session_state['audio_english'], format="audio/mpeg")
            st.markdown('</div>', unsafe_allow_html=True)

        # Show translated Kannada text and audio generation
        if st.session_state.get('translated_text'):
            st.markdown('<div style="margin-top:14px;" class="mini-card">', unsafe_allow_html=True)
            st.markdown('<div class="mini-title">Translated Text — Kannada</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="result-text">{st.session_state["translated_text"]}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            kn_col1, kn_col2 = st.columns([1,1])
            with kn_col1:
                if st.button("Generate Kannada Narration", key="gen_kn"):
                    with st.spinner("Generating Kannada audio..."):
                        text_hash = hashlib.sha256(st.session_state['translated_text'].encode()).hexdigest()
                        audio_kannada = generate_speech(text_hash, st.session_state['translated_text'], lang='kn')
                        if audio_kannada:
                            st.session_state['audio_kannada'] = audio_kannada
                        else:
                            st.error("Kannada narration generation failed.")
            with kn_col2:
                if st.session_state.get('audio_kannada'):
                    st.markdown('<div style="margin-top:8px;">', unsafe_allow_html=True)
                    st.markdown('<div class="mini-title">Kannada Narration</div>', unsafe_allow_html=True)
                    st.audio(st.session_state['audio_kannada'], format="audio/mpeg")
                    st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.info("No result yet. Enter a monument name or upload an image and click the appropriate button to start.")

    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown('<div class="footer">Built with ❤️ · TimeLens © 2025</div>', unsafe_allow_html=True)
