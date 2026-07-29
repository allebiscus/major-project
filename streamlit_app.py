import json
import io
import os
import base64
import random
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

ACTIVITIES = {
    "Pattern Recognition": "pattern",
    "Logic and Problem Solving": "logic",
    "Sequencing": "sequencing",
}
DIFFICULTIES = ["beginner", "intermediate", "hard"]

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BACKEND_URL = os.getenv("WORKSHEET_BACKEND_URL", "http://localhost:8000/generate")
EXAMPLE_ACTIVITY_IMAGES = {
    "pattern": {
        "beginner": BASE_DIR / "activities" / "pattern" / "pattern_activity_423.png",
        "intermediate": BASE_DIR / "activities" / "pattern" / "pattern_activity_200.png",
        "hard": BASE_DIR / "activities" / "pattern" / "pattern_activity_88.png",
    },
    "logic": {
        "beginner": BASE_DIR / "activities" / "logic problem solving" / "BEGINNER_120.png",
        "intermediate": BASE_DIR / "activities" / "logic problem solving" / "INTERMEDDIATE_101.png",
        "hard": BASE_DIR / "activities" / "logic problem solving" / "HARD_127.png",
    },
    "sequencing": {
        "beginner": BASE_DIR / "activities" / "sequencing" / "size_ordering_128.png",
        "intermediate": BASE_DIR / "activities" / "sequencing" / "size_ordering_123.png",
        "hard": BASE_DIR / "activities" / "sequencing" / "size_ordering_125.png",
    },
}

OPTION_ICON_OVERRIDES = {
    "star": ["bi/star-fill", "mdi/star"],
    "moon": ["bi/moon-stars-fill", "mdi/moon-waning-crescent"],
    "sun": ["bi/sun-fill", "mdi/weather-sunny"],
    "tree": ["mdi/tree", "bi/tree-fill"],
    "flower": ["mdi/flower", "bi/flower1"],
    "apple": ["mdi/food-apple", "bi/apple"],
    "cup": ["bi/cup-straw", "mdi/cup"],
    "car": ["bi/car-front-fill", "mdi/car"],
    "train": ["bi/train-front-fill", "mdi/train"],
    "book": ["bi/book-fill", "mdi/book-open-page-variant"],
    "kite": ["mdi/kite", "bi/send-fill"],
    "robot": ["mdi/robot", "bi/cpu-fill"],
    "cat": ["mdi/cat", "bi/emoji-smile-fill"],
    "dog": ["mdi/dog", "bi/emoji-smile-fill"],
    "duck": ["mdi/duck", "bi/emoji-smile-fill"],
    "rabbit": ["mdi/rabbit", "bi/emoji-smile-fill"],
    "elephant": ["mdi/elephant", "bi/emoji-smile-fill"],
    "bee": ["mdi/bee", "bi/emoji-smile-fill"],
}

OPTION_EMOJI_FALLBACK = {
    "star": "⭐",
    "moon": "🌙",
    "sun": "☀️",
    "tree": "🌳",
    "flower": "🌸",
    "apple": "🍎",
    "cup": "🥤",
    "car": "🚗",
    "train": "🚂",
    "book": "📘",
    "kite": "🪁",
    "robot": "🤖",
    "cat": "🐱",
    "dog": "🐶",
    "duck": "🦆",
    "rabbit": "🐰",
    "elephant": "🐘",
    "bee": "🐝",
}


def post_json(url, payload, timeout=180):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw_body = response.read().decode("utf-8")
        return json.loads(raw_body)


def _build_student_pattern_choices(payload, all_tokens):
    correct = str(payload.get("correct_answer", "")).strip()
    if not correct:
        return []

    sequence_tokens = []
    sequence = payload.get("sequence") if isinstance(payload, dict) else None
    if isinstance(sequence, list):
        for item in sequence:
            if isinstance(item, str):
                token = item.strip()
                if token and token != "?" and token != correct and token not in sequence_tokens:
                    sequence_tokens.append(token)

    # Keep option count aligned with puzzle complexity.
    unique_in_puzzle = set(sequence_tokens)
    unique_in_puzzle.add(correct)
    option_count = min(3, max(2, len(unique_in_puzzle)))

    wrong_pool = list(sequence_tokens)
    for token in all_tokens:
        if token != correct and token not in wrong_pool:
            wrong_pool.append(token)

    fallback_tokens = ["star", "moon", "tree", "kite", "cup", "car", "book", "apple"]
    for token in fallback_tokens:
        if token != correct and token not in wrong_pool:
            wrong_pool.append(token)

    needed_wrong = option_count - 1
    wrong_choices = wrong_pool[:needed_wrong]
    choices = [correct] + wrong_choices
    random.shuffle(choices)
    return choices


def _pattern_signature_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    sequence = payload.get("sequence")
    correct_answer = payload.get("correct_answer")
    if not isinstance(sequence, list) or not sequence or not isinstance(correct_answer, str):
        return None

    full = []
    for item in sequence:
        if not isinstance(item, str):
            return None
        token = item.strip()
        if not token:
            return None
        if token == "?":
            token = correct_answer.strip()
        full.append(token)

    symbol_map = {}
    next_code = ord("A")
    signature = []
    for token in full:
        if token not in symbol_map:
            symbol_map[token] = chr(next_code)
            next_code += 1
        signature.append(symbol_map[token])
    return "".join(signature)


@st.cache_data(show_spinner=False)
def _get_option_icon_bytes(option_name):
    if not isinstance(option_name, str) or not option_name.strip():
        return None

    normalized = option_name.strip().lower().replace(" ", "-")

    candidate_ids = []
    candidate_ids.extend(OPTION_ICON_OVERRIDES.get(normalized, []))
    candidate_ids.extend(
        [
            f"bi/{normalized}-fill",
            f"bi/{normalized}",
            f"mdi/{normalized}",
        ]
    )

    candidate_urls = [f"https://api.iconify.design/{icon_id}.png?width=96&height=96" for icon_id in candidate_ids]

    for url in candidate_urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=4) as response:
                if response.status == 200:
                    icon_bytes = response.read()
                    # PNG signature check to avoid PIL parsing errors in st.image.
                    if icon_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                        return icon_bytes
        except Exception:
            continue

    return None


def _get_option_emoji(option_name):
    if not isinstance(option_name, str):
        return None
    normalized = option_name.strip().lower()
    return OPTION_EMOJI_FALLBACK.get(normalized)


@st.cache_data(show_spinner=False)
def _extract_pattern_token_cards(image_path, sequence_tuple, card_size=200, spacing=20):
    """Extract per-token card crops from a generated pattern strip image."""
    card_bytes_by_token = {}
    if not image_path:
        return card_bytes_by_token

    image_file = Path(str(image_path))
    if not image_file.exists():
        return card_bytes_by_token

    try:
        with Image.open(image_file) as src:
            image = src.convert("RGBA")
    except Exception:
        return card_bytes_by_token

    for idx, token in enumerate(sequence_tuple):
        if not isinstance(token, str):
            continue
        name = token.strip()
        if not name or name == "?" or name in card_bytes_by_token:
            continue

        x1 = spacing + idx * (card_size + spacing)
        y1 = spacing
        x2 = x1 + card_size
        y2 = y1 + card_size
        if x2 > image.width or y2 > image.height:
            continue

        crop = image.crop((x1, y1, x2, y2))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        card_bytes_by_token[name.lower()] = buffer.getvalue()

    return card_bytes_by_token

@st.cache_data(show_spinner=False)
def _extract_sequencing_item_cards(image_path, n_items, card_size=320, spacing=30):
    card_bytes_list = []
    if not image_path:
        return card_bytes_list
    image_file = Path(str(image_path))
    if not image_file.exists():
        return card_bytes_list
    try:
        with Image.open(image_file) as src:
            image = src.convert("RGBA")
    except Exception:
        return card_bytes_list
    for i in range(n_items):
        x1 = spacing + i * (card_size + spacing)
        y1 = spacing
        x2 = x1 + card_size
        y2 = y1 + card_size
        if x2 > image.width or y2 > image.height:
            card_bytes_list.append(None)
            continue
        crop = image.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        card_bytes_list.append(buf.getvalue())
    return card_bytes_list


# Page Configuration
st.set_page_config(page_title="Kid Worksheet Maker", page_icon="🎨", layout="wide")


@st.cache_data(show_spinner=False)
def _audio_b64(filename):
    path = BASE_DIR / filename
    if path.exists():
        return base64.b64encode(path.read_bytes()).decode()
    return None


def _play_sound(filename):
    b64 = _audio_b64(filename)
    if b64:
        nonce = random.randint(0, 10 ** 9)
        # components.html renders in an isolated iframe so the script actually executes every call
        components.html(
            f'<script>var _s{nonce}=new Audio("data:audio/mpeg;base64,{b64}");_s{nonce}.play();</script>',
            height=0,
            scrolling=False,
        )

# Custom Styling Injection
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;600;700&family=Quicksand:wght@500;700&display=swap');

        :root {
            --bg-playroom: #FFFDF0;
            --bubblegum: #FF7B9C;
            --sky: #4EA8DE;
            --sunshine: #FFD166;
            --grass: #06D6A0;
            --midnight: #2E294E;
            --cloud-white: #FFFFFF;
        }

        .stApp {
            background-color: var(--bg-playroom);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(255, 123, 156, 0.20), transparent 28%),
                radial-gradient(circle at 85% 18%, rgba(78, 168, 222, 0.22), transparent 30%),
                radial-gradient(circle at 18% 82%, rgba(6, 214, 160, 0.20), transparent 30%),
                radial-gradient(circle at 84% 76%, rgba(255, 209, 102, 0.20), transparent 28%),
                linear-gradient(145deg, #fffef7 0%, #fff9ec 45%, #f7fbff 100%);
            color: var(--midnight);
            font-family: 'Quicksand', sans-serif;
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Fredoka', sans-serif !important;
            font-weight: 700 !important;
            color: var(--midnight) !important;
            letter-spacing: -0.01em !important;
        }

        .hero {
            position: relative;
            background: var(--cloud-white);
            border: 4px solid var(--midnight);
            border-radius: 32px;
            padding: 40px 36px;
            box-shadow: 8px 8px 0px var(--midnight);
            margin-bottom: 30px;
        }

        .hero h1 {
            font-size: clamp(2.5rem, 5vw, 4.5rem) !important;
            margin: 0 0 10px 0 !important;
            color: var(--bubblegum) !important;
            -webkit-text-stroke: 1px var(--midnight);
        }

        .hero p {
            font-size: 1.2rem;
            line-height: 1.6;
            color: var(--midnight);
            margin: 0;
            font-weight: 500;
        }

        .hero-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            margin-top: 20px;
        }

        /* Scoping style specifically to header toggle buttons to preserve original chip styling */
        .hero-chip-row .stButton > button {
            font-family: 'Fredoka', sans-serif !important;
            font-weight: 600 !important;
            border-radius: 16px !important;
            padding: 0.6rem 1.5rem !important;
            border: 2px solid var(--midnight) !important;
            color: var(--midnight) !important;
            font-size: 1rem !important;
            width: auto !important;
            transition: all 0.15s ease-out !important;
            background: var(--bubblegum) !important;
        }

        .panel, .stage {
            background: var(--cloud-white);
            border: 3px solid var(--midnight);
            border-radius: 28px;
            padding: 26px;
            box-shadow: 6px 6px 0px var(--midnight);
            margin-bottom: 24px;
        }
        
        .stage-accent {
            background: rgba(76, 168, 222, 0.08);
        }

        .tiny-label {
            font-family: 'Fredoka', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--bubblegum);
            margin-bottom: 0.5rem;
        }

        div[data-testid="stSelectbox"] label {
            font-family: 'Fredoka', sans-serif !important;
            font-weight: 700 !important;
            color: var(--midnight) !important;
            font-size: 1.2rem !important;
        }

        div[data-baseweb="select"] > div {
            border-radius: 16px !important;
            border: 3px solid var(--midnight) !important;
            background: var(--bg-playroom) !important;
            font-family: 'Quicksand', sans-serif !important;
            font-weight: 700 !important;
            color: var(--midnight) !important;
            font-size: 1.16rem !important;
            min-height: 64px !important;
            line-height: 1.2 !important;
            display: flex !important;
            align-items: center !important;
            padding-left: 8px !important;
        }

        div[data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
        div[data-baseweb="select"] span {
            font-size: 1.2rem !important;
            line-height: 1.2 !important;
            color: var(--midnight) !important;
        }

        div[data-baseweb="select"] svg {
            width: 20px !important;
            height: 20px !important;
            display: block !important;
            color: var(--midnight) !important;
            fill: var(--midnight) !important;
            opacity: 1 !important;
        }

        /* General action layout button specs (all non-quiz buttons) */
        .stButton > button[kind="secondary"] {
            width: 100%;
            background: var(--bubblegum) !important;
            color: var(--midnight) !important;
            border: 3px solid var(--midnight) !important;
            border-radius: 20px !important;
            padding: 1rem 1.5rem !important;
            font-family: 'Fredoka', sans-serif !important;
            font-size: 1.3rem !important;
            font-weight: 700 !important;
            box-shadow: 5px 5px 0px var(--midnight) !important;
            transition: all 0.15s ease-out !important;
        }

        div[data-testid="stDownloadButton"] > button {
            width: 100% !important;
            background: var(--bubblegum) !important;
            color: var(--midnight) !important;
            border: 3px solid var(--midnight) !important;
            border-radius: 20px !important;
            padding: 1rem 1.5rem !important;
            font-family: 'Fredoka', sans-serif !important;
            font-size: 1.3rem !important;
            font-weight: 700 !important;
            box-shadow: 5px 5px 0px var(--midnight) !important;
            transition: all 0.15s ease-out !important;
        }

        div[data-testid="stDownloadButton"] > button:hover {
            transform: translate(-2px, -2px) !important;
            box-shadow: 7px 7px 0px var(--midnight) !important;
        }

        div[data-testid="stDownloadButton"] > button:active {
            transform: translate(2px, 2px) !important;
            box-shadow: 1px 1px 0px var(--midnight) !important;
        }

        .stButton > button[kind="secondary"]:hover {
            transform: translate(-2px, -2px) !important;
            box-shadow: 7px 7px 0px var(--midnight) !important;
            background: var(--bubblegum) !important;
        }
        
        .stButton > button[kind="secondary"]:active {
            transform: translate(2px, 2px) !important;
            box-shadow: 1px 1px 0px var(--midnight) !important;
        }

        /* Student quiz option buttons only */
        .stButton > button[kind="primary"] {
            width: 160px !important;
            min-width: 160px !important;
            background: #2e294e !important;
            color: #ffffff !important;
            border: 3px solid #2e294e !important;
            border-radius: 16px !important;
            padding: 0.55rem 0.9rem !important;
            font-family: 'Fredoka', sans-serif !important;
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            box-shadow: 3px 3px 0px #ff7b9c !important;
            margin: 0 auto !important;
            display: block !important;
        }

        div[data-testid="stButton"]:has(> button[kind="primary"]) {
            display: flex !important;
            justify-content: center !important;
            margin-top: 0.2rem !important;
        }

        .stButton > button[kind="primary"]:hover {
            transform: translate(-1px, -1px) !important;
            box-shadow: 4px 4px 0px #ff7b9c !important;
            background: #242042 !important;
        }

        .stButton > button[kind="primary"]:active {
            transform: translate(1px, 1px) !important;
            box-shadow: 1px 1px 0px #ff7b9c !important;
        }

        .output-frame {
            border: 3px dashed var(--midnight);
            background: var(--cloud-white);
            border-radius: 24px;
            padding: 20px;
            margin-top: 10px;
        }

        .status-pill {
            font-family: 'Fredoka', sans-serif;
            font-weight: 600;
            border: 3px solid var(--midnight);
            background: var(--bg-playroom);
            color: var(--midnight);
            border-radius: 20px;
            padding: 0.6rem 1.2rem;
            font-size: 1.1rem;
            box-shadow: 4px 4px 0px var(--midnight);
            text-align: center;
            margin-bottom: 12px;
        }

        .soft-rule {
            height: 4px;
            background: var(--midnight);
            border-radius: 2px;
            margin: 1.5rem 0;
            opacity: 0.15;
        }

        .quiz-feedback {
            border: 3px solid var(--midnight);
            border-radius: 16px;
            padding: 10px 14px;
            font-family: 'Fredoka', sans-serif;
            font-size: 1.05rem;
            font-weight: 700;
            margin: 0.7rem 0 1rem 0;
            color: #161616;
            box-shadow: 3px 3px 0px var(--midnight);
        }

        .quiz-feedback.error {
            background: #ffb3b3;
        }

        .quiz-feedback.success {
            background: #bff4c4;
        }

        .option-emoji {
            font-size: 2.6rem;
            line-height: 1;
            text-align: center;
            margin: 4px 0 10px 0;
        }

        .student-answer-prompt {
            font-family: 'Fredoka', sans-serif;
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--midnight);
            text-align: center;
            margin: 0.55rem 0 0.8rem 0;
        }

        .student-mode-title {
            font-family: 'Fredoka', sans-serif;
            font-size: clamp(2.0rem, 2.8vw, 2.6rem);
            font-weight: 700;
            color: var(--midnight);
            text-align: center;
            margin: 0.2rem 0 0.6rem 0;
            line-height: 1.12;
        }

    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize target display state profiles
if "user_mode" not in st.session_state:
    st.session_state["user_mode"] = "teacher"

if "student_options" not in st.session_state:
    st.session_state["student_options"] = {}

# Header Block
st.markdown(
    """
    <div class="hero">
        <div class="tiny-label">🎨 Activity Studio for Teachers & Parents</div>
        <h1>AI-Powered Activity Generator</h1>
        <p>Pick a game concept and difficulty level below! You can either create activities for your students or let them play in the interactive segment.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Mode Selector Button row positioned contextually at header base
header_btn_container = st.container()
with header_btn_container:
    # Custom CSS positioning wrapper injection
    st.markdown('<div class="hero-chip-row">', unsafe_allow_html=True)
    btn_col1, btn_col2, _ = st.columns([0.2, 0.2, 0.6])
    
    with btn_col1:
        # Teacher Selection View Controller Style Logic
        is_t_selected = st.session_state["user_mode"] == "teacher"
        t_bg = "background: var(--bubblegum) !important; color: white !important; box-shadow: 3px 3px 0px var(--midnight) !important;" if is_t_selected else "background: rgba(255, 123, 156, 0.18) !important; color: var(--midnight) !important; box-shadow: 3px 3px 0px var(--midnight) !important;"
        if st.button("Teacher Mode", key="toggle_teacher_view"):
            st.session_state["user_mode"] = "teacher"
            st.rerun()
        st.markdown(f"<style>div[data-testid='stSubheader'] + div .stButton:nth-child(1) button {{ {t_bg} }}</style>", unsafe_allow_html=True)

    with btn_col2:
        # Student Selection View Controller Style Logic
        is_s_selected = st.session_state["user_mode"] == "student"
        s_bg = "background: var(--bubblegum) !important; color: white !important; box-shadow: 3px 3px 0px var(--midnight) !important;" if is_s_selected else "background: rgba(255, 123, 156, 0.18) !important; color: var(--midnight) !important; box-shadow: 3px 3px 0px var(--midnight) !important;"
        if st.button("Student Mode", key="toggle_student_view"):
            st.session_state["user_mode"] = "student"
            st.rerun()
        st.markdown(f"<style>div[data-testid='stSubheader'] + div .stButton:nth-child(2) button {{ {s_bg} }}</style>", unsafe_allow_html=True)
    st.markdown('</div><br>', unsafe_allow_html=True)


# Render Content Blocks Conditionally based on selected Header Tab State
if st.session_state["user_mode"] == "teacher":

    # Workspace Columns Split - Styled directly as Teacher & Student areas
    left_column, right_column = st.columns([0.95, 1.05], gap="large")

    with left_column:
        st.markdown('<div class="stage stage-accent">', unsafe_allow_html=True)
        st.markdown('<div class="tiny-label">🍎 TEACHERS AREA</div>', unsafe_allow_html=True)
        st.subheader("Configure Design")
        
        activity_label = st.selectbox("Choose Activity Type", list(ACTIVITIES.keys()), index=0)
        difficulty = st.selectbox("Target Difficulty", DIFFICULTIES, index=0)
        
        # Engine Server input completely removed from UI, handles setup quietly in background
        backend_url = DEFAULT_BACKEND_URL
        st.markdown("</div>", unsafe_allow_html=True)

    with right_column:
        st.markdown('<div class="stage stage-accent">', unsafe_allow_html=True)
        st.markdown('<div class="tiny-label">🖼️ EXAMPLE PREVIEW</div>', unsafe_allow_html=True)
        st.subheader("Sample Activity Image")

        activity_key = ACTIVITIES[activity_label]
        difficulty_map = EXAMPLE_ACTIVITY_IMAGES.get(activity_key, {})
        example_image_path = difficulty_map.get(difficulty) or difficulty_map.get("beginner")
        if example_image_path and example_image_path.exists():
            st.image(str(example_image_path), use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    activity_kind = ACTIVITIES[activity_label]
    
  
    go_pressed = st.button("Make Fresh Worksheet", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    selection_payload = {
        "activity": activity_kind,
        "difficulty": difficulty,
    }

    # Action execution processes
    if go_pressed:
        st.session_state.pop("last_response", None)
        st.session_state["last_selection"] = selection_payload
        st.session_state["last_backend_url"] = backend_url

        try:
            with st.spinner("Please wait a few seconds as we generate it..."):
                backend_response = post_json(backend_url.strip(), selection_payload)
            st.session_state["last_response"] = backend_response
        except urllib.error.HTTPError as error:
            st.session_state.pop("last_response", None)
            st.error(f"Engine responded with HTTP Exception status code {error.code}: {error.read().decode('utf-8', errors='ignore')}")
        except Exception as error:
            st.session_state.pop("last_response", None)
            st.error(f"Unable to safely communicate with generation endpoint service: {error}")

    # Historical Rendering container display
    if "last_selection" in st.session_state:
        st.markdown('<div class="stage" style="margin-top: 1.5rem;">', unsafe_allow_html=True)
        st.markdown('<div class="tiny-label">Output Stage Viewport</div>', unsafe_allow_html=True)
        st.subheader("Generated Document Asset Package")

        if "last_response" in st.session_state:
            backend_response = st.session_state["last_response"]
            generated_at = backend_response.get("generated_at")
            if generated_at:
                st.caption(f"Fresh backend response timestamp: {generated_at}")

            if activity_kind == "pattern":
                payloads = backend_response.get("payloads", [])
                signatures = []
                for idx, payload in enumerate(payloads, start=1):
                    signature = _pattern_signature_from_payload(payload)
                    if signature:
                        signatures.append(f"#{idx}: {signature}")
                if signatures:
                    st.markdown("**Pattern structures returned:** " + " | ".join(signatures))
            
            png_path = backend_response.get("png_path")
            worksheet_path = backend_response.get("worksheet_path")

            preview_left, preview_right = st.columns(2, gap="large")

            with preview_left:
                st.markdown('<div class="output-frame">', unsafe_allow_html=True)
                st.markdown("<h3>🖼️ Activity Preview Image</h3>", unsafe_allow_html=True)
                if png_path:
                    candidate_png = Path(png_path)
                    if candidate_png.exists():
                        st.image(str(candidate_png), use_container_width=True)
                    else:
                        st.info("The preview image asset file has not been found located on active server workspace disks.")
                else:
                    st.info("No Preview Image relative paths returned by processing servers yet.")

                if worksheet_path:
                    candidate_ws = Path(worksheet_path)
                    if candidate_ws.exists():
                        st.download_button(
                            label="Download Worksheet as PNG",
                            data=candidate_ws.read_bytes(),
                            file_name=candidate_ws.name,
                            mime="image/png",
                            use_container_width=True,
                        )
                    else:
                        st.button("Download Worksheet as PNG", use_container_width=True, disabled=True)
                else:
                    st.button("Download Worksheet as PNG", use_container_width=True, disabled=True)    
                st.markdown("</div>", unsafe_allow_html=True)

            with preview_right:
                st.markdown('<div class="output-frame">', unsafe_allow_html=True)
                st.markdown("<h3>📝 Full Worksheet</h3>", unsafe_allow_html=True)
                if worksheet_path:
                    candidate_worksheet = Path(worksheet_path)
                    if candidate_worksheet.exists():
                        with candidate_worksheet.open("rb") as worksheet_file:
                            st.image(worksheet_file.read(), use_container_width=True)
                    else:
                        st.info("The requested worksheet path descriptor file does not exist on target servers.")
                else:
                    st.info("No composite page layout path references passed back from processing pipelines.")
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown('<div style="margin-top: 1.5rem;"></div>', unsafe_allow_html=True)
            with st.expander("🛠️ View raw JSON responses received from processing node servers"):
                st.json(backend_response)
        else:
            st.info("Waiting for configuration activation commands. Trigger the creation controls layout actions above to start processing workflow segments.")

        st.markdown("</div>", unsafe_allow_html=True)

else:
    st.markdown('<div class="panel">', unsafe_allow_html=True)

    if "student_completed" not in st.session_state:
        st.session_state["student_completed"] = False

    def _start_student_game(activity_label, difficulty_label):
        payload = {
            "activity": ACTIVITIES[activity_label],
            "difficulty": difficulty_label,
            "interactive": True,
            "puzzle_count": 3,
        }
        try:
            with st.spinner("Loading 3 puzzles, hang in there..."):
                student_response = post_json(DEFAULT_BACKEND_URL.strip(), payload)
            st.session_state["student_response"] = student_response
            st.session_state["student_current_index"] = 0
            st.session_state["student_feedback"] = ""
            st.session_state["student_options"] = {}
            st.session_state["student_completed"] = False
            st.rerun()
        except urllib.error.HTTPError as error:
            st.session_state.pop("student_response", None)
            st.error(f"Engine HTTP {error.code}: {error.read().decode('utf-8', errors='ignore')}")
        except Exception as error:
            st.session_state.pop("student_response", None)
            st.error(f"Unable to load interactive puzzles: {error}")

    response = st.session_state.get("student_response")
    show_game = False
    payloads = []
    activity = ""
    if isinstance(response, dict):
        activity = str(response.get("activity", "")).strip().lower()
        if activity in ("pattern", "sequencing", "logic"):
            payloads = response.get("payloads", [])
        if isinstance(payloads, list) and payloads:
            current_index = int(st.session_state.get("student_current_index", 0))
            show_game = current_index < len(payloads)

    header_cols = st.columns([1.2, 1.6, 1.2], gap="small")
    with header_cols[1]:
        st.markdown('<div class="tiny-label" style="text-align:center;">🎮 STUDENT MODE</div>', unsafe_allow_html=True)
        st.markdown('<div class="student-mode-title">Play Interactive Puzzle</div>', unsafe_allow_html=True)

    if not show_game:
        game_just_finished = isinstance(payloads, list) and len(payloads) > 0

        if game_just_finished:
            # Show completion celebration; only clear state when student chooses to continue
            _play_sound("correct.mp3")
            _cbust_end = 99
            st.markdown(f"""
<style>
@keyframes confetti-drop-{_cbust_end} {{
    0%   {{ transform: translateY(-50px) rotate(0deg) scale(1);     opacity: 1; }}
    80%  {{ opacity: 1; }}
    100% {{ transform: translateY(110vh) rotate(1080deg) scale(0.6); opacity: 0; }}
}}
.cc{_cbust_end} {{ position:fixed; top:-50px; z-index:99999; pointer-events:none; animation: confetti-drop-{_cbust_end} linear forwards; }}
</style>
<div class="cc{_cbust_end}" style="left:1%;  width:22px;height:22px;background:#ff7b9c;border-radius:4px;animation-duration:3.2s;animation-delay:0.00s;"></div>
<div class="cc{_cbust_end}" style="left:5%;  width:18px;height:26px;background:#4ea8de;border-radius:50%;animation-duration:2.8s;animation-delay:0.08s;"></div>
<div class="cc{_cbust_end}" style="left:10%; width:24px;height:16px;background:#ffd166;border-radius:4px;animation-duration:3.5s;animation-delay:0.15s;"></div>
<div class="cc{_cbust_end}" style="left:15%; width:20px;height:24px;background:#06d6a0;border-radius:50%;animation-duration:2.9s;animation-delay:0.04s;"></div>
<div class="cc{_cbust_end}" style="left:20%; width:26px;height:18px;background:#ff7b9c;border-radius:4px;animation-duration:2.7s;animation-delay:0.22s;"></div>
<div class="cc{_cbust_end}" style="left:25%; width:20px;height:20px;background:#4ea8de;border-radius:50%;animation-duration:3.3s;animation-delay:0.10s;"></div>
<div class="cc{_cbust_end}" style="left:30%; width:22px;height:24px;background:#ffd166;border-radius:4px;animation-duration:2.8s;animation-delay:0.28s;"></div>
<div class="cc{_cbust_end}" style="left:35%; width:18px;height:18px;background:#06d6a0;border-radius:4px;animation-duration:3.1s;animation-delay:0.02s;"></div>
<div class="cc{_cbust_end}" style="left:40%; width:26px;height:16px;background:#ff7b9c;border-radius:50%;animation-duration:2.6s;animation-delay:0.17s;"></div>
<div class="cc{_cbust_end}" style="left:45%; width:16px;height:26px;background:#4ea8de;border-radius:4px;animation-duration:3.4s;animation-delay:0.11s;"></div>
<div class="cc{_cbust_end}" style="left:50%; width:20px;height:20px;background:#ffd166;border-radius:50%;animation-duration:2.9s;animation-delay:0.25s;"></div>
<div class="cc{_cbust_end}" style="left:55%; width:24px;height:18px;background:#06d6a0;border-radius:4px;animation-duration:2.7s;animation-delay:0.06s;"></div>
<div class="cc{_cbust_end}" style="left:60%; width:18px;height:24px;background:#ff7b9c;border-radius:50%;animation-duration:3.2s;animation-delay:0.20s;"></div>
<div class="cc{_cbust_end}" style="left:65%; width:22px;height:22px;background:#4ea8de;border-radius:4px;animation-duration:2.8s;animation-delay:0.13s;"></div>
<div class="cc{_cbust_end}" style="left:70%; width:26px;height:20px;background:#ffd166;border-radius:4px;animation-duration:3.0s;animation-delay:0.24s;"></div>
<div class="cc{_cbust_end}" style="left:75%; width:20px;height:26px;background:#06d6a0;border-radius:50%;animation-duration:2.7s;animation-delay:0.09s;"></div>
<div class="cc{_cbust_end}" style="left:80%; width:24px;height:16px;background:#ff7b9c;border-radius:4px;animation-duration:3.3s;animation-delay:0.30s;"></div>
<div class="cc{_cbust_end}" style="left:85%; width:18px;height:22px;background:#4ea8de;border-radius:50%;animation-duration:2.8s;animation-delay:0.12s;"></div>
<div class="cc{_cbust_end}" style="left:90%; width:22px;height:20px;background:#ffd166;border-radius:4px;animation-duration:3.1s;animation-delay:0.19s;"></div>
<div class="cc{_cbust_end}" style="left:95%; width:26px;height:18px;background:#06d6a0;border-radius:50%;animation-duration:2.6s;animation-delay:0.03s;"></div>
""", unsafe_allow_html=True)

            finish_cols = st.columns([1.2, 1.6, 1.2], gap="small")
            with finish_cols[1]:
                st.markdown(
                    "<div class='quiz-feedback success' style='text-align:center;font-size:1.4rem;padding:20px;'>"
                    "🎉 Amazing! You completed all the puzzles!</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Play Again", use_container_width=True, key="student_play_again_end"):
                    st.session_state.pop("student_response", None)
                    st.session_state["student_current_index"] = 0
                    st.session_state["student_feedback"] = ""
                    st.session_state["student_options"] = {}
                    st.rerun()
        else:
            outer_cols = st.columns([1.2, 1.6, 1.2], gap="small")
            with outer_cols[1]:
                with st.container(border=True):
                    student_activity_label = st.selectbox(
                        "Choose Activity Type",
                        list(ACTIVITIES.keys()),
                        index=0,
                        key="student_activity_label",
                    )
                    student_difficulty = st.selectbox(
                        "Choose Difficulty",
                        DIFFICULTIES,
                        index=0,
                        key="student_difficulty",
                    )

                    if st.button("Select", use_container_width=True, key="student_select"):
                        _start_student_game(student_activity_label, student_difficulty)

    else:
        current_index = int(st.session_state.get("student_current_index", 0))
        puzzle = payloads[current_index]

        st.markdown(f"<div style='font-family:Fredoka,sans-serif;font-size:1.7rem;font-weight:700;color:#2e294e;margin-bottom:0.4rem;'>Puzzle {current_index + 1} of {len(payloads)}</div>", unsafe_allow_html=True)

        feedback = st.session_state.get("student_feedback", "")
        _sfx_uid = st.session_state.get("student_current_index", 0) * 10 + (1 if feedback == "correct" else 2)
        if feedback == "wrong":
            _play_sound("wrong.mp3")
            st.markdown("<div class='quiz-feedback error'>Oh no, that's not right. Try again!</div>", unsafe_allow_html=True)
        elif feedback == "correct":
            _play_sound("correct.mp3")
            st.markdown("<div class='quiz-feedback success'>Correct! Well done.</div>", unsafe_allow_html=True)
            # Unique id per puzzle so React re-mounts the animation every correct answer
            _cbust = current_index
            st.markdown(f"""
<style>
@keyframes confetti-drop-{_cbust} {{
    0%   {{ transform: translateY(-50px) rotate(0deg) scale(1);     opacity: 1; }}
    80%  {{ opacity: 1; }}
    100% {{ transform: translateY(110vh) rotate(1080deg) scale(0.6); opacity: 0; }}
}}
.cc{_cbust} {{ position:fixed; top:-50px; z-index:99999; pointer-events:none; animation: confetti-drop-{_cbust} linear forwards; }}
</style>
<div class="cc{_cbust}" style="left:1%;  width:22px;height:22px;background:#ff7b9c;border-radius:4px;animation-duration:3.2s;animation-delay:0.00s;"></div>
<div class="cc{_cbust}" style="left:4%;  width:18px;height:26px;background:#4ea8de;border-radius:50%;animation-duration:2.8s;animation-delay:0.08s;"></div>
<div class="cc{_cbust}" style="left:7%;  width:24px;height:16px;background:#ffd166;border-radius:4px;animation-duration:3.5s;animation-delay:0.15s;"></div>
<div class="cc{_cbust}" style="left:10%; width:16px;height:24px;background:#06d6a0;border-radius:50%;animation-duration:2.9s;animation-delay:0.04s;"></div>
<div class="cc{_cbust}" style="left:13%; width:26px;height:18px;background:#ff7b9c;border-radius:4px;animation-duration:2.7s;animation-delay:0.22s;"></div>
<div class="cc{_cbust}" style="left:16%; width:20px;height:20px;background:#4ea8de;border-radius:50%;animation-duration:3.3s;animation-delay:0.10s;"></div>
<div class="cc{_cbust}" style="left:19%; width:22px;height:24px;background:#ffd166;border-radius:4px;animation-duration:2.8s;animation-delay:0.28s;"></div>
<div class="cc{_cbust}" style="left:22%; width:18px;height:18px;background:#06d6a0;border-radius:4px;animation-duration:3.1s;animation-delay:0.02s;"></div>
<div class="cc{_cbust}" style="left:25%; width:26px;height:16px;background:#ff7b9c;border-radius:50%;animation-duration:2.6s;animation-delay:0.17s;"></div>
<div class="cc{_cbust}" style="left:28%; width:16px;height:26px;background:#4ea8de;border-radius:4px;animation-duration:3.4s;animation-delay:0.11s;"></div>
<div class="cc{_cbust}" style="left:31%; width:20px;height:20px;background:#ffd166;border-radius:50%;animation-duration:2.9s;animation-delay:0.25s;"></div>
<div class="cc{_cbust}" style="left:34%; width:24px;height:18px;background:#06d6a0;border-radius:4px;animation-duration:2.7s;animation-delay:0.06s;"></div>
<div class="cc{_cbust}" style="left:37%; width:18px;height:24px;background:#ff7b9c;border-radius:50%;animation-duration:3.2s;animation-delay:0.20s;"></div>
<div class="cc{_cbust}" style="left:40%; width:22px;height:22px;background:#4ea8de;border-radius:4px;animation-duration:2.8s;animation-delay:0.13s;"></div>
<div class="cc{_cbust}" style="left:43%; width:16px;height:18px;background:#ffd166;border-radius:50%;animation-duration:3.5s;animation-delay:0.01s;"></div>
<div class="cc{_cbust}" style="left:46%; width:26px;height:20px;background:#06d6a0;border-radius:4px;animation-duration:3.0s;animation-delay:0.24s;"></div>
<div class="cc{_cbust}" style="left:49%; width:20px;height:26px;background:#ff7b9c;border-radius:50%;animation-duration:2.7s;animation-delay:0.09s;"></div>
<div class="cc{_cbust}" style="left:52%; width:24px;height:16px;background:#4ea8de;border-radius:4px;animation-duration:3.3s;animation-delay:0.30s;"></div>
<div class="cc{_cbust}" style="left:55%; width:18px;height:22px;background:#ffd166;border-radius:50%;animation-duration:2.8s;animation-delay:0.12s;"></div>
<div class="cc{_cbust}" style="left:58%; width:22px;height:20px;background:#06d6a0;border-radius:4px;animation-duration:3.1s;animation-delay:0.19s;"></div>
<div class="cc{_cbust}" style="left:61%; width:26px;height:18px;background:#ff7b9c;border-radius:50%;animation-duration:2.6s;animation-delay:0.03s;"></div>
<div class="cc{_cbust}" style="left:64%; width:16px;height:26px;background:#4ea8de;border-radius:4px;animation-duration:3.4s;animation-delay:0.26s;"></div>
<div class="cc{_cbust}" style="left:67%; width:22px;height:18px;background:#ffd166;border-radius:50%;animation-duration:2.9s;animation-delay:0.14s;"></div>
<div class="cc{_cbust}" style="left:70%; width:18px;height:22px;background:#06d6a0;border-radius:4px;animation-duration:2.7s;animation-delay:0.21s;"></div>
<div class="cc{_cbust}" style="left:73%; width:24px;height:20px;background:#ff7b9c;border-radius:4px;animation-duration:3.2s;animation-delay:0.05s;"></div>
<div class="cc{_cbust}" style="left:76%; width:18px;height:18px;background:#4ea8de;border-radius:50%;animation-duration:3.0s;animation-delay:0.16s;"></div>
<div class="cc{_cbust}" style="left:79%; width:26px;height:16px;background:#ffd166;border-radius:4px;animation-duration:2.8s;animation-delay:0.00s;"></div>
<div class="cc{_cbust}" style="left:82%; width:16px;height:26px;background:#06d6a0;border-radius:50%;animation-duration:2.9s;animation-delay:0.29s;"></div>
<div class="cc{_cbust}" style="left:85%; width:22px;height:22px;background:#ff7b9c;border-radius:4px;animation-duration:3.3s;animation-delay:0.11s;"></div>
<div class="cc{_cbust}" style="left:88%; width:20px;height:16px;background:#4ea8de;border-radius:50%;animation-duration:2.7s;animation-delay:0.23s;"></div>
<div class="cc{_cbust}" style="left:91%; width:24px;height:24px;background:#ffd166;border-radius:4px;animation-duration:3.1s;animation-delay:0.07s;"></div>
<div class="cc{_cbust}" style="left:94%; width:18px;height:20px;background:#06d6a0;border-radius:50%;animation-duration:2.8s;animation-delay:0.18s;"></div>
<div class="cc{_cbust}" style="left:97%; width:20px;height:18px;background:#ff7b9c;border-radius:4px;animation-duration:3.5s;animation-delay:0.13s;"></div>
<div class="cc{_cbust}" style="left:3%;  width:16px;height:20px;background:#ffd166;border-radius:50%;animation-duration:3.0s;animation-delay:0.31s;"></div>
<div class="cc{_cbust}" style="left:15%; width:24px;height:16px;background:#4ea8de;border-radius:4px;animation-duration:2.9s;animation-delay:0.16s;"></div>
<div class="cc{_cbust}" style="left:33%; width:18px;height:24px;background:#ff7b9c;border-radius:50%;animation-duration:3.2s;animation-delay:0.09s;"></div>
<div class="cc{_cbust}" style="left:51%; width:22px;height:18px;background:#06d6a0;border-radius:4px;animation-duration:2.7s;animation-delay:0.27s;"></div>
<div class="cc{_cbust}" style="left:69%; width:16px;height:22px;background:#ffd166;border-radius:50%;animation-duration:3.3s;animation-delay:0.05s;"></div>
<div class="cc{_cbust}" style="left:87%; width:26px;height:20px;background:#4ea8de;border-radius:4px;animation-duration:2.8s;animation-delay:0.22s;"></div>
<div class="cc{_cbust}" style="left:44%; width:20px;height:22px;background:#ff7b9c;border-radius:50%;animation-duration:3.0s;animation-delay:0.14s;"></div>
<div class="cc{_cbust}" style="left:57%; width:18px;height:16px;background:#06d6a0;border-radius:4px;animation-duration:2.6s;animation-delay:0.20s;"></div>
""", unsafe_allow_html=True)

        # ── Pattern game ──────────────────────────────────────────────
        if activity == "pattern":
            image_path = None
            if isinstance(puzzle, dict):
                candidate = puzzle.get("__image_path")
                if isinstance(candidate, str) and candidate and Path(candidate).exists():
                    image_path = candidate

            if image_path:
                st.image(image_path, use_container_width=True)
            else:
                fallback_png = response.get("png_path") if isinstance(response, dict) else None
                if fallback_png and Path(fallback_png).exists():
                    st.image(fallback_png, use_container_width=True)
                else:
                    st.warning("Puzzle image not available.")

            sequence = puzzle.get("sequence") if isinstance(puzzle, dict) else []
            if not isinstance(sequence, list):
                sequence = []
            option_card_images = _extract_pattern_token_cards(image_path, tuple(sequence)) if image_path else {}

            all_tokens = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                candidate_correct = payload.get("correct_answer")
                if isinstance(candidate_correct, str):
                    token = candidate_correct.strip()
                    if token and token not in all_tokens:
                        all_tokens.append(token)
                seq = payload.get("sequence")
                if isinstance(seq, list):
                    for item in seq:
                        if isinstance(item, str):
                            token = item.strip()
                            if token and token != "?" and token not in all_tokens:
                                all_tokens.append(token)

            options_by_index = st.session_state.get("student_options", {})
            if current_index not in options_by_index:
                options_by_index[current_index] = _build_student_pattern_choices(puzzle, all_tokens)
                st.session_state["student_options"] = options_by_index
            options = options_by_index.get(current_index, [])

            if not options:
                st.warning("Could not build answer options for this puzzle.")
            else:
                st.markdown("<div class='student-answer-prompt'>Please choose the correct option:</div>", unsafe_allow_html=True)

                option_count = len(options)
                if option_count == 2:
                    option_cols = st.columns([1.3, 1, 1, 1.3], gap="small")
                    active_cols = option_cols[1:3]
                else:
                    option_cols = st.columns([1.2, 1, 1, 1, 1.2], gap="small")
                    active_cols = option_cols[1:4]

                correct_answer = str(puzzle.get("correct_answer", "")).strip() if isinstance(puzzle, dict) else ""
                for idx, option in enumerate(options):
                    with active_cols[idx]:
                        option_inner_cols = st.columns([1, 3, 1], gap="small")
                        with option_inner_cols[1]:
                            token_key = option.strip().lower()
                            card_bytes = option_card_images.get(token_key)
                            if card_bytes:
                                st.image(card_bytes, width=170)
                            else:
                                icon_bytes = _get_option_icon_bytes(option)
                                if icon_bytes:
                                    try:
                                        st.image(icon_bytes, width=130)
                                    except Exception:
                                        fallback_emoji = _get_option_emoji(option)
                                        if fallback_emoji:
                                            st.markdown(f"<div class='option-emoji'>{fallback_emoji}</div>", unsafe_allow_html=True)
                                        else:
                                            st.markdown("<div style='height:100px'></div>", unsafe_allow_html=True)
                                else:
                                    fallback_emoji = _get_option_emoji(option)
                                    if fallback_emoji:
                                        st.markdown(f"<div class='option-emoji'>{fallback_emoji}</div>", unsafe_allow_html=True)
                                    else:
                                        st.markdown("<div style='height:100px'></div>", unsafe_allow_html=True)

                            if st.button("Choose", key=f"student_option_{current_index}_{idx}", type="primary", use_container_width=False):
                                if option == correct_answer:
                                    st.session_state["student_feedback"] = "correct"
                                    st.session_state["student_current_index"] = current_index + 1
                                else:
                                    st.session_state["student_feedback"] = "wrong"
                                st.rerun()

        # ── Logic game ───────────────────────────────────────────────────
        elif activity == "logic":
            grid_colors = puzzle.get("grid_colors", []) if isinstance(puzzle, dict) else []
            diff_index = puzzle.get("diff_index", -1) if isinstance(puzzle, dict) else -1
            diff_color = str(puzzle.get("diff_color", "")).strip() if isinstance(puzzle, dict) else ""

            if not grid_colors or diff_index < 0 or not diff_color:
                st.warning("Puzzle data missing.")
            else:
                n = len(grid_colors)
                grid_size = 2 if n <= 4 else 3
                modified_colors = list(grid_colors)
                if 0 <= diff_index < n:
                    modified_colors[diff_index] = diff_color

                st.markdown("<div class='student-answer-prompt'>Spot the difference! Tap the square that is <b>DIFFERENT</b> in the right grid! 👀</div>", unsafe_allow_html=True)

                left_col, right_col = st.columns(2, gap="large")

                # Left: static original grid rendered as HTML colored squares
                with left_col:
                    st.markdown("<div style='font-family:Fredoka,sans-serif;font-weight:700;font-size:1.05rem;text-align:center;margin-bottom:6px;color:#2e294e;'>Original</div>", unsafe_allow_html=True)
                    cell_px = 150 if grid_size == 3 else 180
                    gap_px = 10
                    html = (
                        f"<div style='display:grid;grid-template-columns:repeat({grid_size},{cell_px}px);"
                        f"gap:{gap_px}px;margin:auto;width:fit-content;'>"
                    )
                    for color in grid_colors:
                        html += f"<div style='background:{color};width:{cell_px}px;height:{cell_px}px;border-radius:14px;border:3px solid #2e294e;'></div>"
                    html += "</div>"
                    st.markdown(html, unsafe_allow_html=True)

                # Right: padding-bottom trick makes each cell a true square that fills column width
                with right_col:
                    st.markdown("<div style='font-family:Fredoka,sans-serif;font-weight:700;font-size:1.2rem;text-align:center;margin-bottom:6px;color:#ff7b9c;'>Find the different one!</div>", unsafe_allow_html=True)
                    max_sq = 150 if grid_size == 3 else 180
                    for row in range(grid_size):
                        row_cols = st.columns(grid_size, gap="small")
                        for col in range(grid_size):
                            cell_idx = row * grid_size + col
                            if cell_idx >= n:
                                break
                            color = modified_colors[cell_idx]
                            with row_cols[col]:
                                st.markdown(
                                    f"<div style='max-width:{max_sq}px;margin:0 auto 4px auto;'>"
                                    f"<div style='position:relative;width:100%;padding-bottom:100%;'>"
                                    f"<div style='position:absolute;top:0;left:0;right:0;bottom:0;background:{color};"
                                    f"border-radius:14px;border:3px solid #2e294e;'></div></div></div>",
                                    unsafe_allow_html=True,
                                )
                                if st.button("Tap!", key=f"logic_tap_{current_index}_{cell_idx}", type="primary", use_container_width=True):
                                    if cell_idx == diff_index:
                                        st.session_state["student_feedback"] = "correct"
                                        st.session_state["student_current_index"] = current_index + 1
                                    else:
                                        st.session_state["student_feedback"] = "wrong"
                                    st.rerun()

        # ── Sequencing game ───────────────────────────────────────────
        elif activity == "sequencing":
            jumbled = puzzle.get("jumbled_sequence", []) if isinstance(puzzle, dict) else []
            n = len(jumbled)

            correct_click_order = sorted(range(n), key=lambda i: jumbled[i].get("size_rating", 0))

            clicks_key = f"seq_clicks_{current_index}"
            if clicks_key not in st.session_state:
                st.session_state[clicks_key] = []
            clicks = st.session_state[clicks_key]

            seq_image_path = puzzle.get("__image_path") if isinstance(puzzle, dict) else None
            if isinstance(seq_image_path, str) and seq_image_path and not Path(seq_image_path).exists():
                seq_image_path = None
            card_images = _extract_sequencing_item_cards(seq_image_path, n) if seq_image_path else []

            st.markdown("<div class='student-answer-prompt'>Tap the items from <b>SMALLEST</b> to <b>BIGGEST</b>! 🐾</div>", unsafe_allow_html=True)

            # Side spacers center the card group; active_cols are still page-level (1 nesting level)
            if n == 2:
                all_cols = st.columns([1.5, 1, 1, 1.5], gap="small")
                active_cols = all_cols[1:3]
            elif n == 3:
                all_cols = st.columns([1.2, 1, 1, 1, 1.2], gap="small")
                active_cols = all_cols[1:4]
            else:
                active_cols = st.columns(n, gap="small")

            for i, item in enumerate(jumbled):
                label = item.get("label", "")
                emoji = item.get("emoji", "❓")
                already_clicked = i in clicks
                tap_order = clicks.index(i) + 1 if already_clicked else None
                card_img = card_images[i] if i < len(card_images) else None

                with active_cols[i]:
                    inner = st.columns([1, 3, 1], gap="small")[1]
                    with inner:
                        if already_clicked:
                            if card_img:
                                st.image(card_img, width=160)
                            else:
                                st.markdown(
                                    f"<div style='text-align:center;font-size:3rem;opacity:0.38;'>{emoji}</div>"
                                    f"<div style='text-align:center;font-size:0.85rem;font-weight:700;color:#aaa;'>{label}</div>",
                                    unsafe_allow_html=True,
                                )
                            st.markdown(
                                f"<div style='text-align:center;font-size:1.1rem;font-weight:800;color:#06D6A0;'>#{tap_order}</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            if card_img:
                                st.image(card_img, width=160)
                            else:
                                st.markdown(
                                    f"<div style='text-align:center;font-size:3.4rem;'>{emoji}</div>"
                                    f"<div style='text-align:center;font-size:0.9rem;font-weight:700;color:#2E294E;margin-bottom:6px;'>{label}</div>",
                                    unsafe_allow_html=True,
                                )
                            if st.button("Tap!", key=f"seq_tap_{current_index}_{i}", type="primary", use_container_width=False):
                                clicks.append(i)
                                st.session_state[clicks_key] = clicks
                                if len(clicks) == n:
                                    if clicks == correct_click_order:
                                        st.session_state["student_feedback"] = "correct"
                                        st.session_state["student_current_index"] = current_index + 1
                                        st.session_state.pop(clicks_key, None)
                                    else:
                                        st.session_state["student_feedback"] = "wrong"
                                        st.session_state[clicks_key] = []
                                else:
                                    st.session_state["student_feedback"] = ""
                                st.rerun()
