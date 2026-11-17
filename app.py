import hashlib
import logging
import os
from io import BytesIO
from typing import List

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from deep_translator import GoogleTranslator
from gtts import gTTS
from google import genai
from google.genai import types

# Optional local .env support. On Streamlit Community Cloud, use st.secrets.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# -----------------------------------------------------------------------------
# APP CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Monument Information and Narration",
    page_icon="🏛️",
    layout="centered",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.8-flash"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_DIMENSION = 800
TRANSLATION_CHUNK_SIZE = 4500


# -----------------------------------------------------------------------------
# SECRETS / GEMINI CLIENT
# -----------------------------------------------------------------------------
def get_gemini_api_key() -> str:
    """Read the key from Streamlit secrets first, then local environment."""
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        # st.secrets may not exist when running locally without secrets.toml.
        secret_key = ""

    return str(secret_key or os.getenv("GEMINI_API_KEY", "")).strip()


GEMINI_API_KEY = get_gemini_api_key()

if not GEMINI_API_KEY:
    st.error(
        "Gemini API key not found. Add GEMINI_API_KEY to your Streamlit "
        "Community Cloud app secrets."
    )
    st.code('GEMINI_API_KEY = "your_gemini_api_key"', language="toml")
    st.stop()


@st.cache_resource(show_spinner=False)
def get_gemini_client(api_key: str):
    """Create one reusable Gemini client for this Streamlit app process."""
    return genai.Client(api_key=api_key)


gemini_client = get_gemini_client(GEMINI_API_KEY)


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def compress_image(image_bytes: bytes) -> bytes:
    """Resize and convert an uploaded image to JPEG to reduce API payload size."""
    try:
        with Image.open(BytesIO(image_bytes)) as original_image:
            image = ImageOps.exif_transpose(original_image)
            image = image.convert("RGB")
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )

            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()

    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.exception("Image compression failed: %s", exc)
        raise ValueError("The uploaded file is not a valid PNG or JPEG image.") from exc


def friendly_gemini_error(exc: Exception) -> str:
    """Return a useful message for common Gemini API errors."""
    error_text = str(exc)
    normalized = error_text.lower()

    if "429" in normalized or "resource_exhausted" in normalized or "quota" in normalized:
        return (
            "Gemini API quota or rate limit reached. Check your Gemini API usage "
            "and limits in Google AI Studio, then try again later."
        )
    if "403" in normalized or "permission_denied" in normalized:
        return (
            "Gemini API access was denied. Check that the API key is valid and "
            "that the selected model is available to your project."
        )
    if "401" in normalized or "api key" in normalized or "unauthorized" in normalized:
        return "Gemini could not authenticate the API key. Check GEMINI_API_KEY in Streamlit secrets."
    if "404" in normalized or "not found" in normalized:
        return (
            f"The Gemini model '{GEMINI_MODEL}' was not found or is unavailable "
            "to this API key. Check the model name in Google AI Studio."
        )

    logger.exception("Gemini API request failed", exc_info=exc)
    return f"Gemini request failed: {error_text}"


def split_text(text: str, max_chars: int = TRANSLATION_CHUNK_SIZE) -> List[str]:
    """Split long text into chunks while keeping paragraph boundaries where possible."""
    chunks: List[str] = []
    current = ""

    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        while len(paragraph) > max_chars:
            split_at = paragraph.rfind(" ", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars

            piece = paragraph[:split_at].strip()
            paragraph = paragraph[split_at:].strip()

            if current:
                chunks.append(current)
                current = ""
            if piece:
                chunks.append(piece)

        if not paragraph:
            continue

        candidate = f"{current}\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks or [text]


# -----------------------------------------------------------------------------
# GEMINI: MONUMENT NAME LOOKUP
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def process_monument_name(_monument_hash: str, monument_name: str) -> str:
    """Generate historical information from a monument name."""
    try:
        prompt = f"""
You are a careful historical information assistant.

Prepare a detailed, well-organized historical profile of: {monument_name}

Cover these points where reliable information is available:
1. Official and commonly used name
2. Exact location (city, state/region, and country)
3. Historical background and why it was built
4. Construction period, patrons, architects, builders, or dynasties
5. Architectural style and notable design features
6. Important historical events and people associated with it
7. Religious, cultural, political, or social significance, where relevant
8. Preservation, restoration, and present-day importance
9. Interesting facts that are well established

Accuracy requirements:
- Do not invent dates, people, events, or architectural details.
- Distinguish widely accepted facts from disputed or uncertain claims.
- If a detail cannot be established confidently, say that it is uncertain.
- Do not claim to have consulted live sources or archives.

Write in clear, informative English using plain text. Use headings and numbered
sections for readability, but do not use Markdown symbols such as # or *.
"""

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )

        result = (response.text or "").strip()
        if not result:
            return "Error: Gemini returned an empty response. Please try again."
        return result

    except Exception as exc:
        logger.exception("Error while processing monument name")
        return f"Error: {friendly_gemini_error(exc)}"


# -----------------------------------------------------------------------------
# GEMINI: MONUMENT IMAGE IDENTIFICATION
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def process_image(_image_hash: str, image_bytes: bytes) -> str:
    """Identify a monument from an image and generate its historical profile."""
    try:
        if len(image_bytes) > MAX_FILE_SIZE:
            return "Error: Uploaded image is larger than the 5 MB limit."

        compressed_bytes = compress_image(image_bytes)
        if len(compressed_bytes) > MAX_FILE_SIZE:
            return "Error: Compressed image is still larger than the 5 MB limit."

        prompt = """
Carefully examine the uploaded photograph and identify the monument, building,
heritage site, or historic structure shown.

Start with an identification assessment:
1. Most likely monument name
2. City, region/state, and country, if identifiable
3. Visual clues supporting the identification
4. Confidence level: high, medium, or low

Then provide a detailed historical profile, if the identification is sufficiently
reliable. Cover its historical background, construction period, builders or
patrons, architectural style, important events, cultural significance,
preservation, and present-day importance.

Important accuracy rules:
- Do not guess a specific monument from weak visual evidence.
- If the image is ambiguous, say that you cannot identify it confidently and
  describe what additional information would help.
- Separate visual observations from historical claims.
- Do not invent dates, people, events, or facts.
- Mention uncertainty when reliable identification is not possible.

Write in clear English using plain text and readable section headings.
"""

        image_part = types.Part.from_bytes(
            data=compressed_bytes,
            mime_type="image/jpeg",
        )

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )

        result = (response.text or "").strip()
        if not result:
            return "Error: Gemini could not analyze this image. Please try another image."
        return result

    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Error while processing monument image")
        return f"Error: {friendly_gemini_error(exc)}"


# -----------------------------------------------------------------------------
# KANNADA TRANSLATION
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def translate_to_kannada(text: str) -> str:
    """Translate long English text to Kannada in manageable chunks."""
    try:
        translator = GoogleTranslator(source="en", target="kn")
        chunks = split_text(text)
        translated_chunks = []

        for chunk in chunks:
            translated = translator.translate(chunk)
            if not translated:
                raise ValueError("The translator returned an empty result.")
            translated_chunks.append(translated)

        return "\n\n".join(translated_chunks)

    except Exception as exc:
        logger.exception("Kannada translation failed")
        return f"Translation failed: {str(exc)}"


# -----------------------------------------------------------------------------
# TEXT-TO-SPEECH
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def generate_speech(_text_hash: str, text: str, lang: str = "kn"):
    """Generate an MP3 narration and return its bytes."""
    try:
        mp3_buffer = BytesIO()
        tts = gTTS(text=text, lang=lang)
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)
        return mp3_buffer.getvalue()

    except Exception as exc:
        logger.exception("gTTS failed for language %s", lang)
        return None


# -----------------------------------------------------------------------------
# STREAMLIT USER INTERFACE
# -----------------------------------------------------------------------------
st.title("🏛️ Monument Information and Narration")
st.caption(
    "Identify a monument by name or photograph, explore its history, "
    "and listen to English or Kannada narration."
)

input_method = st.radio(
    "Choose how you want to provide monument information:",
    ("Enter Monument Name", "Upload Monument Image"),
    horizontal=True,
)

# Initialize session state.
DEFAULT_SESSION_VALUES = {
    "monument_info": None,
    "translated_text": None,
    "audio_kannada": None,
    "audio_english": None,
    "last_input_method": None,
}

for state_key, default_value in DEFAULT_SESSION_VALUES.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value

# Clear old results when the user switches between input methods.
if st.session_state["last_input_method"] != input_method:
    st.session_state["monument_info"] = None
    st.session_state["translated_text"] = None
    st.session_state["audio_kannada"] = None
    st.session_state["audio_english"] = None
    st.session_state["last_input_method"] = input_method


# -----------------------------------------------------------------------------
# INPUT: MONUMENT NAME
# -----------------------------------------------------------------------------
if input_method == "Enter Monument Name":
    st.subheader("Enter Monument Name")
    monument_name = st.text_input(
        "Monument name",
        placeholder="For example: Hampi, Taj Mahal, Gol Gumbaz...",
    )

    if st.button(
        "Get Monument Information",
        type="primary",
        disabled=not monument_name.strip(),
    ):
        monument_hash = hashlib.sha256(
            monument_name.strip().encode("utf-8")
        ).hexdigest()

        with st.spinner("Generating monument information with Gemini..."):
            result = process_monument_name(monument_hash, monument_name.strip())

        if result.startswith("Error:"):
            st.session_state["monument_info"] = None
            st.error(result)
        else:
            st.session_state["monument_info"] = result
            st.session_state["translated_text"] = None
            st.session_state["audio_kannada"] = None
            st.session_state["audio_english"] = None
            st.success("Monument information generated successfully.")


# -----------------------------------------------------------------------------
# INPUT: MONUMENT IMAGE
# -----------------------------------------------------------------------------
else:
    st.subheader("Upload Monument Image")
    uploaded_image = st.file_uploader(
        "Choose a monument photograph (PNG, JPG, or JPEG)",
        type=["png", "jpg", "jpeg"],
    )

    if uploaded_image is not None:
        if not allowed_file(uploaded_image.name):
            st.error("Invalid file type. Please upload a PNG or JPEG image.")
        else:
            image_bytes = uploaded_image.getvalue()

            if len(image_bytes) > MAX_FILE_SIZE:
                st.error("The uploaded image exceeds the 5 MB limit.")
            else:
                try:
                    st.image(
                        image_bytes,
                        caption="Uploaded monument photograph",
                        use_container_width=True,
                    )

                    if st.button("Analyze Monument", type="primary"):
                        image_hash = hashlib.sha256(image_bytes).hexdigest()

                        with st.spinner("Analyzing the photograph with Gemini..."):
                            result = process_image(image_hash, image_bytes)

                        if result.startswith("Error:"):
                            st.session_state["monument_info"] = None
                            st.error(result)
                        else:
                            st.session_state["monument_info"] = result
                            st.session_state["translated_text"] = None
                            st.session_state["audio_kannada"] = None
                            st.session_state["audio_english"] = None
                            st.success("Image analysis completed successfully.")

                except (UnidentifiedImageError, OSError):
                    st.error("The uploaded file could not be opened as an image.")


# -----------------------------------------------------------------------------
# OUTPUT: ENGLISH INFORMATION AND AUDIO
# -----------------------------------------------------------------------------
if st.session_state["monument_info"]:
    st.divider()
    st.subheader("Monument Information (English)")
    st.write(st.session_state["monument_info"])

    if st.button("Generate English Narration"):
        text_to_speak = st.session_state["monument_info"]
        text_hash = hashlib.sha256(text_to_speak.encode("utf-8")).hexdigest()

        with st.spinner("Generating English narration..."):
            audio_english = generate_speech(
                text_hash,
                text_to_speak,
                lang="en",
            )

        if audio_english:
            st.session_state["audio_english"] = audio_english
        else:
            st.error("English narration generation failed. Please try again.")

    if st.session_state["audio_english"]:
        st.subheader("English Audio")
        st.audio(st.session_state["audio_english"], format="audio/mpeg")

    st.divider()

    # -------------------------------------------------------------------------
    # OUTPUT: KANNADA TRANSLATION AND AUDIO
    # -------------------------------------------------------------------------
    if st.button("Translate to Kannada"):
        with st.spinner("Translating the information to Kannada..."):
            translated = translate_to_kannada(
                st.session_state["monument_info"]
            )

        if translated.startswith("Translation failed:"):
            st.session_state["translated_text"] = None
            st.error(translated)
        else:
            st.session_state["translated_text"] = translated
            st.session_state["audio_kannada"] = None

    if st.session_state["translated_text"]:
        st.subheader("Translated Text (Kannada)")
        st.write(st.session_state["translated_text"])

        if st.button("Generate Kannada Narration"):
            text_to_speak = st.session_state["translated_text"]
            text_hash = hashlib.sha256(text_to_speak.encode("utf-8")).hexdigest()

            with st.spinner("Generating Kannada narration..."):
                audio_kannada = generate_speech(
                    text_hash,
                    text_to_speak,
                    lang="kn",
                )

            if audio_kannada:
                st.session_state["audio_kannada"] = audio_kannada
            else:
                st.error("Kannada narration generation failed. Please try again.")

        if st.session_state["audio_kannada"]:
            st.subheader("Kannada Audio")
            st.audio(st.session_state["audio_kannada"], format="audio/mpeg")

else:
    st.info(
        "Enter a monument name or upload a monument photograph to get started."
    )
