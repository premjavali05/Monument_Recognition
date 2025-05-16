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

# Attempt to load environment variables for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, rely on Streamlit secrets or system environment
    pass

# Mistral API Key and Endpoint
# Use st.secrets for Streamlit Cloud, fall back to os.getenv for local
MISTRAL_API_KEY = st.secrets.get("MISTRAL_API_KEY", os.getenv("MISTRAL_API_KEY"))
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY not found. Please set it in Streamlit Secrets or a .env file for local development.")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Set NO_PROXY to bypass proxies for Mistral API
os.environ["NO_PROXY"] = "api.mistral.ai"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for image processing
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGE_DIMENSION = 800  # Max width/height for resizing

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
        return image_bytes  # Fallback to original

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

# Streamlit app
st.title("Monument Information and Narration")

# Input method selection
st.header("Choose Input Method")
input_method = st.radio("Select how you want to provide monument information:", ("Enter Monument Name", "Upload Monument Image"))

# Initialize session state
if 'monument_info' not in st.session_state:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = None

# Clear previous output if input method changes
if st.session_state['last_input_method'] != input_method:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = input_method

if input_method == "Enter Monument Name":
    st.header("Enter Monument Name")
    monument_name = st.text_input("Enter the name of the monument")
    
    if monument_name:
        if st.button("Get Monument Information"):
            with st.spinner("Fetching monument information..."):
                # Compute monument name hash for caching
                monument_hash = hashlib.sha256(monument_name.encode()).hexdigest()
                result = process_monument_name(monument_hash, monument_name)
                st.session_state['monument_info'] = result
                st.session_state['translated_text'] = None
                st.session_state['audio_kannada'] = None
                st.session_state['audio_english'] = None
                st.session_state['last_input_method'] = input_method

elif input_method == "Upload Monument Image":
    st.header("Upload Monument Image")
    uploaded_image = st.file_uploader("Choose an image (PNG, JPG, JPEG)", type=['png', 'jpg', 'jpeg'])
    
    if uploaded_image is not None:
        if not allowed_file(uploaded_image.name):
            st.error("Invalid file type. Only PNG, JPG, JPEG allowed.")
        else:
            st.image(uploaded_image, caption="Uploaded Image", use_container_width=True)
            if st.button("Analyze Monument"):
                with st.spinner("Analyzing image..."):
                    image_bytes = uploaded_image.read()
                    # Compute image hash for caching
                    image_hash = hashlib.sha256(image_bytes).hexdigest()
                    result = process_image(image_hash, image_bytes)
                    st.session_state['monument_info'] = result
                    st.session_state['translated_text'] = None
                    st.session_state['audio_kannada'] = None
                    st.session_state['audio_english'] = None
                    st.session_state['last_input_method'] = input_method

# Display results if available
if st.session_state['monument_info']:
    st.header("Monument Information (English)")
    st.write(st.session_state['monument_info'])

    # English narration
    if st.button("Generate English Narration"):
        with st.spinner("Generating English audio..."):
            text_hash = hashlib.sha256(st.session_state['monument_info'].encode()).hexdigest()
            audio_english = generate_speech(text_hash, st.session_state['monument_info'], lang='en')
            if audio_english:
                st.session_state['audio_english'] = audio_english
            else:
                st.error("English narration generation failed.")

    if st.session_state['audio_english']:
        st.header("English Audio")
        st.audio(st.session_state['audio_english'], format="audio/mpeg")

    # Translation section
    if st.button("Translate to Kannada"):
        with st.spinner("Translating to Kannada..."):
            translated = translate_to_kannada(st.session_state['monument_info'])
            st.session_state['translated_text'] = translated

    if st.session_state['translated_text']:
        st.header("Translated Text (Kannada)")
        st.write(st.session_state['translated_text'])

        # Kannada narration
        if st.button("Generate Kannada Narration"):
            with st.spinner("Generating Kannada audio..."):
                text_hash = hashlib.sha256(st.session_state['translated_text'].encode()).hexdigest()
                audio_kannada = generate_speech(text_hash, st.session_state['translated_text'], lang='kn')
                if audio_kannada:
                    st.session_state['audio_kannada'] = audio_kannada
                else:
                    st.error("Kannada narration generation failed.")

        if st.session_state['audio_kannada']:
            st.header("Kannada Audio")
            st.audio(st.session_state['audio_kannada'], format="audio/mpeg")

if not st.session_state.get('monument_info') and not (input_method == "Enter Monument Name" and monument_name) and not (input_method == "Upload Monument Image" and uploaded_image):
    st.info("Please select an input method and provide a monument name or image to get started.")
