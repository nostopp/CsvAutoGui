import os
import sys
from pathlib import Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def logical_abs_path(path: str | os.PathLike, base_dir: str | os.PathLike | None = None) -> Path:
    raw_path = Path(path)
    if not raw_path.is_absolute() and base_dir is not None:
        raw_path = Path(base_dir) / raw_path
    return Path(os.path.abspath(os.path.normpath(os.fspath(raw_path))))


def default_config_root() -> Path:
    return logical_abs_path("config", application_root())


def normalize_config_root(config_root: str | os.PathLike | None = None) -> Path:
    if config_root is None:
        return default_config_root()
    return logical_abs_path(config_root)


def map_real_path_to_config_link(
    path: str | os.PathLike,
    config_root: str | os.PathLike | None = None,
) -> Path | None:
    root = normalize_config_root(config_root)
    candidate = logical_abs_path(path)
    if candidate.is_relative_to(root):
        return candidate

    try:
        candidate_real = candidate.resolve()
        for child in root.iterdir():
            if not child.is_dir():
                continue
            child_real = child.resolve()
            if candidate_real == child_real:
                return logical_abs_path(child)
            if candidate_real.is_relative_to(child_real):
                return logical_abs_path(child / candidate_real.relative_to(child_real))
    except OSError:
        return None

    return None


def normalize_config_dir(
    config_dir: str | os.PathLike,
    config_root: str | os.PathLike | None = None,
) -> Path:
    raw_path = Path(config_dir)
    cwd_candidate = logical_abs_path(raw_path)
    root = normalize_config_root(config_root)

    candidates: list[Path] = [cwd_candidate]
    if not raw_path.is_absolute():
        app_candidate = logical_abs_path(raw_path, application_root())
        if app_candidate != cwd_candidate:
            candidates.append(app_candidate)

    for candidate in candidates:
        mapped = map_real_path_to_config_link(candidate, root)
        if mapped is not None:
            return mapped

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return cwd_candidate


def display_config_path(
    config_dir: str | os.PathLike,
    display_root: str | os.PathLike | None = None,
    config_root: str | os.PathLike | None = None,
) -> str:
    root = logical_abs_path(display_root or application_root())
    config_path = normalize_config_dir(config_dir, config_root)
    try:
        return config_path.relative_to(root).as_posix()
    except ValueError:
        return config_path.as_posix()