from __future__ import annotations

import csv
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from csv_editor.adapters.ocr_adapter import RuntimeOcrPreviewAdapter
from csv_editor.domain.models import EditorDocument, FlowDocument, OperationNode
from csv_editor.io.csv_codec import CsvEditorCodec
from csv_editor.io.editor_state import EditorStateRepository
from csv_editor.io.assets import save_capture_image
from csv_editor.io.node_clipboard import (
    CLIPBOARD_TEXT_PREFIX,
    build_clipboard_payload,
    deserialize_clipboard_payload,
    serialize_clipboard_payload,
)
from csv_editor.services.asset_usage import find_unused_images
from csv_editor.services.capture import capture_point as native_capture_point
from csv_editor.services.capture import capture_region as native_capture_region
from csv_editor.services.recording import (
    RecordingSession,
    RecordingState,
    VisibleWindowInfo,
    build_recording_review_rows,
    build_recording_summary,
    list_visible_windows,
)
from csv_editor.services.validation import validate_document as validate_editor_document

from .api_models import ApiResult
from .clipboard import ClipboardUnavailableError, SystemClipboard
from .dto import (
    editor_document_from_dict,
    editor_document_to_dict,
    external_flow_summary_to_dict,
    node_clipboard_payload_from_dict,
    node_clipboard_payload_to_dict,
    operation_node_to_dict,
    save_document_result_to_dict,
    unused_image_to_dict,
    validation_issue_to_dict,
)
from .recording_assistant import (
    COMMAND_CLOSE_ATTEMPT,
    COMMAND_MARK,
    COMMAND_PAUSE,
    COMMAND_RESUME,
    COMMAND_STOP,
    AssistantCommand,
    AssistantRect,
    NativeRecordingAssistant,
)


@dataclass(slots=True)
class CompletedRecordingResult:
    session_id: str
    source_root: Path | None
    source_flow: str
    nodes: list[OperationNode]
    response_payload: dict[str, object]


class EditorBridgeApi:
    def __init__(
        self,
        *,
        initial_root_path: Path | None = None,
        app_name: str = "CsvAutoGui Editor",
        app_version: str = "0.0.0",
        frontend_entry: str | None = None,
        codec: CsvEditorCodec | None = None,
        state_repo: EditorStateRepository | None = None,
        clipboard: SystemClipboard | None = None,
    ) -> None:
        self._initial_root_path = initial_root_path
        self._app_name = app_name
        self._app_version = app_version
        self._frontend_entry = frontend_entry
        self._codec = codec or CsvEditorCodec()
        self._state_repo = state_repo or EditorStateRepository(enabled=True)
        self._clipboard = clipboard or SystemClipboard()
        self._window: Any | None = None
        self._ocr_preview = RuntimeOcrPreviewAdapter()
        self._recording_session: RecordingSession | None = None
        self._recording_session_id: str | None = None
        self._recording_source_root: Path | None = None
        self._recording_source_flow: str = "main.csv"
        self._completed_recording: CompletedRecordingResult | None = None
        self._recording_assistant: NativeRecordingAssistant | None = None
        self._recording_window_hidden = False

    def set_window(self, window: Any) -> None:
        self._window = window

    def get_bootstrap(self) -> dict[str, object]:
        return ApiResult.success(
            {
                "app_name": self._app_name,
                "app_version": self._app_version,
                "platform": sys.platform,
                "initial_root_path": str(self._initial_root_path) if self._initial_root_path else None,
                "frontend_entry": self._frontend_entry,
                "capabilities": {
                    "choose_config_directory": True,
                    "document_bridge": True,
                    "clipboard_bridge": True,
                    "external_flow_import": True,
                    "scan_unused_images": True,
                    "delete_unused_images": True,
                    "capture_region": True,
                    "capture_point": True,
                    "recording": True,
                    "pause_recording": True,
                    "copy_recorded_nodes": True,
                    "list_visible_windows": True,
                    "add_visual_mark": True,
                },
            }
        ).to_dict()

    def choose_config_directory(self) -> dict[str, object]:
        try:
            selected_path = self._choose_config_directory()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to choose config directory", {"reason": str(exc)}).to_dict()
        return ApiResult.success(str(selected_path) if selected_path else None).to_dict()

    def load_document(self, rootPath: str) -> dict[str, object]:
        try:
            root_path = self._resolve_root_path(rootPath)
            document = self._codec.load_document(root_path)
            document.state = self._state_repo.load(root_path)
            document.ensure_main_first()
            return ApiResult.success(editor_document_to_dict(document)).to_dict()
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {rootPath}").to_dict()
        except csv.Error as exc:
            return ApiResult.failure("csv_parse_error", "Failed to parse csv files", {"reason": str(exc)}).to_dict()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to load document", {"reason": str(exc)}).to_dict()

    def save_document(self, input: object) -> dict[str, object]:
        try:
            document = self._parse_document_input(input)
            root_path = self._resolve_root_path(document.root_path)
            document.root_path = root_path
            self._validate_flow_paths(document)
            self._delete_removed_flows(document)
            self._codec.save_document(document)
            self._state_repo.save(root_path, document.state)
            normalized = self._codec.load_document(root_path)
            normalized.state = document.state
            normalized.ensure_main_first()
            return ApiResult.success(save_document_result_to_dict(normalized)).to_dict()
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {self._document_root_for_error(input)}").to_dict()
        except ValueError as exc:
            return ApiResult.failure("validation_error", str(exc)).to_dict()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to save document", {"reason": str(exc)}).to_dict()

    def validate_document(self, document: object) -> dict[str, object]:
        try:
            parsed = editor_document_from_dict(document)
            issues = [validation_issue_to_dict(issue) for issue in validate_editor_document(parsed)]
            return ApiResult.success(issues).to_dict()
        except ValueError as exc:
            return ApiResult.failure("validation_error", str(exc)).to_dict()

    def list_external_flows(self, rootPath: str) -> dict[str, object]:
        try:
            root_path = self._resolve_root_path(rootPath)
            document = self._codec.load_document(root_path)
            flows = [external_flow_summary_to_dict(root_path, flow) for flow in document.flows]
            return ApiResult.success(flows).to_dict()
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {rootPath}").to_dict()
        except csv.Error as exc:
            return ApiResult.failure("csv_parse_error", "Failed to parse csv files", {"reason": str(exc)}).to_dict()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to list external flows", {"reason": str(exc)}).to_dict()

    def import_nodes(self, input: object) -> dict[str, object]:
        data = input if isinstance(input, dict) else {}
        root_path_raw = data.get("root_path") or data.get("rootPath")
        flow_name = str(data.get("flow_name") or data.get("flowName") or "")
        node_ids_raw = data.get("node_ids") or data.get("nodeIds") or []
        node_ids = [str(node_id) for node_id in node_ids_raw if str(node_id)]

        if not flow_name:
            return ApiResult.failure("validation_error", "flow_name is required").to_dict()

        try:
            root_path = self._resolve_root_path(root_path_raw)
            document = self._codec.load_document(root_path)
            flow = document.get_flow(flow_name)
            if flow is None:
                return ApiResult.failure("validation_error", f"Flow not found: {flow_name}").to_dict()
            nodes = self._select_import_nodes(flow, node_ids)
            return ApiResult.success([operation_node_to_dict(node) for node in nodes]).to_dict()
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {root_path_raw}").to_dict()
        except ValueError as exc:
            return ApiResult.failure("validation_error", str(exc)).to_dict()
        except csv.Error as exc:
            return ApiResult.failure("csv_parse_error", "Failed to parse csv files", {"reason": str(exc)}).to_dict()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to import nodes", {"reason": str(exc)}).to_dict()

    def scan_unused_images(self, rootPath: str) -> dict[str, object]:
        try:
            root_path = self._resolve_root_path(rootPath)
            document = self._codec.load_document(root_path)
            unused = [unused_image_to_dict(root_path, image_name) for image_name in find_unused_images(document)]
            return ApiResult.success(unused).to_dict()
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {rootPath}").to_dict()
        except csv.Error as exc:
            return ApiResult.failure("csv_parse_error", "Failed to parse csv files", {"reason": str(exc)}).to_dict()
        except OSError as exc:
            return ApiResult.failure("io_error", "Failed to scan unused images", {"reason": str(exc)}).to_dict()

    def delete_unused_images(self, input: object) -> dict[str, object]:
        data = input if isinstance(input, dict) else {}
        root_path_raw = data.get("root_path") or data.get("rootPath")
        image_names_raw = data.get("image_names") or data.get("imageNames") or []
        image_names = [str(image_name) for image_name in image_names_raw] if isinstance(image_names_raw, (list, tuple)) else []

        try:
            root_path = self._resolve_root_path(root_path_raw)
        except FileNotFoundError:
            return ApiResult.failure("config_not_found", f"Config directory not found: {root_path_raw}").to_dict()

        deleted: list[str] = []
        missing: list[str] = []
        failed: list[dict[str, str]] = []
        for image_name in image_names:
            try:
                image_path = self._asset_path(root_path, image_name)
            except ValueError as exc:
                failed.append({"image_name": image_name, "reason": str(exc)})
                continue

            if not image_path.exists():
                missing.append(image_name)
                continue

            try:
                image_path.unlink()
            except OSError as exc:
                failed.append({"image_name": image_name, "reason": str(exc)})
                continue
            deleted.append(image_name)

        return ApiResult.success(
            {
                "deleted": deleted,
                "missing": missing,
                "failed": failed,
            }
        ).to_dict()

    def read_clipboard_nodes(self) -> dict[str, object]:
        try:
            raw_text = self._clipboard.read_text()
        except ClipboardUnavailableError as exc:
            return ApiResult.failure("clipboard_unavailable", "Clipboard is unavailable", {"reason": str(exc)}).to_dict()
        payload = deserialize_clipboard_payload(raw_text or "")
        if payload is None:
            return ApiResult.success(None).to_dict()
        return ApiResult.success(node_clipboard_payload_to_dict(payload)).to_dict()

    def write_clipboard_nodes(self, payload: object) -> dict[str, object]:
        try:
            clipboard_payload = node_clipboard_payload_from_dict(payload)
            raw_text = serialize_clipboard_payload(clipboard_payload)
            self._clipboard.write_text(f"{CLIPBOARD_TEXT_PREFIX}{raw_text}")
            return ApiResult.success(None).to_dict()
        except ClipboardUnavailableError as exc:
            return ApiResult.failure("clipboard_unavailable", "Clipboard is unavailable", {"reason": str(exc)}).to_dict()
        except Exception as exc:
            return ApiResult.failure("validation_error", f"Invalid clipboard payload: {exc}").to_dict()

    def capture_region(self, prompt: str | None = None) -> dict[str, object]:
        data = prompt if isinstance(prompt, dict) else {"prompt": prompt}
        root_path_raw = data.get("root_path") or data.get("rootPath")
        prompt_text = str(data.get("prompt") or "")
        save_image = bool(data.get("save_image") or data.get("saveImage"))
        ocr_preview = bool(data.get("ocr_preview") or data.get("ocrPreview"))
        try:
            with self._hidden_window():
                captured = native_capture_region(prompt=prompt_text)
        except RuntimeError as exc:
            return ApiResult.failure("io_error", str(exc)).to_dict()
        if captured is None:
            return ApiResult.success(None).to_dict()

        image_path: str | None = None
        ocr_candidates: list[str] = []
        if save_image:
            if not root_path_raw:
                return ApiResult.failure("validation_error", "root_path is required when save_image is enabled").to_dict()
            try:
                root_path = self._resolve_root_path(root_path_raw)
                image_path = save_capture_image(root_path, captured.image, captured.left, captured.top, captured.width, captured.height)
            except Exception as exc:
                return ApiResult.failure("io_error", "Failed to save captured image", {"reason": str(exc)}).to_dict()
        if ocr_preview:
            ocr_candidates = self._ocr_preview.preview_from_image(captured.image)

        payload: dict[str, object] = {
            "left": captured.left,
            "top": captured.top,
            "width": captured.width,
            "height": captured.height,
            "region_text": captured.region_text,
            "image_path": image_path,
        }
        if ocr_candidates:
            payload["ocr_candidates"] = ocr_candidates
            payload["suggested_text"] = ocr_candidates[0]
        return ApiResult.success(payload).to_dict()

    def capture_point(self, prompt: str | None = None) -> dict[str, object]:
        prompt_text = str(prompt or "")
        try:
            with self._hidden_window():
                captured = native_capture_point(prompt=prompt_text)
        except RuntimeError as exc:
            return ApiResult.failure("io_error", str(exc)).to_dict()
        if captured is None:
            return ApiResult.success(None).to_dict()
        return ApiResult.success({"x": captured.x, "y": captured.y, "point_text": captured.point_text}).to_dict()

    def start_recording(self, input: object) -> dict[str, object]:
        self._finalize_pending_recording_session()
        if self._recording_session is not None and self._recording_session.get_state().is_recording:
            return ApiResult.failure("recording_busy", "A recording session is already active").to_dict()

        data = input if isinstance(input, dict) else {}
        target_hwnd = data.get("target_window_hwnd") or data.get("targetWindowHwnd")
        coordinate_mode = str(data.get("coordinate_mode") or data.get("coordinateMode") or "screen")
        match_child_window = self._coerce_bool(data.get("match_child_window") if "match_child_window" in data else data.get("matchChildWindow"))
        source_root_raw = data.get("source_root") or data.get("sourceRoot")
        source_flow = str(data.get("source_flow") or data.get("sourceFlow") or "main.csv")

        if coordinate_mode not in {"screen", "window"}:
            return ApiResult.failure("validation_error", f"Unsupported coordinate_mode: {coordinate_mode}").to_dict()

        session = RecordingSession()
        session.recorder.set_coordinate_mode(coordinate_mode)
        if coordinate_mode == "window":
            target_window = self._resolve_visible_window(target_hwnd)
            if target_window is None:
                return ApiResult.failure("validation_error", "Target window is required for window coordinate mode").to_dict()
            session.recorder.set_target_window(target_window, match_child_window)
        else:
            session.recorder.set_target_window(None, match_child_window=False)

        try:
            session.start(stop_callback=self._handle_recording_stop_requested)
        except RuntimeError as exc:
            return ApiResult.failure("io_error", str(exc)).to_dict()

        self._completed_recording = None
        self._recording_session = session
        self._recording_session_id = uuid4().hex
        self._recording_source_root = self._resolve_optional_root(source_root_raw)
        self._recording_source_flow = source_flow or "main.csv"
        assistant_message = "Recording started. Use Shift+X as the fallback stop hotkey."
        try:
            self._show_recording_assistant()
            threading.Thread(target=self._hide_recording_window, name="csv-editor-hide-recording-window", daemon=True).start()
            assistant_message = "Native recording assistant active. Use the assistant or Shift+X to stop."
        except RuntimeError as exc:
            assistant_message = f"Recording started without native assistant: {exc}. Use Shift+X to stop."
        return ApiResult.success(self._recording_status_payload(message=assistant_message)).to_dict()

    def pause_recording(self, input: object) -> dict[str, object]:
        data = input if isinstance(input, dict) else {}
        session_id = str(data.get("session_id") or data.get("sessionId") or "")
        paused = self._coerce_bool(data.get("paused"))
        self._finalize_pending_recording_session(session_id)
        session = self._require_recording_session(session_id)
        if session is None:
            completed = self._completed_recording_for(session_id)
            if completed is not None:
                return ApiResult.success(dict(completed.response_payload["session"])).to_dict()
            return ApiResult.failure("recording_not_started", "Recording session is not active").to_dict()
        if not session.get_state().is_recording:
            return ApiResult.failure("recording_not_started", "Recording session is not active").to_dict()
        session.set_capture_paused(paused)
        self._sync_recording_assistant("Capture paused." if paused else "Recording resumed.")
        return ApiResult.success(self._recording_status_payload()).to_dict()

    def get_recording_status(self, sessionId: str) -> dict[str, object]:
        self._finalize_pending_recording_session(sessionId)
        if self._require_recording_session(sessionId) is None:
            completed = self._completed_recording_for(sessionId)
            if completed is not None:
                return ApiResult.success(dict(completed.response_payload["session"])).to_dict()
            return ApiResult.failure("recording_not_started", "Recording session is not active").to_dict()
        return ApiResult.success(self._recording_status_payload()).to_dict()

    def stop_recording(self, sessionId: str) -> dict[str, object]:
        self._finalize_pending_recording_session(sessionId)
        completed = self._completed_recording_for(sessionId)
        if completed is not None:
            return ApiResult.success(completed.response_payload).to_dict()

        session = self._require_recording_session(sessionId)
        if session is None:
            return ApiResult.failure("recording_not_started", "Recording session is not active").to_dict()
        return ApiResult.success(self._complete_recording_session(sessionId, stop_reason="user_stop")).to_dict()

    def copy_recorded_nodes(self, input: object) -> dict[str, object]:
        data = input if isinstance(input, dict) else {}
        session_id = str(data.get("session_id") or data.get("sessionId") or "")
        destination = str(data.get("destination") or "clipboard").strip().lower()
        requested_ids = data.get("node_ids") if "node_ids" in data else data.get("nodeIds")
        if destination != "clipboard":
            return ApiResult.failure("validation_error", f"Unsupported destination: {destination}").to_dict()

        self._finalize_pending_recording_session(session_id)
        completed = self._completed_recording_for(session_id)
        if completed is None:
            return ApiResult.failure("recording_not_started", "Recording review is not available").to_dict()
        if completed.source_root is None:
            return ApiResult.failure("validation_error", "Recording source_root is unavailable for clipboard copy").to_dict()

        try:
            nodes = self._select_recorded_nodes(completed.nodes, requested_ids)
        except ValueError as exc:
            return ApiResult.failure("validation_error", str(exc)).to_dict()

        try:
            payload = build_clipboard_payload(completed.source_root, completed.source_flow, nodes)
            raw_text = serialize_clipboard_payload(payload)
            self._clipboard.write_text(f"{CLIPBOARD_TEXT_PREFIX}{raw_text}")
        except ClipboardUnavailableError as exc:
            return ApiResult.failure("clipboard_unavailable", "Clipboard is unavailable", {"reason": str(exc)}).to_dict()
        return ApiResult.success(None).to_dict()

    def list_visible_windows(self) -> dict[str, object]:
        windows = [
            {
                "hwnd": window.hwnd,
                "title": window.title,
                "process_name": window.process_name,
                "class_name": window.class_name,
                "display_text": window.display_text,
            }
            for window in list_visible_windows()
        ]
        return ApiResult.success(windows).to_dict()

    def add_visual_mark(self, input: object) -> dict[str, object]:
        self._finalize_pending_recording_session()
        if not self._recording_session or self._recording_session_id is None:
            return ApiResult.failure("recording_not_started", "Recording session is not active").to_dict()

        data = input if isinstance(input, dict) else {}
        kind = str(data.get("kind") or "")
        action = str(data.get("action") or "")
        search_target = str(data.get("search_target") or data.get("searchTarget") or "")
        region_text = str(data.get("region_text") or data.get("regionText") or "")
        note = str(data.get("note") or "")
        if not kind or not action or not region_text:
            return ApiResult.failure("validation_error", "kind, action, and region_text are required").to_dict()

        try:
            self._recording_session.recorder.add_visual_mark(
                kind=kind,
                action=action,
                search_target=search_target,
                region_text=region_text,
                note=note,
            )
        except ValueError as exc:
            return ApiResult.failure("validation_error", str(exc)).to_dict()
        self._sync_recording_assistant(f"Added {kind.upper()} {action}")
        return ApiResult.success(self._recording_status_payload()).to_dict()

    def _choose_config_directory(self) -> Path | None:
        if self._window is not None:
            return self._choose_directory_via_window()
        return self._choose_directory_via_tk()

    def _choose_directory_via_window(self) -> Path | None:
        if self._window is None:
            return None
        try:
            import webview
        except ImportError:
            return None

        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            chosen = result[0] if result else None
        else:
            chosen = result
        if not chosen:
            return None
        return Path(chosen)

    def _choose_directory_via_tk(self) -> Path | None:
        try:
            from tkinter import Tk, filedialog
        except Exception as exc:  # pragma: no cover - platform specific
            raise OSError("Folder dialog is unavailable") from exc

        root = Tk()
        root.withdraw()
        try:
            selected = filedialog.askdirectory()
        finally:
            root.destroy()
        return Path(selected) if selected else None

    def _parse_document_input(self, payload: object) -> EditorDocument:
        if isinstance(payload, dict) and "document" in payload:
            raw_document = payload["document"]
        else:
            raw_document = payload
        if not isinstance(raw_document, dict):
            raise ValueError("document payload must be an object")
        if not raw_document.get("root_path"):
            raise ValueError("document.root_path is required")
        document = editor_document_from_dict(raw_document)
        document.ensure_main_first()
        for flow in document.flows:
            flow.reindex()
        return document

    def _resolve_root_path(self, root_path: str | Path | object) -> Path:
        path = Path(str(root_path)).expanduser()
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(str(root_path))
        return path.resolve()

    def _validate_flow_paths(self, document: EditorDocument) -> None:
        seen_names: set[str] = set()
        for flow in document.flows:
            if not flow.filename:
                raise ValueError("Flow filename cannot be empty")
            if Path(flow.filename).name != flow.filename:
                raise ValueError(f"Invalid flow filename: {flow.filename}")
            if not flow.filename.lower().endswith(".csv"):
                raise ValueError(f"Flow filename must end with .csv: {flow.filename}")
            folded = flow.filename.casefold()
            if folded in seen_names:
                raise ValueError(f"Duplicate flow filename: {flow.filename}")
            seen_names.add(folded)
            self._flow_path(document.root_path, flow.filename)

    def _delete_removed_flows(self, document: EditorDocument) -> None:
        expected = {flow.filename.casefold() for flow in document.flows}
        for csv_path in document.root_path.glob("*.csv"):
            if csv_path.name.casefold() not in expected:
                csv_path.unlink()

    def _flow_path(self, root_path: Path, filename: str) -> Path:
        candidate = (root_path / filename).resolve()
        try:
            candidate.relative_to(root_path.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid flow filename: {filename}") from exc
        return candidate

    def _asset_path(self, root_path: Path, image_name: str) -> Path:
        if not image_name or Path(image_name).name != image_name:
            raise ValueError(f"Invalid image name: {image_name}")
        candidate = (root_path / image_name).resolve()
        try:
            candidate.relative_to(root_path.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid image name: {image_name}") from exc
        return candidate

    def _select_import_nodes(self, flow: FlowDocument, node_ids: list[str]) -> list[OperationNode]:
        if not node_ids:
            return []
        by_id = {node.node_id: node for node in flow.nodes}
        missing = [node_id for node_id in node_ids if node_id not in by_id]
        if missing:
            raise ValueError(f"Unknown node ids: {', '.join(missing)}")

        imported: list[OperationNode] = []
        for index, node_id in enumerate(node_ids, start=1):
            clone = by_id[node_id].clone()
            clone.node_id = uuid4().hex
            clone.index = index
            imported.append(clone)
        return imported

    def _select_recorded_nodes(self, nodes: list[OperationNode], requested_ids: object) -> list[OperationNode]:
        if requested_ids == "all":
            return [node.clone() for node in nodes]
        if not isinstance(requested_ids, (list, tuple)):
            raise ValueError("node_ids must be 'all' or a list of node ids")

        selected_ids = {str(node_id) for node_id in requested_ids if str(node_id)}
        if not selected_ids:
            raise ValueError("node_ids cannot be empty")

        selected = [node.clone() for node in nodes if node.node_id in selected_ids]
        if len(selected) != len(selected_ids):
            found_ids = {node.node_id for node in selected}
            missing = sorted(selected_ids - found_ids)
            raise ValueError(f"Unknown recorded node ids: {', '.join(missing)}")
        return selected

    def _document_root_for_error(self, payload: object) -> str:
        if isinstance(payload, dict):
            if "document" in payload and isinstance(payload["document"], dict):
                document = payload["document"]
                root_path = document.get("root_path")
                if root_path is not None:
                    return str(root_path)
            root_path = payload.get("root_path")
            if root_path is not None:
                return str(root_path)
        return ""

    def _not_implemented(self, operation: str) -> dict[str, object]:
        return ApiResult.failure(
            "not_implemented",
            f"{operation} is not implemented in the web host skeleton",
        ).to_dict()

    def _resolve_visible_window(self, hwnd: object) -> VisibleWindowInfo | None:
        try:
            target = int(hwnd)
        except (TypeError, ValueError):
            return None
        for window in list_visible_windows():
            if window.hwnd == target:
                return window
        return None

    def _resolve_optional_root(self, root_path: object) -> Path | None:
        if root_path in {None, ""}:
            return None
        try:
            return self._resolve_root_path(root_path)
        except FileNotFoundError:
            return None

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _require_recording_session(self, session_id: object) -> RecordingSession | None:
        if not self._recording_session or str(session_id or "") != (self._recording_session_id or ""):
            return None
        return self._recording_session

    def _completed_recording_for(self, session_id: object) -> CompletedRecordingResult | None:
        if self._completed_recording is None:
            return None
        if str(session_id or "") != self._completed_recording.session_id:
            return None
        return self._completed_recording

    def _finalize_pending_recording_session(self, session_id: object | None = None) -> CompletedRecordingResult | None:
        if self._recording_session is None or self._recording_session_id is None:
            return self._completed_recording_for(session_id) if session_id else self._completed_recording
        if session_id is not None and str(session_id or "") != self._recording_session_id:
            return self._completed_recording_for(session_id)
        if not self._recording_session.get_state().stop_pending:
            return None
        return self._complete_recording_session(self._recording_session_id, stop_reason="stop_hotkey")

    def _complete_recording_session(self, session_id: str, *, stop_reason: str) -> dict[str, object]:
        session = self._require_recording_session(session_id)
        if session is None:
            completed = self._completed_recording_for(session_id)
            if completed is None:
                raise ValueError(f"Recording session is not active: {session_id}")
            return completed.response_payload

        state_before_stop = session.get_state()
        nodes = session.stop()
        response_payload = self._build_recording_result_payload(
            session_id=session_id,
            nodes=nodes,
            state=state_before_stop,
            source_root=self._recording_source_root,
            source_flow=self._recording_source_flow,
            stop_reason=stop_reason,
        )
        self._completed_recording = CompletedRecordingResult(
            session_id=session_id,
            source_root=self._recording_source_root,
            source_flow=self._recording_source_flow,
            nodes=[node.clone() for node in nodes],
            response_payload=response_payload,
        )
        self._teardown_recording_assistant()
        self._restore_recording_window()
        self._recording_session = None
        self._recording_session_id = None
        self._recording_source_root = None
        self._recording_source_flow = "main.csv"
        return response_payload

    def _show_recording_assistant(self) -> None:
        self._teardown_recording_assistant()
        assistant = NativeRecordingAssistant(
            on_command=self._handle_assistant_command,
            on_geometry_changed=self._handle_assistant_geometry_changed,
        )
        assistant.start()
        assistant.show()
        self._recording_assistant = assistant
        self._sync_recording_assistant("Native assistant active. Shift+X is available as fallback.", close_protected=True)

    def _teardown_recording_assistant(self) -> None:
        assistant = self._recording_assistant
        self._recording_assistant = None
        if assistant is None:
            return
        try:
            assistant.close(force=True, wait=True)
        except Exception:
            pass

    def _hide_recording_window(self) -> None:
        if self._window is None or self._recording_window_hidden:
            return
        hide = getattr(self._window, "hide", None)
        if callable(hide):
            hide()
            self._recording_window_hidden = True
            time.sleep(0.15)

    def _restore_recording_window(self) -> None:
        if self._window is None or not self._recording_window_hidden:
            return
        show = getattr(self._window, "show", None)
        restore = getattr(self._window, "restore", None)
        if callable(show):
            show()
        if callable(restore):
            restore()
        self._recording_window_hidden = False

    def _handle_recording_stop_requested(self) -> None:
        if self._recording_session_id is None:
            return
        self._sync_recording_assistant("Finishing review...", close_protected=False)
        self._finalize_pending_recording_session(self._recording_session_id)

    def _handle_assistant_command(self, command: AssistantCommand) -> None:
        if command.name == COMMAND_PAUSE:
            self._handle_assistant_pause_changed(True)
            return
        if command.name == COMMAND_RESUME:
            self._handle_assistant_pause_changed(False)
            return
        if command.name == COMMAND_STOP:
            self._handle_assistant_stop_requested()
            return
        if command.name == COMMAND_MARK:
            self._handle_assistant_mark_requested(command.mark_kind, command.mark_action)
            return
        if command.name == COMMAND_CLOSE_ATTEMPT:
            self._sync_recording_assistant("Stop recording before closing the assistant.", close_protected=True)

    def _handle_assistant_pause_changed(self, paused: bool) -> None:
        session = self._recording_session
        if session is None or self._recording_session_id is None:
            return
        session.set_capture_paused(paused)
        self._sync_recording_assistant("Capture paused." if paused else "Recording resumed.")

    def _handle_assistant_stop_requested(self) -> None:
        session_id = self._recording_session_id
        if not session_id:
            return
        self._sync_recording_assistant("Stopping...", close_protected=False)
        self._complete_recording_session(session_id, stop_reason="assistant_stop")

    def _handle_assistant_geometry_changed(self, rect: AssistantRect | None) -> None:
        session = self._recording_session
        if session is None:
            return
        if rect is None or rect.width <= 0 or rect.height <= 0:
            session.set_ignored_screen_rects([])
            session.set_overlay_visible(False)
            return
        session.set_ignored_screen_rects([rect.as_tuple()])
        session.set_overlay_visible(True)

    def _handle_assistant_mark_requested(self, kind: str, action: str) -> None:
        session = self._recording_session
        if session is None or self._recording_session_id is None:
            return

        was_paused = session.get_state().capture_paused
        session.set_capture_paused(True)
        session.suppress_events_for(0.25)
        session.set_ignored_screen_rects([])
        session.set_overlay_visible(False)
        assistant = self._recording_assistant
        self._sync_recording_assistant(f"{kind.upper()} {action} marking...", close_protected=True)

        captured = None
        error_text = ""
        note = ""
        search_target = ""
        prompt = f"{kind.upper()} {action}: capture target region"
        try:
            if assistant is not None:
                captured = assistant.run_hidden(native_capture_region, prompt=prompt)
            else:
                captured = native_capture_region(prompt=prompt)
            if captured is not None:
                if kind == "pic":
                    if self._recording_source_root is None:
                        raise RuntimeError("Recording source root is unavailable for picture marks.")
                    saved_path = save_capture_image(
                        self._recording_source_root,
                        captured.image,
                        captured.left,
                        captured.top,
                        captured.width,
                        captured.height,
                    )
                    search_target = str(saved_path)
                else:
                    candidates = self._ocr_preview.preview_from_image(captured.image)
                    unique_candidates = [candidate.strip() for candidate in dict.fromkeys(candidates) if candidate.strip()]
                    if unique_candidates:
                        if len(unique_candidates) > 1 and assistant is not None:
                            selected_candidate = assistant.choose_text_candidate(
                                unique_candidates,
                                title="Choose OCR Candidate",
                                prompt="Select the OCR text to use for this recording mark.",
                                initial_value=unique_candidates[0],
                            )
                            search_target = (selected_candidate or unique_candidates[0]).strip()
                            if search_target and search_target not in unique_candidates:
                                note = f"Manual OCR candidate: {search_target}"
                        else:
                            search_target = unique_candidates[0]
                    else:
                        note = "OCR text was not recognized during recording; review before insert."

                session.recorder.add_visual_mark(
                    kind=kind,
                    action=action,
                    search_target=search_target,
                    region_text=captured.region_text,
                    note=note,
                )
        except Exception as exc:
            error_text = f"Mark failed: {exc}"

        session.suppress_events_for(0.25)
        session.set_capture_paused(was_paused)
        if error_text:
            status_text = error_text
        elif captured is None:
            status_text = "Mark cancelled"
        else:
            target_label = search_target or "(review target)"
            status_text = f"Added {kind.upper()} {action} {target_label}"
        self._sync_recording_assistant(status_text, close_protected=True)

    def _assistant_target_label(self, state: RecordingState) -> str:
        target = state.target_window
        if target is None:
            return "free screen"
        return target.display_text

    def _sync_recording_assistant(self, message: str | None = None, *, close_protected: bool | None = None) -> None:
        assistant = self._recording_assistant
        session = self._recording_session
        if assistant is None or session is None:
            return
        state = session.get_state()
        status = "paused" if state.capture_paused else "recording"
        assistant.set_status(
            status=status,
            event_count=state.event_count,
            paused=state.capture_paused,
            coordinate_mode=state.coordinate_mode,
            target_label=self._assistant_target_label(state),
            message=message,
            close_protected=close_protected,
        )

    def _build_recording_result_payload(
        self,
        *,
        session_id: str,
        nodes: list[OperationNode],
        state: RecordingState,
        source_root: Path | None,
        source_flow: str,
        stop_reason: str,
    ) -> dict[str, object]:
        review_rows = build_recording_review_rows(nodes)
        summary = build_recording_summary(nodes)
        return {
            "session": self._recording_status_payload(
                stopped=True,
                session_id=session_id,
                state=state,
                source_root=source_root,
                source_flow=source_flow,
                message="Recording stopped. Review is ready.",
                review_ready=True,
                close_protected=False,
                stop_reason=stop_reason,
            ),
            "nodes": [operation_node_to_dict(node) for node in nodes],
            "review_rows": [
                {
                    "source": row.source,
                    "semantic": row.semantic,
                    "node_text": row.node_text,
                    "target_text": row.target_text,
                    "region_text": row.region_text,
                    "strategy_text": row.strategy_text,
                    "wait_text": row.wait_text,
                    "note_text": row.note_text,
                }
                for row in review_rows
            ],
            "summary": {
                "total": summary.total,
                "visual_count": summary.visual_count,
                "wait_count": summary.wait_count,
                "locator_count": summary.locator_count,
                "input_count": summary.input_count,
            },
        }

    def _recording_status_payload(
        self,
        stopped: bool = False,
        *,
        session_id: str | None = None,
        state: RecordingState | None = None,
        source_root: Path | None = None,
        source_flow: str | None = None,
        message: str | None = None,
        review_ready: bool = False,
        close_protected: bool | None = None,
        stop_reason: str | None = None,
    ) -> dict[str, object]:
        if state is None and self._recording_session is not None:
            state = self._recording_session.get_state()
        target_window_payload = None
        status = "idle"
        session_message = message
        if state is not None:
            target = state.target_window
            if target is not None:
                target_window_payload = {
                    "hwnd": target.hwnd,
                    "title": target.title,
                    "process_name": target.process_name,
                    "class_name": target.class_name,
                }
            if stopped:
                status = "stopped"
            elif state.is_recording and state.capture_paused:
                status = "paused"
            elif state.is_recording:
                status = "recording"
            elif state.stop_pending:
                status = "stopped"
            if state.stop_pending and not stopped and session_message is None:
                session_message = "Stop requested"
        resolved_close_protected = close_protected if close_protected is not None else status in {"recording", "paused"}
        return {
            "session_id": session_id if session_id is not None else self._recording_session_id,
            "status": status,
            "target_window": target_window_payload,
            "coordinate_mode": state.coordinate_mode if state is not None else "screen",
            "match_child_window": state.match_child_window if state is not None else False,
            "overlay_visible": state.overlay_visible if state is not None else False,
            "capture_paused": state.capture_paused if state is not None else False,
            "ignored_region_count": state.ignored_rect_count if state is not None else 0,
            "assistant_suppressing_events": state.suppressing_events if state is not None else False,
            "buffered_event_count": state.event_count if state is not None else 0,
            "message": session_message,
            "source_root": str(source_root if source_root is not None else self._recording_source_root)
            if (source_root if source_root is not None else self._recording_source_root) is not None
            else None,
            "source_flow": source_flow if source_flow is not None else self._recording_source_flow,
            "review_ready": review_ready,
            "close_protected": resolved_close_protected,
            "stop_reason": stop_reason,
        }

    class _HiddenWindowContext:
        def __init__(self, window: Any | None) -> None:
            self._window = window
            self._hidden = False

        def __enter__(self) -> None:
            if self._window is None:
                return
            hide = getattr(self._window, "hide", None)
            if callable(hide):
                hide()
                self._hidden = True
                time.sleep(0.15)

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._window is None or not self._hidden:
                return
            show = getattr(self._window, "show", None)
            restore = getattr(self._window, "restore", None)
            if callable(show):
                show()
            if callable(restore):
                restore()

    def _hidden_window(self) -> "_HiddenWindowContext":
        return self._HiddenWindowContext(self._window)
