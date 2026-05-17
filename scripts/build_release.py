from __future__ import annotations

import argparse
import shutil
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / ".build-release"
OUTPUT_ROOT = ROOT / "artifacts" / "release"
ARCHIVE_SUFFIX = ".7z"

PYPROJECTS = {
    "cpu": ROOT / "pyproject_cpu.toml",
    "gpu": ROOT / "pyproject_gpu.toml",
}

COPY_FILES = [
    "README.md",
    "main.py",
    "mainWindow.py",
    "csv_schema.py",
    "pyproject.toml",
    "pyproject_cpu.toml",
    "pyproject_gpu.toml",
    "uv.lock",
    "CsvAutoGuiBundle.spec",
]

COPY_DIRS = [
    "autogui",
    "csv_editor",
    "config",
]

EXPECTED_PACKAGE_FILES = [
    Path("CsvAutoGui.exe"),
    Path("CsvEditor.exe"),
    Path("README.md"),
    Path("config") / "template.csv",
    Path("config") / "example" / "main.csv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local release bundles for CsvAutoGui.")
    parser.add_argument(
        "--variant",
        choices=["cpu", "gpu", "all"],
        default="all",
        help="Which release variant to build.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
        help="Directory that receives unpacked bundles and 7z archives.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing output and working directories before building.",
    )
    parser.add_argument(
        "--archive-tool",
        type=Path,
        help="Optional path to the 7-Zip executable. Defaults to resolving `7z`, `7za`, or `7zr` from PATH.",
    )
    return parser.parse_args()


def read_version(path: Path) -> str:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data["project"]["version"]


def load_versions() -> tuple[str, dict[str, str]]:
    versions = {"default": read_version(ROOT / "pyproject.toml")}
    versions.update({name: read_version(path) for name, path in PYPROJECTS.items()})
    unique = set(versions.values())
    if len(unique) != 1:
        formatted = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise RuntimeError(f"Version mismatch across pyproject files: {formatted}")
    version = unique.pop()
    return version, versions


def copy_project_tree(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for file_name in COPY_FILES:
        source = ROOT / file_name
        shutil.copy2(source, destination / file_name)
    for dir_name in COPY_DIRS:
        source = ROOT / dir_name
        shutil.copytree(source, destination / dir_name)


def prepare_workspace(variant: str, clean: bool) -> Path:
    workspace = BUILD_ROOT / variant / "workspace"
    if clean or workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    copy_project_tree(workspace)
    shutil.copy2(workspace / f"pyproject_{variant}.toml", workspace / "pyproject.toml")
    return workspace


def run(cmd: list[str], cwd: Path) -> None:
    printable = " ".join(cmd)
    print(f"[run] {printable} (cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def resolve_7z(override: Path | None = None) -> str:
    if override is not None:
        candidate = override.expanduser().resolve()
        if not candidate.exists():
            raise RuntimeError(f"Configured 7-Zip executable does not exist: {candidate}")
        return str(candidate)

    for candidate in (shutil.which("7z"), shutil.which("7za"), shutil.which("7zr")):
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError(
        "Missing 7-Zip executable. Install 7-Zip and ensure `7z` is available in PATH, "
        "or pass `--archive-tool`."
    )


def compress_runtime(release_dir: Path) -> None:
    internal_dir = release_dir / "_internal"
    if not internal_dir.exists():
        raise RuntimeError(f"Missing packaged runtime directory: {internal_dir}")
    run(
        [
            "compact.exe",
            "/c",
            f"/s:{internal_dir}",
            "/a",
            "/i",
            "/f",
            "/exe:lzx",
        ],
        cwd=release_dir,
    )


def write_7z(source_dir: Path, archive_path: Path, archive_tool: Path | None) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    seven_zip = resolve_7z(archive_tool)
    run(
        [
            seven_zip,
            "a",
            "-t7z",
            str(archive_path),
            str(source_dir.name),
            "-xr!ocr_model",
            "-mx=9",
            "-m0=lzma2",
            "-ms=on",
            "-mmt=on",
        ],
        cwd=source_dir.parent,
    )


def build_variant(
    variant: str,
    version_tag: str,
    output_root: Path,
    clean: bool,
    archive_tool: Path | None,
) -> tuple[Path, Path]:
    workspace = prepare_workspace(variant, clean=clean)
    run(["uv", "sync", "--group", "build"], cwd=workspace)
    run(["uv", "run", "pyinstaller", "--noconfirm", "--clean", "CsvAutoGuiBundle.spec"], cwd=workspace)

    bundle_dir = workspace / "dist" / "CsvAutoGuiBundle"
    if not bundle_dir.exists():
        raise RuntimeError(f"Missing PyInstaller output: {bundle_dir}")

    release_name = f"CsvAutoGui-{version_tag}-{variant}"
    release_dir = output_root / release_name
    archive_path = output_root / f"{release_name}{ARCHIVE_SUFFIX}"

    if release_dir.exists():
        shutil.rmtree(release_dir)
    if archive_path.exists():
        archive_path.unlink()

    shutil.copytree(bundle_dir, release_dir)
    copy_release_assets(workspace, release_dir)
    validate_release_dir(release_dir)
    compress_runtime(release_dir)
    write_7z(release_dir, archive_path, archive_tool)
    return release_dir, archive_path


def copy_release_assets(workspace: Path, release_dir: Path) -> None:
    shutil.copy2(workspace / "README.md", release_dir / "README.md")

    release_config_dir = release_dir / "config"
    release_config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(workspace / "config" / "template.csv", release_config_dir / "template.csv")
    shutil.copytree(workspace / "config" / "example", release_config_dir / "example")


def validate_release_dir(release_dir: Path) -> None:
    for relative_path in EXPECTED_PACKAGE_FILES:
        target = release_dir / relative_path
        if not target.exists():
            raise RuntimeError(f"Expected packaged file is missing: {target}")


def main() -> int:
    args = parse_args()
    version, versions = load_versions()
    version_tag = f"v{version}"
    variants = ["cpu", "gpu"] if args.variant == "all" else [args.variant]

    print(f"[info] Building release bundles for {version_tag}")
    print(f"[info] Verified pyproject versions: {versions}")

    if args.clean:
        shutil.rmtree(args.output_root, ignore_errors=True)
        shutil.rmtree(BUILD_ROOT, ignore_errors=True)

    args.output_root.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, Path, Path]] = []
    for variant in variants:
        release_dir, archive_path = build_variant(
            variant,
            version_tag,
            args.output_root,
            clean=False,
            archive_tool=args.archive_tool,
        )
        results.append((variant, release_dir, archive_path))

    print("[done] Built release bundles:")
    for variant, release_dir, archive_path in results:
        size_mb = archive_path.stat().st_size / (1024 * 1024)
        print(f"  - {variant}: {archive_path} ({size_mb:.1f} MiB), unpacked at {release_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
