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

# Custom CSS to match the landing page theme
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Marcellus&display=swap');
    
    /* Global Styles */
    .stApp {
        background-color: #f3ebd8;
        color: #3e3423;
        font-family: 'Marcellus', serif;
    }
    
    /* Hero Title */
    .hero-title {
        font-family: 'Cinzel', serif;
        font-size: 3.8rem;
        background: linear-gradient(90deg, #b18400, #f3d27c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0;
    }
    
    .hero-subtitle {
        font-size: 1.4rem;
        color: #5d4a2d;
        text-align: center;
        margin-top: -10px;
        margin-bottom: 20px;
    }
    
    .hero-quote {
        font-style: italic;
        font-size: 1.2rem;
        text-align: center;
        color: #705c3b;
        margin-bottom: 40px;
    }
    
    /* Headers */
    h1, h2, h3 {
        font-family: 'Cinzel', serif;
        color: #a27800;
    }
    
    /* Sections */
    .section {
        background: #ffffff;
        padding: 25px;
        border-radius: 15px;
        border: 2px solid #d0b98a;
        box-shadow: 0 5px 15px rgba(0,0,0,0.15);
        margin-bottom: 20px;
        transition: 0.3s ease;
    }
    
    .section:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.2);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #a27800, #eecf82);
        color: white;
        font-weight: 600;
        border-radius: 10px;
        border: none;
        padding: 10px 18px;
        font-family: 'Marcellus', serif;
    }
    
    .stButton > button:hover {
        background: linear-gradient(90deg, #eecf82, #a27800);
    }
    
    /* Text areas */
    .stTextInput > div > div > input {
        background-color: #ffffff;
        border: 1px solid #d0b98a;
        border-radius: 10px;
        color: #3e3423;
        font-family: 'Marcellus', serif;
    }
    
    /* File uploader */
    .stFileUploader > div > div {
        background-color: #ffffff;
        border: 2px dashed #d0b98a;
        border-radius: 15px;
    }
    
    /* Radio buttons */
    .stRadio > div {
        background-color: #ffffff;
        border: 2px solid #d0b98a;
        border-radius: 15px;
        padding: 15px;
    }
    
    /* Info/Warning/Error messages */
    .stInfo, .stWarning, .stError {
        background-color: #e8dbc0;
        border: 1px solid #d0b98a;
        border-radius: 10px;
        color: #4b3a23;
    }
    
    /* Spinner */
    .stSpinner > div {
        color: #a27800;
    }
    
    /* Audio player */
    .stAudio > div > audio {
        background-color: #ffffff;
        border: 1px solid #d0b98a;
        border-radius: 10px;
    }
    
    /* Image display */
    .stImage > img {
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.15);
    }
    
    /* Footer */
    .footer {
        text-align: center;
        padding: 18px;
        font-size: 0.9rem;
        background-color: #e8dbc0;
        color: #4b3a23;
        margin-top: 30px;
        border-radius: 10px;
    }
    
    /* Fade-in animation for sections */
    .fade-in {
        animation: fadeIn 0.8s forwards;
        opacity: 0;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    </style>
""", unsafe_allow_html=True)

# Hero section
st.markdown('<h1 class="hero-title">TimeLens</h1>', unsafe_allow_html=True)
st.markdown('<h2 class="hero-subtitle">Monument Recognition & Historical Narration</h2>', unsafe_allow_html=True)
st.markdown('<p class="hero-quote">“Where ancient worlds whisper — and AI listens.”</p>', unsafe_allow_html=True)

# Initialize session state
if 'monument_info' not in st.session_state:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = None

# Input method selection
col1, col2 = st.columns([1, 3])
with col1:
    st.markdown('<div class="section fade-in"><h3>Choose Your Path</h3>', unsafe_allow_html=True)
    input_method = st.radio("Select how you want to provide monument information:", ("Enter Monument Name", "Upload Monument Image"))
with col2:
    st.markdown('<div class="section fade-in"><p>Embark on a journey through time. Enter a name or upload an image to uncover the stories etched in stone.</p></div>', unsafe_allow_html=True)

# Clear previous output if input method changes
if st.session_state['last_input_method'] != input_method:
    st.session_state['monument_info'] = None
    st.session_state['translated_text'] = None
    st.session_state['audio_kannada'] = None
    st.session_state['audio_english'] = None
    st.session_state['last_input_method'] = input_method

if input_method == "Enter Monument Name":
    with st.container():
        st.markdown('<div class="section fade-in">', unsafe_allow_html=True)
        st.markdown('<h3>By Name</h3>', unsafe_allow_html=True)
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
        st.markdown('</div>', unsafe_allow_html=True)
elif input_method == "Upload Monument Image":
    with st.container():
        st.markdown('<div class="section fade-in">', unsafe_allow_html=True)
        st.markdown('<h3>By Image</h3>', unsafe_allow_html=True)
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
        st.markdown('</div>', unsafe_allow_html=True)

# Display results if available
if st.session_state['monument_info']:
    with st.container():
        st.markdown('<div class="section fade-in">', unsafe_allow_html=True)
        st.markdown('<h3>Monument Information (English)</h3>', unsafe_allow_html=True)
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
            st.markdown('<h3>English Audio</h3>', unsafe_allow_html=True)
            st.audio(st.session_state['audio_english'], format="audio/mpeg")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Translation section
    with st.container():
        st.markdown('<div class="section fade-in">', unsafe_allow_html=True)
        if st.button("Translate to Kannada"):
            with st.spinner("Translating to Kannada..."):
                translated = translate_to_kannada(st.session_state['monument_info'])
                st.session_state['translated_text'] = translated
        if st.session_state['translated_text']:
            st.markdown('<h3>Translated Text (Kannada)</h3>', unsafe_allow_html=True)
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
                st.markdown('<h3>Kannada Audio</h3>', unsafe_allow_html=True)
                st.audio(st.session_state['audio_kannada'], format="audio/mpeg")
        st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state.get('monument_info') and not (input_method == "Enter Monument Name" and 'monument_name' in locals() and monument_name) and not (input_method == "Upload Monument Image" and 'uploaded_image' in locals() and uploaded_image):
    st.info("Please select an input method and provide a monument name or image to get started.")

# Footer
st.markdown('<div class="footer">Built with ❤️ · TimeLens © 2025</div>', unsafe_allow_html=True)
