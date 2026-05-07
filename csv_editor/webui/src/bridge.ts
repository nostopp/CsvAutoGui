import type {
  ApiResult,
  BootstrapDTO,
  DeleteUnusedImagesResultDTO,
  EditorDocumentDTO,
  ExternalFlowSummaryDTO,
  NodeClipboardPayloadDTO,
  OperationNodeDTO,
  RecordedNodesResultDTO,
  RecordingSessionDTO,
  UnusedImageDTO,
  ValidationIssueDTO,
  VisibleWindowDTO,
} from "./types";

declare global {
  interface Window {
    pywebview?: {
      api?: Record<string, (...args: unknown[]) => Promise<unknown> | unknown>;
    };
  }
}

type ApiName =
  | "get_bootstrap"
  | "choose_config_directory"
  | "load_document"
  | "save_document"
  | "validate_document"
  | "list_external_flows"
  | "import_nodes"
  | "scan_unused_images"
  | "delete_unused_images"
  | "read_clipboard_nodes"
  | "write_clipboard_nodes"
  | "capture_region"
  | "capture_point"
  | "start_recording"
  | "pause_recording"
  | "get_recording_status"
  | "stop_recording"
  | "copy_recorded_nodes"
  | "list_visible_windows"
  | "add_visual_mark";

function notImplemented(name: string): ApiResult<never> {
  return {
    ok: false,
    error: {
      code: "not_implemented",
      message: `Bridge method ${name} is unavailable.`,
    },
  };
}

async function callApi<T>(name: ApiName, ...args: unknown[]): Promise<ApiResult<T>> {
  const fn = window.pywebview?.api?.[name];
  if (typeof fn !== "function") {
    return notImplemented(name);
  }
  try {
    const result = (await fn(...args)) as ApiResult<T>;
    if (!result || typeof result !== "object" || !("ok" in result)) {
      return {
        ok: false,
        error: {
          code: "unknown_error",
          message: `Bridge method ${name} returned an invalid payload.`,
        },
      };
    }
    return result;
  } catch (error) {
    return {
      ok: false,
      error: {
        code: "unknown_error",
        message: error instanceof Error ? error.message : String(error),
      },
    };
  }
}

export const bridge = {
  getBootstrap: () => callApi<BootstrapDTO>("get_bootstrap"),
  chooseConfigDirectory: () => callApi<string | null>("choose_config_directory"),
  loadDocument: (rootPath: string) => callApi<EditorDocumentDTO>("load_document", rootPath),
  saveDocument: (document: EditorDocumentDTO) =>
    callApi<{ document: EditorDocumentDTO }>("save_document", { document }),
  validateDocument: (document: EditorDocumentDTO) =>
    callApi<ValidationIssueDTO[]>("validate_document", document),
  listExternalFlows: (rootPath: string) =>
    callApi<ExternalFlowSummaryDTO[]>("list_external_flows", rootPath),
  importNodes: (payload: { root_path: string; flow_name: string; node_ids: string[] }) =>
    callApi<OperationNodeDTO[]>("import_nodes", payload),
  scanUnusedImages: (rootPath: string) =>
    callApi<UnusedImageDTO[]>("scan_unused_images", rootPath),
  deleteUnusedImages: (payload: { root_path: string; image_names: string[] }) =>
    callApi<DeleteUnusedImagesResultDTO>("delete_unused_images", payload),
  readClipboardNodes: () => callApi<NodeClipboardPayloadDTO | null>("read_clipboard_nodes"),
  writeClipboardNodes: (payload: NodeClipboardPayloadDTO) =>
    callApi<null>("write_clipboard_nodes", payload),
  captureRegion: (payload: Record<string, unknown>) =>
    callApi<Record<string, unknown> | null>("capture_region", payload),
  capturePoint: (prompt: string) =>
    callApi<{ x: number; y: number; point_text: string } | null>("capture_point", prompt),
  listVisibleWindows: () => callApi<VisibleWindowDTO[]>("list_visible_windows"),
  startRecording: (payload: Record<string, unknown>) =>
    callApi<RecordingSessionDTO>("start_recording", payload),
  pauseRecording: (payload: { session_id: string; paused: boolean }) =>
    callApi<RecordingSessionDTO>("pause_recording", payload),
  getRecordingStatus: (sessionId: string) =>
    callApi<RecordingSessionDTO>("get_recording_status", sessionId),
  stopRecording: (sessionId: string) =>
    callApi<RecordedNodesResultDTO>("stop_recording", sessionId),
  copyRecordedNodes: (payload: { session_id: string; node_ids: string[] | "all"; destination: "clipboard" }) =>
    callApi<null>("copy_recorded_nodes", payload),
  addVisualMark: (payload: Record<string, unknown>) =>
    callApi<RecordingSessionDTO>("add_visual_mark", payload),
};
