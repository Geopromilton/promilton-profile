# PyInstaller recipe for LithoLog Studio (Windows, also works on Linux/macOS).
#   pyinstaller packaging/litholog_studio.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "litholog" / "data"), "litholog/data"), (str(ROOT / "litholog" / "fonts"), "litholog/fonts")]
datas += collect_data_files("qtawesome")          # icon fonts
datas += collect_data_files("pyvista")
datas += collect_data_files("pyproj")             # PROJ database for reprojection
datas += collect_data_files("skimage", includes=["**/*.py", "**/*.pyi"])
_SKIP = ("pyvista.examples", "pyvista.demos", "pyvista.jupyter", "pyvista.trame", "pyvista.ext",
         "pyvista.plotting.utilities.sphinx_gallery", "vtkmodules.web", "vtkmodules.test")
_keep = lambda n: not n.startswith(_SKIP)  # noqa: E731 - optional parts pull in networking/web stacks
hidden = (collect_submodules("vtkmodules", filter=_keep) + collect_submodules("pyvista", filter=_keep)
          + collect_submodules("pyvistaqt")
          + collect_submodules("skimage.measure") + ["shapefile", "scipy.spatial", "scipy.ndimage",
          "scipy.optimize", "openpyxl", "pyproj.database", "matplotlib.backends.backend_qtagg",
          "PySide6.QtSvg", "tifffile", "imagecodecs", "PIL.Image", "xml.etree.ElementTree"])

a = Analysis([str(ROOT / "packaging" / "studio_main.py")], pathex=[str(ROOT)], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "streamlit", "IPython", "jupyter", "pytest", "trame",
                                             "PyQt5", "PyQt6", "PySide2"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LithoLogStudio",
          icon=str(ROOT / "packaging" / "litholog.ico"), console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="LithoLogStudio", upx=False)
