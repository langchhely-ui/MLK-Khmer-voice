"""កម្មវិធីបម្លែងអត្ថបទភាសាខ្មែរទៅជាសំឡេង MP3។"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts
import streamlit as st


APP_TITLE = "ខ្មែរ អត្ថបទទៅសំឡេង"
MAX_CHARACTERS = 80_000
MAX_CHUNK_SIZE = 2_300
SUPPORTED_TYPES = [
    "txt",
    "srt",
    "vtt",
    "md",
    "csv",
    "rtf",
    "docx",
    "pdf",
]
VOICES = {
    "ស្រី — Sreymom": "km-KH-SreymomNeural",
    "ប្រុស — Piseth": "km-KH-PisethNeural",
}
PROJECT_DIR = Path(__file__).resolve().parent
RVC_RUNTIME_PYTHON = PROJECT_DIR / ".rvc-runtime" / "Scripts" / "python.exe"
RVC_BRIDGE = PROJECT_DIR / "rvc_bridge.py"
RVC_ASSET_DIR = PROJECT_DIR / "rvc_assets"
# Keep the resource-heavy local voice-conversion models off the hosted app.
# On this PC the default remains enabled; a hosting provider can set
# ENABLE_RVC=0 to expose only Khmer text-to-speech.
ENABLE_RVC = os.environ.get("ENABLE_RVC", "1").strip().lower() not in {"0", "false", "no", "off"}
RVC_MODELS = {
    "ដូណាស់ត្រាំ — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "ដូណាស់ត្រាំ_male.pth",
    "បារ៉ាក់អូបាម៉ា — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "បារ៉ាក់អូបាម៉ា_male.pth",
    "បូណា — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "បូណា_male.pth",
    "ផានិត — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "ផានិត_male.pth",
    "មាស សាម៉ន — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "មាស សាម៉ន_male.pth",
    "ម៉ូនីកា — ស្រី (RVC)": PROJECT_DIR / ".pth file Model" / "ម៉ូនីកា_female.pth",
    "រតន — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "រតន_male.pth",
    "ហេង — ប្រុស (RVC)": PROJECT_DIR / ".pth file Model" / "ហេង_male.pth",
}
NARRATION_STYLES = {
    "កក់ក្ដៅ និងទន់ភ្លន់": {
        "voice": "ស្រី — Sreymom",
        "rate": -14,
        "pitch": -2,
        "description": "សមស្របសម្រាប់រឿងគ្រួសារ កុមារ និងសាច់រឿងមានអារម្មណ៍។",
    },
    "ផ្សងព្រេង និងរំភើប": {
        "voice": "ប្រុស — Piseth",
        "rate": -3,
        "pitch": 3,
        "description": "សមស្របសម្រាប់រឿងដំណើរ សកម្មភាព និងឈុតរំភើប។",
    },
    "អាថ៌កំបាំង និងស្ងប់ស្ងាត់": {
        "voice": "ប្រុស — Piseth",
        "rate": -18,
        "pitch": -5,
        "description": "សមស្របសម្រាប់រឿងភ័យរន្ធត់ អាថ៌កំបាំង និងការពិពណ៌នា។",
    },
    "ឯកសារ និងមានវិជ្ជាជីវៈ": {
        "voice": "ស្រី — Sreymom",
        "rate": -5,
        "pitch": 0,
        "description": "សមស្របសម្រាប់វីដេអូពន្យល់ ប្រវត្តិសាស្ត្រ និងឯកសារ។",
    },
    "សម្រាក និងមុនចូលគេង": {
        "voice": "ស្រី — Sreymom",
        "rate": -22,
        "pitch": -4,
        "description": "អានយឺត ទន់ និងស្រួលស្តាប់សម្រាប់រឿងមុនចូលគេង។",
    },
}


def decode_text(raw: bytes) -> str:
    """Decode common user-uploaded text files without making users choose an encoding."""
    for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def remove_subtitle_metadata(text: str, extension: str) -> str:
    """Keep the spoken dialogue from SRT/VTT files and remove subtitles metadata."""
    if extension not in {"srt", "vtt"}:
        return text

    cleaned_lines: list[str] = []
    timestamp = re.compile(
        r"^\s*(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s*-->\s*(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}"
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper().startswith("WEBVTT"):
            continue
        if timestamp.match(stripped) or stripped.isdigit() or stripped.startswith(("NOTE", "STYLE", "REGION")):
            continue
        # Preserve dialogue but remove subtitle/HTML styling tags.
        cleaned_lines.append(re.sub(r"<[^>]+>", "", stripped))
    return "\n".join(cleaned_lines)


def remove_rtf_markup(text: str) -> str:
    """A lightweight RTF fallback for ordinary text-only RTF documents."""
    text = re.sub(r"\\par[d]?", "\n", text)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    return re.sub(r"[{}]", "", text)


def extract_file_text(uploaded_file) -> str:
    extension = Path(uploaded_file.name).suffix.lower().lstrip(".")
    raw = uploaded_file.getvalue()

    if extension == "docx":
        try:
            from docx import Document
        except ImportError as error:
            raise ValueError("ត្រូវដំឡើង python-docx សិន ដើម្បីអានឯកសារ DOCX។") from error
        document = Document(io.BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    if extension == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise ValueError("ត្រូវដំឡើង pypdf សិន ដើម្បីអានឯកសារ PDF។") from error
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    text = decode_text(raw)
    if extension == "csv":
        rows = csv.reader(io.StringIO(text))
        text = "\n".join("។ ".join(cell.strip() for cell in row if cell.strip()) for row in rows)
    elif extension == "rtf":
        text = remove_rtf_markup(text)
    return remove_subtitle_metadata(text, extension)


def normalise_text(text: str) -> str:
    text = text.replace("\u200b", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_for_speech(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split long text at Khmer/regular sentence boundaries for the TTS service."""
    sentences = re.split(r"(?<=[។.!?៖])\s+|\n+", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_size:
            words = re.split(r"\s+", sentence)
            for word in words:
                if len(current) + len(word) + 1 > max_size:
                    if current:
                        chunks.append(current)
                    current = word
                else:
                    current = f"{current} {word}".strip()
            continue
        if len(current) + len(sentence) + 1 > max_size:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


async def synthesize_chunk(text: str, voice: str, rate: str, pitch: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for message in communicate.stream():
        if message["type"] == "audio":
            audio.extend(message["data"])
    return bytes(audio)


def create_audio(text: str, voice: str, rate: str, pitch: str, progress_bar) -> bytes:
    chunks = split_for_speech(text)
    output = bytearray()
    for index, chunk in enumerate(chunks, start=1):
        output.extend(asyncio.run(synthesize_chunk(chunk, voice, rate, pitch)))
        progress_bar.progress(index / len(chunks), text=f"កំពុងបង្កើតសំឡេង… {index}/{len(chunks)}")
    return bytes(output)


def rvc_is_ready() -> bool:
    """Check dependencies without importing the heavy RVC runtime into Streamlit."""
    if not ENABLE_RVC:
        return False
    required_files = [
        RVC_RUNTIME_PYTHON,
        RVC_BRIDGE,
        RVC_ASSET_DIR / "hubert_base.pt",
        RVC_ASSET_DIR / "rmvpe.pt",
        *RVC_MODELS.values(),
    ]
    return all(path.is_file() for path in required_files)


def convert_to_character_voice(
    audio_bytes: bytes,
    model_path: Path,
    progress_bar,
    pitch_method: str = "pm",
) -> bytes:
    """Send the generated MP3 through the isolated RVC runtime and return MP3."""
    if not rvc_is_ready():
        raise RuntimeError("RVC runtime ឬ model assets មិនទាន់រួចរាល់ទេ។")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("មិនរកឃើញ FFmpeg សម្រាប់បម្លែងសំឡេងទេ។")

    with tempfile.TemporaryDirectory(prefix="khmer-rvc-") as temp_dir:
        temporary_path = Path(temp_dir)
        source_mp3 = temporary_path / "source.mp3"
        converted_wav = temporary_path / "character.wav"
        converted_mp3 = temporary_path / "character.mp3"
        source_mp3.write_bytes(audio_bytes)

        conversion_label = "លឿន" if pitch_method == "pm" else "គុណភាពខ្ពស់"
        progress_bar.progress(
            0.18,
            text=f"កំពុងបម្លែងទៅជាសំឡេងតួអង្គ ({conversion_label})…",
        )
        rvc_result = subprocess.run(
            [
                str(RVC_RUNTIME_PYTHON),
                str(RVC_BRIDGE),
                "--input",
                str(source_mp3),
                "--output",
                str(converted_wav),
                "--model",
                str(model_path),
                "--hubert",
                str(RVC_ASSET_DIR / "hubert_base.pt"),
                "--rmvpe",
                str(RVC_ASSET_DIR / "rmvpe.pt"),
                "--pitch-method",
                pitch_method,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        if rvc_result.returncode != 0 or not converted_wav.is_file():
            details = rvc_result.stderr.strip() or rvc_result.stdout.strip()
            raise RuntimeError(details or "RVC មិនអាចបម្លែងសំឡេងបានទេ។")

        progress_bar.progress(0.9, text="កំពុងរៀបចំ MP3 ចុងក្រោយ…")
        ffmpeg_result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(converted_wav),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(converted_mp3),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if ffmpeg_result.returncode != 0 or not converted_mp3.is_file():
            raise RuntimeError(ffmpeg_result.stderr.strip() or "មិនអាចបង្កើត MP3 ចុងក្រោយបានទេ។")
        return converted_mp3.read_bytes()


def render_text_source(state_key: str, height: int = 330) -> str:
    """Show the shared text/file input without cross-contaminating the two pages."""
    if state_key not in st.session_state:
        st.session_state[state_key] = ""

    uploaded_file = st.file_uploader(
        "អាប់ឡូដឯកសារ",
        type=SUPPORTED_TYPES,
        key=f"{state_key}_upload",
        help="គាំទ្រ TXT, SRT, VTT, MD, CSV, RTF, DOCX និង PDF។ សម្រាប់ SRT/VTT កម្មវិធីនឹងអានតែប្រយោគ។",
    )
    if uploaded_file is not None:
        try:
            file_id = f"{uploaded_file.name}:{uploaded_file.size}"
            loaded_key = f"loaded_{state_key}_file_id"
            # Do not overwrite a user's manual edits on ordinary widget reruns.
            if st.session_state.get(loaded_key) != file_id:
                st.session_state[state_key] = normalise_text(extract_file_text(uploaded_file))
                st.session_state[loaded_key] = file_id
                st.success(f"បានអានឯកសារ៖ {uploaded_file.name}")
        except ValueError as error:
            st.error(str(error))

    text = st.text_area(
        "បញ្ចូល ឬកែសម្រួលអត្ថបទ",
        key=state_key,
        height=height,
        max_chars=MAX_CHARACTERS,
        placeholder="ឧទាហរណ៍៖ សួស្តី! នេះជាកម្មវិធីបម្លែងអក្សរទៅជាសំឡេងភាសាខ្មែរ។",
    )
    st.caption(f"{len(text):,}/{MAX_CHARACTERS:,} តួអក្សរ")
    return text


def generate_and_show_audio(
    text: str,
    voice: str,
    speed: int,
    pitch: int,
    filename: str,
    character_model: Path | None = None,
    character_pitch_method: str = "pm",
) -> None:
    ready_text = normalise_text(text)
    if not ready_text:
        st.warning("សូមបញ្ចូលអត្ថបទ ឬអាប់ឡូដឯកសារជាមុនសិន។")
        return

    progress = st.progress(0, text="កំពុងរៀបចំអត្ថបទ…")
    try:
        audio_bytes = create_audio(ready_text, voice, f"{speed:+d}%", f"{pitch:+d}Hz", progress)
        if character_model is not None:
            audio_bytes = convert_to_character_voice(
                audio_bytes,
                character_model,
                progress,
                character_pitch_method,
            )
    except Exception as error:  # Network/service errors should be clear to end users.
        progress.empty()
        st.error("មិនអាចបង្កើតសំឡេងបានទេ។ សូមពិនិត្យអ៊ីនធឺណិត រួចសាកល្បងម្ដងទៀត។")
        with st.expander("ព័ត៌មានបច្ចេកទេស"):
            st.code(str(error))
        return

    progress.empty()
    st.success("បង្កើតសំឡេងរួចរាល់!")
    st.audio(audio_bytes, format="audio/mpeg")
    st.download_button(
        "ទាញយកជា MP3",
        data=audio_bytes,
        file_name=filename,
        mime="audio/mpeg",
        use_container_width=True,
    )


def render_standard_page() -> None:
    st.markdown(
        """
        <section class="hero">
          <h1>🔊 ខ្មែរ អត្ថបទទៅសំឡេង</h1>
          <p>បម្លែងអត្ថបទ ឬឯកសាររបស់អ្នក ទៅជា MP3 អានជាភាសាខ្មែរ។</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.subheader("អត្ថបទ ឬឯកសារ")
        text = render_text_source("source_text")

    with right:
        st.subheader("ការកំណត់សំឡេង")
        voice_label = st.selectbox("ជ្រើសរើសសំឡេង", list(VOICES), key="standard_voice")
        speed = st.slider("ល្បឿនអាន", min_value=-40, max_value=40, value=0, step=5, format="%d%%", key="standard_speed")
        pitch = st.slider("កម្ពស់សំឡេង", min_value=-20, max_value=20, value=0, step=5, format="%d Hz", key="standard_pitch")
        st.markdown(
            """
            <div class="info-card">
              <strong>ឯកសារដែលអាចអានបាន</strong><br>
              TXT · SRT · VTT · MD · CSV · RTF · DOCX · PDF<br><br>
              កម្មវិធីត្រូវការអ៊ីនធឺណិតនៅពេលបម្លែង ដើម្បីប្រើសំឡេង AI ភាសាខ្មែរ។
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        generate = st.button("បង្កើត MP3", type="primary", use_container_width=True, key="standard_generate")

    if generate:
        generate_and_show_audio(text, VOICES[voice_label], speed, pitch, "khmer-speech.mp3")


def render_narration_page() -> None:
    st.markdown(
        """
        <section class="hero">
          <h1>🎙️ អ្នកនិទានរឿង</h1>
          <p>បង្កើតសំឡេងនិទានដែលមានចង្វាក់ និងអារម្មណ៍សមនឹងសាច់រឿង។</p>
        </section>
        <div class="story-card">
          <strong>គន្លឹះសំឡេងធម្មជាតិ</strong>៖ សរសេរអត្ថបទជាប្រយោគខ្លីៗ ហើយប្រើ «។», «!», «?» និងការបំបែកកថាខណ្ឌ ដើម្បីឲ្យ AI ផ្អាកតាមធម្មជាតិ។
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.subheader("សាច់រឿងរបស់អ្នក")
        story_text = render_text_source("narration_text", height=360)

    with right:
        st.subheader("រចនាប័ទ្មនិទាន")
        style_label = st.selectbox("ជ្រើសអារម្មណ៍សាច់រឿង", list(NARRATION_STYLES), key="narration_style")
        style = NARRATION_STYLES[style_label]
        st.markdown(f"<div class=\"info-card\">{style['description']}</div>", unsafe_allow_html=True)
        st.write("")
        default_voice = list(VOICES).index(style["voice"])
        voice_label = st.radio(
            "អ្នកនិទាន",
            list(VOICES),
            index=default_voice,
            horizontal=True,
            key=f"narration_voice_{style_label}",
        )
        speed = st.slider(
            "ចង្វាក់និទាន",
            min_value=-40,
            max_value=20,
            value=style["rate"],
            step=1,
            format="%d%%",
            key=f"narration_speed_{style_label}",
        )
        pitch = st.slider(
            "ទឹកដមសំឡេង",
            min_value=-20,
            max_value=20,
            value=style["pitch"],
            step=1,
            format="%d Hz",
            key=f"narration_pitch_{style_label}",
        )
        st.caption("សំឡេង AI neural នឹងអានតាមសញ្ញាវណ្ណយុត្តិ និងល្បឿនដែលអ្នកកំណត់។")
        character_model = None
        character_pitch_method = "pm"
        if ENABLE_RVC and rvc_is_ready():
            use_character_voice = st.checkbox(
                "បម្លែងជា​សំឡេងតួអង្គ",
                help="បង្កើត MP3 ជាមុន រួចបម្លែងវាទៅជាសំឡេង RVC។ វាអាចចំណាយពេលបន្តិចលើ CPU។",
            )
            if use_character_voice:
                character_label = st.selectbox("ជ្រើសសំឡេងតួអង្គ", list(RVC_MODELS))
                character_model = RVC_MODELS[character_label]
                rvc_mode = st.radio(
                    "ល្បឿនបម្លែង",
                    ["លឿន — សាកសមសម្រាប់ CPU", "គុណភាពខ្ពស់ — យឺតជាង"],
                    index=0,
                    help="របៀបលឿនប្រើ pitch detector ស្រាលជាង។ របៀបគុណភាពខ្ពស់ប្រើ RMVPE និងចំណាយពេលច្រើន។",
                    key="rvc_mode",
                )
                character_pitch_method = "pm" if rvc_mode.startswith("លឿន") else "rmvpe+"
                if len(story_text) > 2_000:
                    st.warning(
                        "អត្ថបទវែង៖ លើ CPU សូមប្រើ «លឿន» ឬបែងចែកអត្ថបទជា 1,000–2,000 តួអក្សរ ក្នុងមួយលើក។"
                    )
        elif ENABLE_RVC:
            st.info("កំពុងរៀបចំ RVC assets សម្រាប់សំឡេងតួអង្គ…")
        else:
            st.caption("កំណែអនឡាញនេះផ្ដល់តែសំឡេងនិទាន Khmer ដើម្បីឲ្យដំណើរការលឿន និងស្រាល។")
        generate = st.button("បង្កើតសំឡេងនិទាន", type="primary", use_container_width=True, key="narration_generate")

    if generate:
        filename = "khmer-character-narration.mp3" if character_model else "khmer-narration.mp3"
        generate_and_show_audio(
            story_text,
            VOICES[voice_label],
            speed,
            pitch,
            filename,
            character_model,
            character_pitch_method,
        )


def render_app() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🔊", layout="wide")
    st.markdown(
        """
        <style>
          :root { color-scheme: light; }
          .stApp { background: linear-gradient(135deg, #fffaf3 0%, #f5fbf7 100%); color: #17261d; }
          [data-testid="stHeader"] { background: transparent; }
          [data-testid="stSidebar"] { background: #eff8f0; }
          .hero { padding: 1.3rem 0 0.5rem; }
          .hero h1 { color: #163d2b !important; font-size: 2.25rem; margin-bottom: .2rem; }
          .hero p { color: #3d5849 !important; font-size: 1.05rem; }
          .info-card { background: #ffffff; border: 1px solid #b8d4bf; border-radius: 16px; color: #1d3829 !important; padding: 1rem 1.15rem; }
          .info-card * { color: #1d3829 !important; }
          .story-card { background: #e6f3e8; border-left: 5px solid #196a43; border-radius: 10px; color: #1d3829 !important; padding: .9rem 1.1rem; margin: .5rem 0 1.2rem; }
          [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #263e30 !important; }
          [data-testid="stRadio"] label, [data-testid="stRadio"] label span { color: #17261d !important; }
          [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 { color: #173523 !important; }
          .stButton button { background: #196a43; color: white; border: 0; border-radius: 10px; font-weight: 700; padding: .65rem 1.15rem; width: 100%; }
          .stButton button:hover { background: #115133; color: white; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("## មុខងារ")
    page = st.sidebar.radio("ជ្រើសទំព័រ", ["អានអត្ថបទ", "អ្នកនិទានរឿង"])
    st.sidebar.caption("សំឡេងនិទានប្រើ AI neural Khmer voice និងត្រូវការអ៊ីនធឺណិត។")

    if page == "អ្នកនិទានរឿង":
        render_narration_page()
    else:
        render_standard_page()


if __name__ == "__main__":
    render_app()
