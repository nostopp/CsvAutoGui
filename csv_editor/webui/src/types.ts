export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export type ApiResult<T> =
  | {
      ok: true;
      data: T;
    }
  | {
      ok: false;
      error: ApiError;
    };

export type BranchConfigDTO = {
  trigger: string;
  mode: string;
  primary_target: string;
  secondary_target: string;
};

export type OperationNodeDTO = {
  node_id: string;
  index: number;
  operation: string;
  param_text: string;
  wait_value: string;
  wait_random: string;
  search_target: string;
  region_text: string;
  confidence_text: string;
  retry_value: string;
  retry_random: string;
  pic_range_random: boolean;
  move_time: string;
  jump_mark: string;
  disable_grayscale: boolean;
  note: string;
  branch: BranchConfigDTO;
  raw_extra: Record<string, string>;
};

export type FlowDocumentDTO = {
  filename: string;
  nodes: OperationNodeDTO[];
};

export type EditorDocumentDTO = {
  root_path: string;
  flows: FlowDocumentDTO[];
  state: {
    selected_flow: string;
    selected_node_id: string | null;
  };
};

export type ValidationIssueDTO = {
  severity: "error" | "warning" | "info" | string;
  flow_name: string;
  node_id: string | null;
  message: string;
};

export type UnusedImageDTO = {
  image_name: string;
  image_path: string;
};

export type DeleteUnusedImagesResultDTO = {
  deleted: string[];
  missing: string[];
  failed: {
    image_name: string;
    reason: string;
  }[];
};

export type ExternalFlowSummaryDTO = {
  root_path: string;
  flow_name: string;
  node_count: number;
};

export type NodeClipboardPayloadDTO = {
  version: number;
  source_root: string;
  source_flow: string;
  nodes: OperationNodeDTO[];
};

export type BootstrapDTO = {
  app_name: string;
  app_version?: string;
  initial_root_path: string | null;
  frontend_entry?: string | null;
  operation_types?: string[];
  capabilities?: Record<string, boolean>;
  supports_native_capture?: boolean;
  supports_recording?: boolean;
};

export type VisibleWindowDTO = {
  hwnd: number;
  title: string;
  process_name: string;
  class_name: string;
  display_text?: string;
};

export type RecordingSessionDTO = {
  session_id: string | null;
  status: string;
  target_window: {
    hwnd: number;
    title: string;
    process_name: string;
    class_name: string;
  } | null;
  coordinate_mode?: "screen" | "window" | string;
  match_child_window?: boolean;
  overlay_visible?: boolean;
  capture_paused?: boolean;
  ignored_region_count?: number;
  assistant_suppressing_events?: boolean;
  buffered_event_count: number;
  message: string | null;
  source_root?: string | null;
  source_flow?: string | null;
  review_ready?: boolean;
  close_protected?: boolean;
  stop_reason?: string | null;
};

export type RecordingReviewRowDTO = {
  source: string;
  semantic: string;
  node_text: string;
  target_text: string;
  region_text: string;
  strategy_text: string;
  wait_text: string;
  note_text: string;
};

export type RecordedNodesResultDTO = {
  session: RecordingSessionDTO;
  nodes: OperationNodeDTO[];
  review_rows: RecordingReviewRowDTO[];
  summary: {
    total: number;
    visual_count: number;
    wait_count: number;
    locator_count: number;
    input_count: number;
  };
};
