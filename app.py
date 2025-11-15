import streamlit as st 
import requests
import os
import base64
import logging
from deep_translator import GoogleTranslator
from gtts import gTTS
from io import BytesIO
from PIL import Image
import hashlib

# ---------------------------------------------------------------------
# 🔥 OPTION 1 FIX: Disable ALL outbound proxies (important for Streamlit Cloud)
# ---------------------------------------------------------------------
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

# Attempt to load environment variables for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Mistral API Key
MISTRAL_API_KEY = st.secrets.get("MISTRAL_API_KEY", os.getenv("MISTRAL_API_KEY"))
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY not found.")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Force Mistral to bypass proxy as well
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
                            "text": (
                                f"Provide in depth historical information about {monument_name}. "
                                f"Provide the response in plain text without markdown formatting."
                            )
                        }
                    ]
                }
            ]
        }

        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()
        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get(
            "content", "No details found."
        )
        return info
    except Exception as e:
        logger.error("Name processing error: %s", e)
        return f"Error: {e}"


@st.cache_data(show_spinner=False)
def process_image(_image_hash, image_bytes):
    try:
        compressed_bytes = compress_image(image_bytes)
        if len(compressed_bytes) > MAX_FILE_SIZE:
            return "Error: Compressed file too large."

        image_base64 = base64.b64encode(compressed_bytes).decode("utf-8")

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
                            "text": "What monument is this? Provide in depth historical info in plain text."
                        }
                    ]
                }
            ]
        }

        response = requests.post(MISTRAL_URL, json=payload, headers=headers, proxies={"http": "", "https": ""})
        response.raise_for_status()
        result = response.json()
        info = result.get("choices", [{}])[0].get("message", {}).get(
            "content", "No details found."
        )
        return info

    except Exception as e:
        logger.error("Image processing error: %s", e)
        return f"Error: {e}"


# ---------------------------------------------------------------------
# TRANSLATION FUNCTION (deep_translator)
# With proxy disabled, it should now work on Streamlit Cloud
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def translate_to_kannada(text):
    try:
        translator = GoogleTranslator(source='en', target='kn')
        translated = translator.translate(text)
        if not translated:
            return "Translation failed: Empty output."
        return translated
    except Exception as e:
        logger.error("Translation error: %s", e)
        return f"Translation failed: {e}"


@st.cache_data(show_spinner=False)
def generate_speech(_text_hash, text, lang='kn'):
    try:
        mp3_fp = BytesIO()
        tts = gTTS(text=text, lang=lang)
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        return mp3_fp
    except Exception as e:
        logger.error("gTTS error: %s", e)
        return None


# ---------------------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------------------
st.title("Monument Information and Narration")

input_method = st.radio("Choose Input Method:", ("Enter Monument Name", "Upload Monument Image"))

if 'monument_info' not in st.session_state:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = None

if st.session_state['last_input_method'] != input_method:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = input_method


# ---------------------------------------
# NAME INPUT
# ---------------------------------------
if input_method == "Enter Monument Name":
    monument_name = st.text_input("Enter the monument name")

    if monument_name:
        if st.button("Get Monument Information"):
            with st.spinner("Fetching details..."):
                monument_hash = hashlib.sha256(monument_name.encode()).hexdigest()
                st.session_state['monument_info'] = process_monument_name(monument_hash, monument_name)


# ---------------------------------------
# IMAGE INPUT
# ---------------------------------------
elif input_method == "Upload Monument Image":
    uploaded_image = st.file_uploader("Upload an image", type=['png', 'jpg', 'jpeg'])

    if uploaded_image:
        st.image(uploaded_image, caption="Uploaded Image", use_container_width=True)

        if st.button("Analyze Monument"):
            with st.spinner("Analyzing image..."):
                image_bytes = uploaded_image.read()
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                st.session_state['monument_info'] = process_image(image_hash, image_bytes)


# ---------------------------------------
# RESULTS
# ---------------------------------------
if st.session_state['monument_info']:
    st.header("Monument Information (English)")
    st.write(st.session_state['monument_info'])

    if st.button("Generate English Narration"):
        with st.spinner("Generating audio..."):
            text_hash = hashlib.sha256(st.session_state['monument_info'].encode()).hexdigest()
            st.session_state['audio_english'] = generate_speech(text_hash, st.session_state['monument_info'], lang='en')

    if st.session_state['audio_english']:
        st.audio(st.session_state['audio_english'], format="audio/mpeg")

    # Translation
    if st.button("Translate to Kannada"):
        with st.spinner("Translating..."):
            st.session_state['translated_text'] = translate_to_kannada(st.session_state['monument_info'])

    if st.session_state['translated_text']:
        st.header("Kannada Translation")
        st.write(st.session_state['translated_text'])

        if st.button("Generate Kannada Narration"):
            with st.spinner("Generating Kannada audio..."):
                text_hash = hashlib.sha256(st.session_state['translated_text'].encode()).hexdigest()
                st.session_state['audio_kannada'] = generate_speech(
                    text_hash, st.session_state['translated_text'], lang='kn'
                )

        if st.session_state['audio_kannada']:
            st.audio(st.session_state['audio_kannada'], format="audio/mpeg")

