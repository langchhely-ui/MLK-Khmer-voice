"""កម្មវិធីបម្លែងវីដេអូ និងសំឡេងទៅជាអក្សរ និង subtitle។"""

from __future__ import annotations

import io
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import streamlit as st


APP_TITLE = "បម្លែងវីដេអូទៅអក្សរ"
MEDIA_TYPES = [
    "mp4", "mov", "mkv", "avi", "webm", "m4v", "mp3", "wav", "m4a", "aac", "ogg", "flac",
]
LANGUAGES = {
    "ខ្មែរ": "km",
    "ស្វ័យប្រវត្តិ": None,
    "English": "en",
    "ไทย": "th",
    "Tiếng Việt": "vi",
    "中文": "zh",
    "日本語": "ja",
    "한국어": "ko",
    "Français": "fr",
}
MODEL_OPTIONS = {
    "លឿនបំផុត — Tiny": "tiny",
    "លឿន — Base": "base",
    "សមតុល្យ — Small (ណែនាំ)": "small",
    "គុណភាពខ្ពស់ — Medium": "medium",
    "ល្អបំផុត — Large v3": "large-v3",
}


def initialize_state() -> None:
    """Set per-session defaults in one place."""
    st.session_state.setdefault("transcription", None)
    st.session_state.setdefault("source_name", "transcript")
    st.session_state.setdefault("upload_reset_nonce", 0)


@st.cache_data(show_spinner=False)
def gpu_is_available() -> bool:
    """Show GPU processing only on a host where CTranslate2 can use CUDA."""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def clear_current_work() -> None:
    """Discard the selected media and any transcription from this session."""
    st.session_state.transcription = None
    st.session_state.source_name = "transcript"
    # A new widget key resets the uploader without mutating an existing widget.
    st.session_state.upload_reset_nonce += 1


@st.cache_resource(show_spinner=False)
def load_whisper_model(model_size: str, device: str, compute_type: str):
    """Load and share the selected local Whisper model across reruns."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "រកមិនឃើញ faster-whisper។ សូមរត់ `pip install -r requirements.txt` មុនសិន។"
        ) from error
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def format_timestamp(seconds: float, decimal_separator: str = ",") -> str:
    """Format seconds as a subtitle timestamp."""
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds_value:02}{decimal_separator}{milliseconds:03}"


def clean_caption_text(text: str) -> str:
    """Normalize spacing without removing source-language characters."""
    return re.sub(r"\s+", " ", text).strip()


def to_srt(segments: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}",
                    segment["text"],
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: list[dict[str, Any]]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        blocks.extend(
            [
                f"{format_timestamp(segment['start'], '.')} --> {format_timestamp(segment['end'], '.')}",
                segment["text"],
                "",
            ]
        )
    return "\n".join(blocks)


def to_timestamped_text(segments: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[{format_timestamp(segment['start'], '.')[:-4]}] {segment['text']}"
        for segment in segments
    )


def create_export_bundle(base_name: str, plain_text: str, srt_text: str, vtt_text: str) -> bytes:
    """Create one downloadable ZIP containing every supported export."""
    with io.BytesIO() as archive_buffer:
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{base_name}.txt", plain_text.encode("utf-8"))
            archive.writestr(f"{base_name}.srt", srt_text.encode("utf-8"))
            archive.writestr(f"{base_name}.str", srt_text.encode("utf-8"))
            archive.writestr(f"{base_name}.vtt", vtt_text.encode("utf-8"))
        return archive_buffer.getvalue()


def safe_base_name(filename: str) -> str:
    name = Path(filename).stem or "transcript"
    cleaned = re.sub(r"[^\w\-. ]", "_", name, flags=re.UNICODE).strip(" .")
    return cleaned or "transcript"


def save_uploaded_media(uploaded_file) -> Path:
    """Save uploaded bytes to an isolated temporary file for Whisper."""
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="transcribe_") as temporary_file:
        temporary_file.write(uploaded_file.getbuffer())
        return Path(temporary_file.name)


def transcribe_media(
    media_path: Path,
    model_size: str,
    language: str | None,
    device: str,
) -> tuple[list[dict[str, Any]], str, float]:
    """Run local transcription and return serializable subtitle data."""
    compute_type = "float16" if device == "cuda" else "int8"
    model = load_whisper_model(model_size, device, compute_type)
    started_at = time.perf_counter()
    segment_iterator, info = model.transcribe(
        str(media_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
    )
    segments = [
        {"start": float(segment.start), "end": float(segment.end), "text": clean_caption_text(segment.text)}
        for segment in segment_iterator
        if clean_caption_text(segment.text)
    ]
    elapsed = time.perf_counter() - started_at
    detected_language = getattr(info, "language", language) or "មិនស្គាល់"
    return segments, detected_language, elapsed


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=":material/subtitles:",
    layout="centered",
)
initialize_state()

st.title(f":material/subtitles: {APP_TITLE}")
st.caption("បញ្ចូលវីដេអូ ឬសំឡេង រួចបម្លែងជាអក្សរ និង subtitle ដែលអាចទាញយកបាន។")

with st.sidebar:
    st.header("ការកំណត់", divider=False)
    language_label = st.selectbox("ភាសានៃសំឡេង", list(LANGUAGES), key="language")
    model_label = st.selectbox("គុណភាពសំឡេង", list(MODEL_OPTIONS), index=2, key="model")
    if gpu_is_available():
        device_label = st.segmented_control(
            "ឧបករណ៍ដំណើរការ",
            options=["CPU", "GPU (NVIDIA)"],
            default="CPU",
            key="device",
        )
    else:
        device_label = "CPU"
        st.caption("Server នេះប្រើ CPU។ ជម្រើស GPU នឹងបង្ហាញដោយស្វ័យប្រវត្តិពេល CUDA មាន។")

with st.container(border=True):
    uploaded_file = st.file_uploader(
        "ជ្រើសវីដេអូ ឬឯកសារសំឡេង",
        type=MEDIA_TYPES,
        max_upload_size=2_048,
        help="គាំទ្រ MP4, MOV, MKV, MP3, WAV, M4A និងទម្រង់ពេញនិយមផ្សេងទៀត។",
        key=f"media_upload_{st.session_state.upload_reset_nonce}",
    )
    if uploaded_file:
        size_in_mb = uploaded_file.size / (1024 * 1024)
        st.caption(f"បានជ្រើស៖ {uploaded_file.name} · {size_in_mb:.1f} MB")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        start_transcription = st.button(
            "បម្លែងទៅអក្សរ",
            icon=":material/play_arrow:",
            type="primary",
            disabled=uploaded_file is None,
            key="start_transcription",
        )
        st.button(
            "បោះបង់",
            icon=":material/cancel:",
            on_click=clear_current_work,
            disabled=uploaded_file is None and st.session_state.transcription is None,
            key="cancel_transcription",
        )

if start_transcription and uploaded_file:
    temporary_path: Path | None = None
    device = "cuda" if device_label == "GPU (NVIDIA)" else "cpu"
    try:
        with st.status("កំពុងរៀបចំឯកសារ…", expanded=True) as progress_status:
            temporary_path = save_uploaded_media(uploaded_file)
            progress_status.write("កំពុងផ្ទុក Whisper model…")
            progress_status.update(label="កំពុងស្តាប់ និងបម្លែងសំឡេង…")
            segments, detected_language, elapsed = transcribe_media(
                temporary_path,
                MODEL_OPTIONS[model_label],
                LANGUAGES[language_label],
                device,
            )
            if not segments:
                raise ValueError("រកមិនឃើញសំឡេងដែលអាចបម្លែងបានក្នុងឯកសារនេះទេ។")
            st.session_state.transcription = {
                "segments": segments,
                "detected_language": detected_language,
                "elapsed": elapsed,
            }
            st.session_state.source_name = safe_base_name(uploaded_file.name)
            progress_status.update(label="បម្លែងរួចរាល់", state="complete", expanded=False)
    except Exception as error:
        st.session_state.transcription = None
        st.error(f"មិនអាចបម្លែងឯកសារបាន៖ {error}", icon=":material/error:")
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)

result = st.session_state.transcription
if result:
    segments = result["segments"]
    full_text = "\n".join(segment["text"] for segment in segments)
    srt_text = to_srt(segments)
    vtt_text = to_vtt(segments)
    timestamped_text = to_timestamped_text(segments)
    base_name = st.session_state.source_name

    st.success("អត្ថបទ និង subtitle របស់អ្នករួចរាល់ហើយ។", icon=":material/check_circle:")
    metric_one, metric_two = st.columns(2)
    metric_one.metric("ចំនួន subtitle", len(segments))
    metric_two.metric("ពេលវេលាបម្លែង", f"{result['elapsed']:.1f} វិនាទី")
    st.caption(f"ភាសាដែលស្គាល់៖ {result['detected_language']}")

    preview_tab, timestamp_tab = st.tabs(["អត្ថបទ", "អត្ថបទមានពេលវេលា"])
    with preview_tab:
        st.text_area("អត្ថបទដែលបានបម្លែង", full_text, height=280, key="transcript_preview")
    with timestamp_tab:
        st.text_area("អត្ថបទមានពេលវេលា", timestamped_text, height=280, key="timestamped_preview")

    st.subheader("ទាញយកឯកសារ", divider=False)
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        st.download_button(
            "TXT", data=full_text.encode("utf-8"), file_name=f"{base_name}.txt",
            mime="text/plain; charset=utf-8", icon=":material/description:", key="download_txt",
        )
        st.download_button(
            "SRT", data=srt_text.encode("utf-8"), file_name=f"{base_name}.srt",
            mime="application/x-subrip; charset=utf-8", icon=":material/subtitles:", key="download_srt",
        )
        st.download_button(
            "STR", data=srt_text.encode("utf-8"), file_name=f"{base_name}.str",
            mime="text/plain; charset=utf-8", icon=":material/subtitles:", key="download_str",
        )
        st.download_button(
            "VTT", data=vtt_text.encode("utf-8"), file_name=f"{base_name}.vtt",
            mime="text/vtt; charset=utf-8", icon=":material/closed_caption:", key="download_vtt",
        )
        st.download_button(
            "ZIP", data=create_export_bundle(base_name, full_text, srt_text, vtt_text),
            file_name=f"{base_name}_exports.zip", mime="application/zip",
            icon=":material/folder_zip:", key="download_zip",
        )

with st.expander("របៀបប្រើ និងចំណាំ", icon=":material/help:"):
    st.markdown(
        """
1. ជ្រើសភាសា និងកម្រិតគុណភាពនៅជ្រុងខាងឆ្វេង។
2. អាប់ឡូដវីដេអូ ឬសំឡេង ហើយចុច **បម្លែងទៅអក្សរ**។
3. ពិនិត្យអត្ថបទ រួចទាញយកជា TXT, SRT, STR, VTT ឬ ZIP។

កម្មវិធីប្រើ Whisper នៅលើកុំព្យូទ័ររបស់អ្នក។ លើកដំបូងនៃគំរូនីមួយៗ វានឹងទាញយក model ម្តង។ សម្រាប់វីដេអូវែង ឬសំឡេងភាសាខ្មែរ សូមប្រើ Small, Medium ឬ Large v3 ដើម្បីបានគុណភាពល្អជាង។
        """
    )
