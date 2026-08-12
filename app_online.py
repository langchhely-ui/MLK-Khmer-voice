"""Entrypoint for the lightweight hosted version of the Khmer TTS app.

RVC character models remain private to the desktop installation. Deploy this
file as the Streamlit entrypoint to expose only Khmer text-to-speech online.
"""

import os

os.environ["ENABLE_RVC"] = "0"

from app import render_app


render_app()
