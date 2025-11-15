import streamlit as st 
import requests
import os
import base64
import logging
from deep_translator import GoogleTranslator
from io import BytesIO
from PIL import Image
import hashlib

# -------------------------------------------------------------------------------------
# FIX: Disable proxies so GoogleTranslator works properly on Streamlit Cloud
# -------------------------------------------------------------------------------------
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

# Load environment for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# Mistral API Key
MISTRAL_API_KEY = st.secrets.get("MISTRAL_API_KEY", os.getenv("MISTRAL_API_KEY"))
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY missing.")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

os.environ["NO_PROXY"] = "api.mistral.ai"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
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


@st.cache_data(show_spinner=False)
def process_monument_name(_hash, name):
    try:
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "pixtral-large-latest",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Explain the historical background of {name} in plain text. No markdown."}
                    ]
                }
            ]
        }
        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()

        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get("content", "No info found.")
        return info
    except Exception as e:
        return f"Error: {e}"


@st.cache_data(show_spinner=False)
def process_image(_hash, image_bytes):
    try:
        compressed_bytes = compress_image(image_bytes)
        if len(compressed_bytes) > MAX_FILE_SIZE:
            return "Error: File too large."

        image_base64 = base64.b64encode(compressed_bytes).decode("utf-8")

        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "pixtral-large-latest",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                        {"type": "text", "text": "Identify this monument and provide detailed history in plain text."}
                    ]
                }
            ]
        }

        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()

        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get("content", "No info found.")
        return info

    except Exception as e:
        return f"Error: {e}"


# -------------------------------------------------------------------------------------
# NEW: LibreTTS Text-to-Speech (FREE, CLOUD SAFE)
# -------------------------------------------------------------------------------------
def generate_speech(_hash, text, lang='kn'):
    try:
        tts_url = "https://libretranslate.de/tts"
        payload = {"q": text, "target": lang}

        response = requests.post(tts_url, data=payload)
        response.raise_for_status()

        audio_bytes = BytesIO(response.content)
        return audio_bytes
    except Exception as e:
        logger.error("LibreTTS error: %s", e)
        return None


# -------------------------------------------------------------------------------------
# Translation (deep_translator)
# -------------------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def translate_to_kannada(text):
    try:
        tr = GoogleTranslator(source='en', target='kn')
        return tr.translate(text)
    except Exception as e:
        return f"Translation error: {e}"


# -------------------------------------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------------------------------------
st.title("Monument Information & Narration")

input_method = st.radio("Choose Input Method", ("Enter Monument Name", "Upload Monument Image"))

if "monument_info" not in st.session_state:
    st.session_state.monument_info = None
    st.session_state.translated_text = None
    st.session_state.audio_kn = None
    st.session_state.audio_en = None
    st.session_state.last_method = None

if st.session_state.last_method != input_method:
    st.session_state.monument_info = None
    st.session_state.translated_text = None
    st.session_state.audio_kn = None
    st.session_state.audio_en = None
    st.session_state.last_method = input_method


# NAME INPUT
if input_method == "Enter Monument Name":
    name = st.text_input("Enter monument name")
    if name and st.button("Get Monument Info"):
        with st.spinner("Fetching information..."):
            _hash = hashlib.sha256(name.encode()).hexdigest()
            st.session_state.monument_info = process_monument_name(_hash, name)


# IMAGE INPUT
else:
    uploaded = st.file_uploader("Upload image", type=['png', 'jpg', 'jpeg'])
    if uploaded:
        st.image(uploaded, caption="Uploaded Image", use_container_width=True)
        if st.button("Analyze Monument"):
            with st.spinner("Analyzing image..."):
                img_bytes = uploaded.read()
                _hash = hashlib.sha256(img_bytes).hexdigest()
                st.session_state.monument_info = process_image(_hash, img_bytes)


# OUTPUT INFO
if st.session_state.monument_info:
    st.header("Monument Information")
    st.write(st.session_state.monument_info)

    # English Audio
    if st.button("Generate English Audio"):
        with st.spinner("Generating English audio..."):
            text_hash = hashlib.sha256(st.session_state.monument_info.encode()).hexdigest()
            st.session_state.audio_en = generate_speech(text_hash, st.session_state.monument_info, lang='en')

    if st.session_state.audio_en:
        st.audio(st.session_state.audio_en, format="audio/mpeg")

    # Translation
    if st.button("Translate to Kannada"):
        with st.spinner("Translating..."):
            st.session_state.translated_text = translate_to_kannada(st.session_state.monument_info)

    if st.session_state.translated_text:
        st.header("Kannada Translation")
        st.write(st.session_state.translated_text)

        # Kannada Audio
        if st.button("Generate Kannada Audio"):
            with st.spinner("Generating Kannada audio..."):
                text_hash = hashlib.sha256(st.session_state.translated_text.encode()).hexdigest()
                st.session_state.audio_kn = generate_speech(text_hash, st.session_state.translated_text, lang='kn')

        if st.session_state.audio_kn:
            st.audio(st.session_state.audio_kn, format="audio/mpeg")
