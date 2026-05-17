# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata


PROJECT_ROOT = Path.cwd()
PADDLEX_DATAS = collect_data_files(
    "paddlex",
    includes=[
        ".version",
        "configs/**/*.yaml",
        "configs/**/*.yml",
    ],
)
OCR_CORE_METADATA = []
for dist_name in [
    "imagesize",
    "opencv-contrib-python",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
]:
    OCR_CORE_METADATA += copy_metadata(dist_name)
EXTRA_BINARIES = []
_mklml_path = PROJECT_ROOT / ".venv" / "Lib" / "site-packages" / "paddle" / "libs" / "mklml.dll"
if _mklml_path.exists():
    EXTRA_BINARIES.append((str(_mklml_path), "paddle/libs"))
QT_EXCLUDED_BASENAMES = {
    "Qt6Pdf.dll",
    "Qt6Qml.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6Quick.dll",
    "Qt6Svg.dll",
    "Qt6VirtualKeyboard.dll",
}
OPENCV_EXCLUDED_BASENAMES = {
    "opencv_videoio_ffmpeg4100_64.dll",
    "opencv_videoio_ffmpeg4120_64.dll",
}
QT_EXCLUDED_PREFIXES = {
    "PySide6/translations/",
}


def unique_entries(*tocs):
    seen = set()
    merged = []
    for toc in tocs:
        for entry in toc:
            key = tuple(entry)
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


def filter_entries(toc, excluded_basenames=None, excluded_prefixes=None):
    excluded_basenames = excluded_basenames or set()
    excluded_prefixes = excluded_prefixes or set()
    filtered = []
    for entry in toc:
        dest_name = str(entry[0]).replace("\\", "/")
        base_name = Path(dest_name).name
        if base_name in excluded_basenames:
            continue
        if any(dest_name.startswith(prefix) for prefix in excluded_prefixes):
            continue
        filtered.append(entry)
    return filtered


common_analysis_kwargs = dict(
    pathex=[str(PROJECT_ROOT)],
    binaries=EXTRA_BINARIES,
    datas=PADDLEX_DATAS + OCR_CORE_METADATA,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


manager = Analysis(["mainWindow.py"], **common_analysis_kwargs)
editor = Analysis(["csv_editor/__main__.py"], **common_analysis_kwargs)

manager.binaries = filter_entries(
    manager.binaries,
    QT_EXCLUDED_BASENAMES | OPENCV_EXCLUDED_BASENAMES,
    QT_EXCLUDED_PREFIXES,
)
manager.datas = filter_entries(manager.datas, excluded_prefixes=QT_EXCLUDED_PREFIXES)
editor.binaries = filter_entries(
    editor.binaries,
    QT_EXCLUDED_BASENAMES | OPENCV_EXCLUDED_BASENAMES,
    QT_EXCLUDED_PREFIXES,
)
editor.datas = filter_entries(editor.datas, excluded_prefixes=QT_EXCLUDED_PREFIXES)

manager_pyz = PYZ(manager.pure)
editor_pyz = PYZ(editor.pure)

manager_exe = EXE(
    manager_pyz,
    manager.scripts,
    [],
    exclude_binaries=True,
    name="CsvAutoGui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

editor_exe = EXE(
    editor_pyz,
    editor.scripts,
    [],
    exclude_binaries=True,
    name="CsvEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    manager_exe,
    editor_exe,
    unique_entries(manager.binaries, editor.binaries),
    unique_entries(manager.datas, editor.datas),
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CsvAutoGuiBundle",
)
