"""LithoLog: open-source borehole logs, sections and aquifer models."""

__version__ = "0.1.0"

from .io import load_gms, load_legend, load_project, write_project, write_template  # noqa: E402
from .patterns import DEFAULT_LEGEND, Legend, LithType  # noqa: E402
from .project import Borehole, Project  # noqa: E402
from .striplog import Style, save_striplog, striplog_pages  # noqa: E402
from .validate import Issue, validate  # noqa: E402
from .typeface import use_in_matplotlib  # noqa: E402

use_in_matplotlib()

__all__ = [
    "Borehole", "DEFAULT_LEGEND", "Issue", "Legend", "LithType", "Project", "Style",
    "load_gms", "load_legend", "load_project", "write_project", "save_striplog", "striplog_pages", "validate", "write_template",
]
