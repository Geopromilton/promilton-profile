"""Entry point for Streamlit Community Cloud (and `streamlit run streamlit_app.py`)."""

import runpy
from pathlib import Path

# Run the app script afresh on every Streamlit rerun (importing it would run it only once).
runpy.run_path(str(Path(__file__).parent / "litholog" / "app.py"), run_name="__main__")
