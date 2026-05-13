import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { bridge } from "./bridge";
import { buildCsvPreview } from "./csvPreview";
import {
  createNodeForOperation,
  getAllowedHelpers,
  getBranchOptions,
  getBranchPrimaryLabel,
  getBranchSecondaryLabel,
  hasVisibleField,
  getNodeRowView,
  getOperationEntries,
  getOperationMeta,
  getParamEditorConfig,
  getSearchTargetLabel,
  normalizeNodeForOperation,
} from "./editorSemantics";
import {
  createEditorSelection,
  createEditorTransaction,
  nodeFieldMergeKey,
  type EditorSelectionDTO,
  type EditorTransaction,
} from "./editorCommands";
import {
  applyEditorTransaction,
  canRedoEditorHistory,
  canUndoEditorHistory,
  cloneEditorDocument,
  createEditorHistoryState,
  isEditorHistoryClean,
  normalizeEditorDocument,
  redoEditorHistory,
  resetEditorHistoryState,
  undoEditorHistory,
} from "./editorHistory";
import type {
  BootstrapDTO,
  EditorDocumentDTO,
  FlowDocumentDTO,
  NodeClipboardPayloadDTO,
  OperationNodeDTO,
  RecordingReviewRowDTO,
  RecordingSessionDTO,
  UnusedImageDTO,
  ValidationIssueDTO,
  VisibleWindowDTO,
} from "./types";

type Notice = { tone: "idle" | "success" | "warning" | "error"; text: string };
type ToolWindow = "none" | "csv_preview" | "unused_assets";

type ImportDialogState = {
  open: boolean;
  rootPath: string;
  document: EditorDocumentDTO | null;
  selectedFlow: string | null;
  selectedNodeIds: string[];
};

type RecordingDialogState = {
  open: boolean;
  windows: VisibleWindowDTO[];
  coordinateMode: "screen" | "window";
  selectedWindowHwnd: string;
  matchChildWindow: boolean;
  session: RecordingSessionDTO | null;
  recordedNodes: OperationNodeDTO[];
  selectedRecordedNodeIds: string[];
  reviewRows: RecordingReviewRowDTO[];
  summary: {
    total: number;
    visual_count: number;
    wait_count: number;
    locator_count: number;
    input_count: number;
  } | null;
};

type OcrCandidateDialogState = {
  open: boolean;
  targetFlow: string | null;
  targetNodeId: string | null;
  regionText: string;
  candidates: string[];
  selected: string;
};

type ImageLightboxState = {
  src: string;
  title: string;
};

type SelectionGesture = {
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
};

type SelectionClickResult<T extends string> = {
  selectedIds: T[];
  anchorId: T | null;
};

const EMPTY_BRANCH = {
  trigger: "none",
  mode: "none",
  primary_target: "",
  secondary_target: "",
};

const EMPTY_NODE: OperationNodeDTO = {
  node_id: "",
  index: 0,
  operation: "click",
  param_text: "",
  wait_value: "",
  wait_random: "",
  search_target: "",
  region_text: "",
  confidence_text: "",
  retry_value: "",
  retry_random: "",
  pic_range_random: false,
  move_time: "",
  jump_mark: "",
  disable_grayscale: false,
  note: "",
  branch: EMPTY_BRANCH,
  raw_extra: {},
};

function cloneDocument<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function fileUrl(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }
  const normalized = path.replaceAll("\\", "/");
  return normalized.startsWith("file://") ? normalized : `file:///${normalized}`;
}

function uniqueNodeId(): string {
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
}

function summarizeNode(node: OperationNodeDTO): string {
  return getNodeRowView(node).summary;
}

function reindexFlow(flow: FlowDocumentDTO): FlowDocumentDTO {
  return {
    ...flow,
    nodes: flow.nodes.map((node, index) => ({
      ...node,
      index: index + 1,
    })),
  };
}

function flowByName(document: EditorDocumentDTO | null, filename: string | null): FlowDocumentDTO | null {
  if (!document || !filename) {
    return null;
  }
  return document.flows.find((flow) => flow.filename === filename) ?? null;
}

function imagePathForNode(document: EditorDocumentDTO | null, node: OperationNodeDTO | null): string | null {
  if (!document || !node || !node.search_target) {
    return null;
  }
  if (node.operation !== "pic") {
    return null;
  }
  return `${document.root_path}\\${node.search_target}`;
}

function cloneNodesForInsert(nodes: OperationNodeDTO[], targetFlow: FlowDocumentDTO): OperationNodeDTO[] {
  const existingMarks = new Set(targetFlow.nodes.map((node) => node.jump_mark.trim()).filter(Boolean));
  const renamedMarks = new Map<string, string>();
  const usedMarks = new Set(existingMarks);

  const cloned = nodes.map((node) => {
    const copy = cloneDocument(node);
    copy.node_id = uniqueNodeId();
    copy.index = 0;
    if (copy.jump_mark.trim()) {
      let candidate = copy.jump_mark.trim();
      let suffix = 1;
      while (usedMarks.has(candidate)) {
        candidate = `${copy.jump_mark.trim()}_copy${suffix++}`;
      }
      if (candidate !== copy.jump_mark.trim()) {
        renamedMarks.set(copy.jump_mark.trim(), candidate);
      }
      usedMarks.add(candidate);
      copy.jump_mark = candidate;
    }
    return copy;
  });

  for (const node of cloned) {
    if (node.operation === "jmp" && renamedMarks.has(node.param_text.trim())) {
      node.param_text = renamedMarks.get(node.param_text.trim()) ?? node.param_text;
    }
    if (node.branch.mode === "jump_pair") {
      if (renamedMarks.has(node.branch.primary_target.trim())) {
        node.branch.primary_target = renamedMarks.get(node.branch.primary_target.trim()) ?? node.branch.primary_target;
      }
      if (renamedMarks.has(node.branch.secondary_target.trim())) {
        node.branch.secondary_target = renamedMarks.get(node.branch.secondary_target.trim()) ?? node.branch.secondary_target;
      }
    }
  }
  return cloned;
}

function moveSelectedNodes(nodes: OperationNodeDTO[], selectedIds: string[], direction: -1 | 1): OperationNodeDTO[] {
  const selected = new Set(selectedIds);
  const reordered = [...nodes];
  if (direction < 0) {
    for (let index = 1; index < reordered.length; index += 1) {
      if (selected.has(reordered[index].node_id) && !selected.has(reordered[index - 1].node_id)) {
        [reordered[index - 1], reordered[index]] = [reordered[index], reordered[index - 1]];
      }
    }
    return reordered;
  }
  for (let index = reordered.length - 2; index >= 0; index -= 1) {
    if (selected.has(reordered[index].node_id) && !selected.has(reordered[index + 1].node_id)) {
      [reordered[index], reordered[index + 1]] = [reordered[index + 1], reordered[index]];
    }
  }
  return reordered;
}

function labelFromPath(path: string | null | undefined): string {
  if (!path) {
    return "未加载配置";
  }
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function describeFlow(flow: FlowDocumentDTO): string {
  const lower = flow.filename.toLowerCase();
  if (lower.includes("main")) {
    return "主流程";
  }
  if (lower.includes("battle")) {
    return "战斗流程";
  }
  if (lower.includes("return")) {
    return "返回流程";
  }
  if (lower.includes("pending")) {
    return "暂存流程";
  }
  return flow.nodes.length <= 12 ? "子流程" : "自动化流程";
}

function summarizeBranch(node: OperationNodeDTO | null): string {
  if (!node) {
    return "未配置分支";
  }
  const targets = [node.branch.primary_target, node.branch.secondary_target].filter(Boolean).join(" / ");
  if (node.branch.mode === "none" && node.branch.trigger === "none") {
    return "未配置分支";
  }
  const details = [
    node.branch.trigger !== "none" ? `触发 ${node.branch.trigger}` : "",
    node.branch.mode !== "none" ? `模式 ${node.branch.mode}` : "",
    targets,
  ]
    .filter(Boolean)
    .join(" · ");
  return details || "未配置分支";
}

function compactLocator(node: OperationNodeDTO): string {
  return getNodeRowView(node).locator_text;
}

function compactRegion(node: OperationNodeDTO): string {
  return getNodeRowView(node).region_text;
}

function compactTiming(node: OperationNodeDTO): string {
  return getNodeRowView(node).timing_text;
}

function compactBranch(node: OperationNodeDTO): string {
  return getNodeRowView(node).branch_text;
}

function compactSummary(node: OperationNodeDTO): string {
  return getNodeRowView(node).secondary_text;
}

function resolveSelectionClick<T extends string>(
  orderedIds: readonly T[],
  currentSelectedIds: readonly T[],
  clickedId: T,
  anchorId: T | null,
  gesture: SelectionGesture,
  options?: { allowEmpty?: boolean },
): SelectionClickResult<T> {
  const allowEmpty = options?.allowEmpty ?? true;
  const modifier = gesture.ctrlKey || gesture.metaKey;
  const selectedSet = new Set(currentSelectedIds.filter((id) => orderedIds.includes(id)));
  const anchorIndex = anchorId ? orderedIds.indexOf(anchorId) : -1;
  const clickedIndex = orderedIds.indexOf(clickedId);

  if (gesture.shiftKey && anchorIndex >= 0 && clickedIndex >= 0) {
    const start = Math.min(anchorIndex, clickedIndex);
    const end = Math.max(anchorIndex, clickedIndex);
    const rangeIds = orderedIds.slice(start, end + 1);
    if (modifier) {
      for (const id of rangeIds) {
        selectedSet.add(id);
      }
      return {
        selectedIds: orderedIds.filter((id) => selectedSet.has(id)),
        anchorId,
      };
    }
    return {
      selectedIds: [...rangeIds],
      anchorId,
    };
  }

  if (modifier) {
    if (selectedSet.has(clickedId)) {
      selectedSet.delete(clickedId);
    } else {
      selectedSet.add(clickedId);
    }
    if (!allowEmpty && !selectedSet.size) {
      selectedSet.add(clickedId);
    }
    return {
      selectedIds: orderedIds.filter((id) => selectedSet.has(id)),
      anchorId: clickedId,
    };
  }

  return {
    selectedIds: [clickedId],
    anchorId: clickedId,
  };
}

function parseConfidence(value: string): number {
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(1, numeric));
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

const EMPTY_OCR_CANDIDATE_DIALOG: OcrCandidateDialogState = {
  open: false,
  targetFlow: null,
  targetNodeId: null,
  regionText: "",
  candidates: [],
  selected: "",
};

const COMMAND_GROUP_STYLE: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  flexWrap: "wrap",
};

const COMMAND_LABEL_STYLE: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "#627277",
};

const COMPACT_BUTTON_STYLE: CSSProperties = {
  minHeight: 30,
  padding: "6px 10px",
  borderRadius: 10,
  fontSize: 12,
  fontWeight: 700,
};

const TABLE_HEADER_CELL_STYLE: CSSProperties = {
  padding: "8px 10px",
  fontSize: 11,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
};

const TABLE_BODY_CELL_STYLE: CSSProperties = {
  padding: "6px 8px",
  fontSize: 12,
  lineHeight: 1.2,
};

const SECONDARY_TEXT_STYLE: CSSProperties = {
  fontSize: 11,
  color: "#627277",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const TABLE_SINGLE_LINE_STYLE: CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  display: "block",
};

const DENSE_SECTION_STYLE: CSSProperties = {
  padding: "12px 13px",
  gap: 10,
  borderRadius: 14,
};

export default function App() {
  const [bootstrap, setBootstrap] = useState<BootstrapDTO | null>(null);
  const [history, setHistory] = useState(() => createEditorHistoryState(null));
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [nodeSelectionAnchorId, setNodeSelectionAnchorId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [flowQuery, setFlowQuery] = useState("");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [createOperation, setCreateOperation] = useState("click");
  const [activeToolWindow, setActiveToolWindow] = useState<ToolWindow>("none");
  const [issues, setIssues] = useState<ValidationIssueDTO[]>([]);
  const [unusedImages, setUnusedImages] = useState<UnusedImageDTO[]>([]);
  const [selectedUnusedImageNames, setSelectedUnusedImageNames] = useState<string[]>([]);
  const [unusedImageSelectionAnchor, setUnusedImageSelectionAnchor] = useState<string | null>(null);
  const [previewImagePath, setPreviewImagePath] = useState<string | null>(null);
  const [imageLightbox, setImageLightbox] = useState<ImageLightboxState | null>(null);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const [notice, setNotice] = useState<Notice>({ tone: "idle", text: "正在等待编辑器桥接启动..." });
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [importDialog, setImportDialog] = useState<ImportDialogState>({
    open: false,
    rootPath: "",
    document: null,
    selectedFlow: null,
    selectedNodeIds: [],
  });
  const [importSelectionAnchorId, setImportSelectionAnchorId] = useState<string | null>(null);
  const [recordingDialog, setRecordingDialog] = useState<RecordingDialogState>({
    open: false,
    windows: [],
    coordinateMode: "screen",
    selectedWindowHwnd: "",
    matchChildWindow: false,
    session: null,
    recordedNodes: [],
    selectedRecordedNodeIds: [],
    reviewRows: [],
    summary: null,
  });
  const [recordedSelectionAnchorId, setRecordedSelectionAnchorId] = useState<string | null>(null);
  const [ocrCandidateDialog, setOcrCandidateDialog] = useState<OcrCandidateDialogState>(EMPTY_OCR_CANDIDATE_DIALOG);
  const document = history.present;

  useEffect(() => {
    void initialize();
  }, []);

  useEffect(() => {
    if (!recordingDialog.session?.session_id || !["recording", "paused"].includes(recordingDialog.session.status)) {
      return;
    }
    const handle = window.setInterval(async () => {
      const result = await bridge.getRecordingStatus(recordingDialog.session?.session_id ?? "");
      if (result.ok) {
        if (result.data.status === "stopped" && result.data.review_ready && recordingDialog.session?.session_id) {
          const stoppedResult = await bridge.stopRecording(recordingDialog.session.session_id);
          if (stoppedResult.ok) {
            setRecordingDialog((current) => ({
              ...current,
              session: stoppedResult.data.session,
              recordedNodes: stoppedResult.data.nodes,
              selectedRecordedNodeIds: stoppedResult.data.nodes.map((node) => node.node_id),
              reviewRows: stoppedResult.data.review_rows,
              summary: stoppedResult.data.summary,
            }));
            setRecordedSelectionAnchorId(stoppedResult.data.nodes[0]?.node_id ?? null);
          } else {
            setRecordingDialog((current) => ({ ...current, session: result.data }));
          }
          return;
        }
        setRecordingDialog((current) => ({ ...current, session: result.data }));
      }
    }, 1000);
    return () => window.clearInterval(handle);
  }, [recordingDialog.session?.session_id, recordingDialog.session?.status, recordingDialog.session?.review_ready]);

  useEffect(() => {
    const sessionId = recordingDialog.session?.session_id;
    if (!sessionId || recordingDialog.session?.status !== "stopped" || recordingDialog.recordedNodes.length > 0) {
      return;
    }

    let cancelled = false;
    void (async () => {
      const result = await bridge.stopRecording(sessionId);
      if (cancelled) {
        return;
      }
      if (!result.ok) {
        setNotice({ tone: "error", text: result.error.message });
        return;
      }
      setRecordingDialog((current) => ({
        ...current,
        session: result.data.session,
        recordedNodes: result.data.nodes,
        reviewRows: result.data.review_rows,
        summary: result.data.summary,
      }));
    })();

    return () => {
      cancelled = true;
    };
  }, [recordingDialog.recordedNodes.length, recordingDialog.session?.session_id, recordingDialog.session?.status]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) {
        return;
      }
      const modifier = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (modifier && key === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        return;
      }
      if (modifier && key === "y") {
        event.preventDefault();
        handleRedo();
        return;
      }
      if (modifier && key === "c" && selectedNodeIds.length) {
        event.preventDefault();
        void copySelection();
        return;
      }
      if (modifier && key === "v" && document) {
        event.preventDefault();
        void pasteSelection();
        return;
      }
      if ((key === "delete" || key === "backspace") && selectedNodeIds.length) {
        event.preventDefault();
        deleteNodes();
        return;
      }
      if (key === "escape") {
        if (ocrCandidateDialog.open) {
          setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
          return;
        }
        if (activeToolWindow !== "none") {
          setActiveToolWindow("none");
          return;
        }
        if (recordingDialog.open && (!recordingDialog.session || !["recording", "paused"].includes(recordingDialog.session.status))) {
          setRecordingDialog((current) => ({ ...current, open: false }));
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    activeToolWindow,
    document,
    ocrCandidateDialog.open,
    recordingDialog.open,
    recordingDialog.session,
    selectedNodeIds,
  ]);

  const currentFlow = useMemo(
    () => flowByName(document, document?.state.selected_flow ?? null),
    [document],
  );

  const activeNode = useMemo(() => {
    if (!currentFlow || !document?.state.selected_node_id) {
      return null;
    }
    return currentFlow.nodes.find((node) => node.node_id === document.state.selected_node_id) ?? null;
  }, [currentFlow, document?.state.selected_node_id]);

  const visibleNodes = useMemo(() => {
    if (!currentFlow) {
      return [];
    }
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return currentFlow.nodes;
    }
    return currentFlow.nodes.filter((node) => {
      const haystack = [node.index, getNodeRowView(node).search_text].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [currentFlow, searchQuery]);
  const importFlow = useMemo(
    () => flowByName(importDialog.document, importDialog.selectedFlow),
    [importDialog.document, importDialog.selectedFlow],
  );
  const importFlowNodes = useMemo(() => importFlow?.nodes ?? [], [importFlow]);
  const unusedImageNames = useMemo(() => unusedImages.map((image) => image.image_name), [unusedImages]);
  const recordedNodeIds = useMemo(
    () => recordingDialog.recordedNodes.map((node) => node.node_id),
    [recordingDialog.recordedNodes],
  );

  const visibleFlows = useMemo(() => {
    const flows = document?.flows ?? [];
    const query = flowQuery.trim().toLowerCase();
    if (!query) {
      return flows;
    }
    return flows.filter((flow) => {
      const nodeHaystack = flow.nodes
        .map((node) => getNodeRowView(node).search_text)
        .join(" ");
      const haystack = [flow.filename, describeFlow(flow), flow.nodes.length, nodeHaystack].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [document, flowQuery]);

  const csvPreview = useMemo(() => (currentFlow ? buildCsvPreview(currentFlow) : ""), [currentFlow]);
  const operationEntries = useMemo(() => getOperationEntries(bootstrap), [bootstrap]);
  const jumpTargetOptions = useMemo(
    () => (currentFlow ? currentFlow.nodes.map((node) => node.jump_mark.trim()).filter(Boolean) : []),
    [currentFlow],
  );
  const flowNameOptions = useMemo(() => (document?.flows ?? []).map((flow) => flow.filename), [document]);
  const branchTargetOptions = useMemo(
    () => getBranchOptions(flowNameOptions, jumpTargetOptions),
    [flowNameOptions, jumpTargetOptions],
  );
  const activeNodeMeta = useMemo(
    () => (activeNode ? getOperationMeta(bootstrap, activeNode.operation) : null),
    [activeNode, bootstrap],
  );
  const activeRowView = useMemo(() => (activeNode ? getNodeRowView(activeNode) : null), [activeNode]);
  const paramEditorConfig = useMemo(
    () => (activeNode ? getParamEditorConfig(activeNode.operation, jumpTargetOptions) : null),
    [activeNode, jumpTargetOptions],
  );
  const activeHelpers = useMemo(
    () => (activeNode ? getAllowedHelpers(bootstrap, activeNode.operation) : []),
    [activeNode, bootstrap],
  );
  const dirty = useMemo(() => !isEditorHistoryClean(history), [history]);
  const issueSummary = useMemo(
    () =>
      issues.reduce(
        (summary, issue) => {
          if (issue.severity === "error") {
            summary.error += 1;
          } else if (issue.severity === "warning") {
            summary.warning += 1;
          } else {
            summary.info += 1;
          }
          return summary;
        },
        { error: 0, warning: 0, info: 0 },
      ),
    [issues],
  );
  const quickFilters = useMemo(() => {
    if (!currentFlow) {
      return [];
    }
    const preferred = ["ocr", "pic", "click", "jmp", "write", "notify"];
    return preferred
      .filter((operation) => currentFlow.nodes.some((node) => node.operation === operation))
      .map((operation) => ({
        operation,
        count: currentFlow.nodes.filter((node) => node.operation === operation).length,
      }));
  }, [currentFlow]);
  const totalNodes = useMemo(
    () => document?.flows.reduce((count, flow) => count + flow.nodes.length, 0) ?? 0,
    [document],
  );

  async function initialize() {
    const maxAttempts = 20;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const result = await bridge.getBootstrap();
      if (result.ok) {
        setBootstrap(result.data);
        const initialOperation = result.data.operation_types?.[0];
        if (initialOperation) {
          setCreateOperation(initialOperation);
        }
        setNotice({ tone: "success", text: "编辑器桥接已就绪。" });
        if (result.data.initial_root_path) {
          await openDocument(result.data.initial_root_path);
        }
        return;
      }

      const shouldRetry =
        result.error.code === "not_implemented" ||
        result.error.message.includes("get_bootstrap is unavailable") ||
        result.error.message.includes("get_bootstrap");
      if (!shouldRetry || attempt === maxAttempts) {
        setNotice({ tone: "error", text: result.error.message });
        return;
      }

      await new Promise((resolve) => window.setTimeout(resolve, 150));
    }
  }

  function setBusyFlag(name: string, value: boolean) {
    setBusy((current) => ({ ...current, [name]: value }));
  }

  function replaceDraftDocument(target: EditorDocumentDTO, source: EditorDocumentDTO) {
    target.root_path = source.root_path;
    target.flows = cloneDocument(source.flows);
    target.state = cloneDocument(source.state);
  }

  function replaceDocument(next: EditorDocumentDTO) {
    setHistory(resetEditorHistoryState(next));
  }

  function updateDocumentView(mutator: (draft: EditorDocumentDTO) => void) {
    if (!document) {
      return;
    }
    const next = normalizeEditorDocument(cloneEditorDocument(document));
    mutator(next);
    setHistory((current) => ({
      ...current,
      present: next,
    }));
  }

  function applyTransaction(transaction: EditorTransaction, selectionBefore?: EditorSelectionDTO) {
    const result = applyEditorTransaction(history, transaction, selectionBefore ?? createEditorSelection(selectedNodeIds));
    setHistory(result.history);
    setSelectedNodeIds(result.selection.selectedNodeIds);
    setNodeSelectionAnchorId(result.history.present?.state.selected_node_id ?? result.selection.selectedNodeIds[0] ?? null);
  }

  function commitDocument(
    label: string,
    mutator: (draft: EditorDocumentDTO) => void,
    options?: {
      mergeKey?: string | null;
      selectionAfter?: string[];
      selectionBefore?: string[];
    },
  ) {
    if (!document) {
      return;
    }
    const before = normalizeEditorDocument(cloneEditorDocument(document));
    const after = normalizeEditorDocument(cloneEditorDocument(document));
    mutator(after);
    const transaction = createEditorTransaction(
      label,
      [
        {
          id: `${label}-${Date.now().toString(16)}`,
          label,
          mergeKey: options?.mergeKey ?? null,
          apply(draft) {
            replaceDraftDocument(draft, after);
          },
          revert(draft) {
            replaceDraftDocument(draft, before);
          },
        },
      ],
      {
        mergeKey: options?.mergeKey ?? null,
        selectionAfter: options?.selectionAfter ? createEditorSelection(options.selectionAfter) : null,
      },
    );
    applyTransaction(
      transaction,
      createEditorSelection(options?.selectionBefore ?? selectedNodeIds),
    );
  }

  async function openDocument(rootPath: string) {
    setBusyFlag("load", true);
    const result = await bridge.loadDocument(rootPath);
    setBusyFlag("load", false);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setIssues([]);
    setUnusedImages([]);
    setSelectedUnusedImageNames([]);
    setUnusedImageSelectionAnchor(null);
    setPreviewImagePath(null);
    setSelectedNodeIds(result.data.state.selected_node_id ? [result.data.state.selected_node_id] : []);
    setNodeSelectionAnchorId(result.data.state.selected_node_id ?? null);
    replaceDocument(result.data);
    setNotice({ tone: "success", text: `已加载配置：${rootPath}` });
  }

  async function handleChooseDirectory() {
    const result = await bridge.chooseConfigDirectory();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    if (result.data) {
      await openDocument(result.data);
    }
  }

  async function handleWindowMinimize() {
    const result = await bridge.minimizeWindow();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
    }
  }

  async function handleWindowToggleMaximize() {
    const result = await bridge.toggleMaximizeWindow();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setWindowMaximized(Boolean(result.data?.maximized));
  }

  async function handleWindowClose() {
    const result = await bridge.closeWindow();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
    }
  }

  async function handleSave() {
    if (!document) {
      return;
    }
    setBusyFlag("save", true);
    const result = await bridge.saveDocument(document);
    setBusyFlag("save", false);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    replaceDocument(result.data.document);
    setNotice({ tone: "success", text: "CSV 已保存。" });
  }

  async function handleValidate() {
    if (!document) {
      return;
    }
    setBusyFlag("validate", true);
    const result = await bridge.validateDocument(document);
    setBusyFlag("validate", false);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setIssues(result.data);
    setNotice({ tone: "success", text: `校验完成，共 ${result.data.length} 个问题。` });
  }

  async function handleScanImages() {
    if (!document) {
      return;
    }
    setBusyFlag("scan", true);
    const result = await bridge.scanUnusedImages(document.root_path);
    setBusyFlag("scan", false);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setUnusedImages(result.data);
    setSelectedUnusedImageNames([]);
    setUnusedImageSelectionAnchor(null);
    setPreviewImagePath(result.data[0]?.image_path ?? null);
    setNotice({ tone: "success", text: `发现 ${result.data.length} 张未使用图片。` });
  }

  function handleUnusedImageSelection(imageName: string, gesture: SelectionGesture) {
    const result = resolveSelectionClick(
      unusedImageNames,
      selectedUnusedImageNames,
      imageName,
      unusedImageSelectionAnchor,
      gesture,
      { allowEmpty: true },
    );
    setSelectedUnusedImageNames(result.selectedIds);
    setUnusedImageSelectionAnchor(result.anchorId);
    const image = unusedImages.find((item) => item.image_name === imageName);
    if (image) {
      setPreviewImagePath(image.image_path);
    }
  }

  async function openUnusedAssetsWorkspace() {
    if (!document) {
      return;
    }
    if (!unusedImages.length) {
      await handleScanImages();
    }
    setActiveToolWindow("unused_assets");
  }

  async function deleteSelectedUnusedImages() {
    if (!document || !selectedUnusedImageNames.length) {
      return;
    }
    setBusyFlag("delete_unused", true);
    const result = await bridge.deleteUnusedImages({
      root_path: document.root_path,
      image_names: selectedUnusedImageNames,
    });
    setBusyFlag("delete_unused", false);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    const deleted = new Set(result.data.deleted);
    const nextUnusedImages = unusedImages.filter((image) => !deleted.has(image.image_name));
    setUnusedImages(nextUnusedImages);
    setSelectedUnusedImageNames((current) => current.filter((name) => !deleted.has(name)));
    setUnusedImageSelectionAnchor(null);
    setPreviewImagePath((current) => {
      const stillExists = nextUnusedImages.some((image) => image.image_path === current);
      if (stillExists) {
        return current;
      }
      return nextUnusedImages[0]?.image_path ?? null;
    });
    const parts = [
      result.data.deleted.length ? `已删 ${result.data.deleted.length}` : "",
      result.data.missing.length ? `缺失 ${result.data.missing.length}` : "",
      result.data.failed.length ? `失败 ${result.data.failed.length}` : "",
    ].filter(Boolean);
    setNotice({ tone: result.data.failed.length ? "warning" : "success", text: `图片清理结果：${parts.join(" · ")}` });
  }

  function handleUndo() {
    if (!document || !canUndoEditorHistory(history)) {
      return;
    }
    const result = undoEditorHistory(history);
    setHistory(result.history);
    setSelectedNodeIds(result.selection?.selectedNodeIds ?? []);
    setNodeSelectionAnchorId(result.history.present?.state.selected_node_id ?? result.selection?.selectedNodeIds?.[0] ?? null);
  }

  function handleRedo() {
    if (!canRedoEditorHistory(history)) {
      return;
    }
    const result = redoEditorHistory(history);
    setHistory(result.history);
    setSelectedNodeIds(result.selection?.selectedNodeIds ?? []);
    setNodeSelectionAnchorId(result.history.present?.state.selected_node_id ?? result.selection?.selectedNodeIds?.[0] ?? null);
  }

  function selectFlow(filename: string) {
    if (!document) {
      return;
    }
    const flow = document.flows.find((item) => item.filename === filename);
    if (!flow) {
      return;
    }
    const nextNodeId = flow.nodes[0]?.node_id ?? null;
    updateDocumentView((draft) => {
      draft.state.selected_flow = filename;
      draft.state.selected_node_id = nextNodeId;
    });
    setSelectedNodeIds(nextNodeId ? [nextNodeId] : []);
    setNodeSelectionAnchorId(nextNodeId);
  }

  function handleNodeSelection(nodeId: string, gesture: SelectionGesture) {
    if (!document) {
      return;
    }
    const result = resolveSelectionClick(
      visibleNodes.map((node) => node.node_id),
      selectedNodeIds,
      nodeId,
      nodeSelectionAnchorId,
      gesture,
      { allowEmpty: false },
    );
    const nextActiveNodeId = result.selectedIds.includes(nodeId) ? nodeId : result.selectedIds[result.selectedIds.length - 1] ?? nodeId;
    updateDocumentView((draft) => {
      draft.state.selected_node_id = nextActiveNodeId;
    });
    setSelectedNodeIds(result.selectedIds);
    setNodeSelectionAnchorId(result.anchorId ?? nextActiveNodeId);
  }

  function activateNode(nodeId: string) {
    if (!document) {
      return;
    }
    updateDocumentView((draft) => {
      draft.state.selected_node_id = nodeId;
    });
    setSelectedNodeIds([nodeId]);
    setNodeSelectionAnchorId(nodeId);
  }

  function addNode(operation: string) {
    if (!document || !currentFlow) {
      return;
    }
    const newNode = cloneDocument(createNodeForOperation(operation));
    newNode.node_id = uniqueNodeId();
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "新增节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        const anchorIndex = flow.nodes.findIndex((node) => node.node_id === anchorId);
        const insertIndex = anchorIndex >= 0 ? anchorIndex + 1 : flow.nodes.length;
        flow.nodes.splice(insertIndex, 0, newNode);
        draft.state.selected_node_id = newNode.node_id;
      },
      { selectionAfter: [newNode.node_id] },
    );
    setSelectedNodeIds([newNode.node_id]);
    setNodeSelectionAnchorId(newNode.node_id);
    setNotice({ tone: "success", text: `已新增 ${getOperationMeta(bootstrap, operation).label} 节点。` });
  }

  function deleteNodes() {
    if (!document || !currentFlow) {
      return;
    }
    const nodeIds = selectedNodeIds.length ? selectedNodeIds : document.state.selected_node_id ? [document.state.selected_node_id] : [];
    if (!nodeIds.length) {
      return;
    }
    commitDocument(
      "删除节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        flow.nodes = flow.nodes.filter((node) => !nodeIds.includes(node.node_id));
        draft.state.selected_node_id = flow.nodes[0]?.node_id ?? null;
      },
      { selectionAfter: [] },
    );
    setSelectedNodeIds([]);
    setNodeSelectionAnchorId(null);
  }

  function moveSelection(direction: -1 | 1) {
    if (!document || !currentFlow) {
      return;
    }
    const orderedIndexes = currentFlow.nodes
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => selectedNodeIds.includes(node.node_id))
      .map(({ index }) => index);
    if (!orderedIndexes.length) {
      return;
    }
    const minIndex = Math.min(...orderedIndexes);
    const maxIndex = Math.max(...orderedIndexes);
    if (direction < 0 && minIndex === 0) {
      return;
    }
    if (direction > 0 && maxIndex === currentFlow.nodes.length - 1) {
      return;
    }
    commitDocument(
      direction < 0 ? "上移节点" : "下移节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        flow.nodes = moveSelectedNodes(flow.nodes, selectedNodeIds, direction);
      },
      { selectionAfter: [...selectedNodeIds] },
    );
  }

  async function copySelection() {
    if (!document || !currentFlow) {
      return;
    }
    const nodes = currentFlow.nodes.filter((node) => selectedNodeIds.includes(node.node_id));
    if (!nodes.length) {
      setNotice({ tone: "warning", text: "请先选择一个或多个节点。" });
      return;
    }
    const payload: NodeClipboardPayloadDTO = {
      version: 1,
      source_root: document.root_path,
      source_flow: currentFlow.filename,
      nodes,
    };
    const result = await bridge.writeClipboardNodes(payload);
    setNotice({
      tone: result.ok ? "success" : "error",
      text: result.ok ? `已复制 ${nodes.length} 个节点。` : result.error.message,
    });
  }

  async function pasteSelection() {
    if (!document || !currentFlow) {
      return;
    }
    const result = await bridge.readClipboardNodes();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    if (!result.data?.nodes?.length) {
      setNotice({ tone: "warning", text: "剪贴板中没有可用于编辑器的节点数据。" });
      return;
    }
    const cloned = cloneNodesForInsert(result.data.nodes, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "粘贴节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        const anchorIndex = flow.nodes.findIndex((node) => node.node_id === anchorId);
        const insertIndex = anchorIndex >= 0 ? anchorIndex + 1 : flow.nodes.length;
        flow.nodes.splice(insertIndex, 0, ...cloned);
        draft.state.selected_node_id = cloned[0]?.node_id ?? null;
      },
      { selectionAfter: cloned.map((node) => node.node_id) },
    );
    setSelectedNodeIds(cloned.map((node) => node.node_id));
    setNodeSelectionAnchorId(cloned[0]?.node_id ?? null);
    setNotice({ tone: "success", text: `已粘贴 ${cloned.length} 个节点。` });
  }

  function updateNodeField(field: keyof OperationNodeDTO, value: string | boolean) {
    if (!document || !activeNode) {
      return;
    }
    const activeId = activeNode.node_id;
    commitDocument(
      `编辑字段 ${String(field)}`,
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        const node = flow?.nodes.find((item) => item.node_id === activeId);
        if (!node) {
          return;
        }
        (node[field] as string | boolean) = value;
      },
      {
        mergeKey: nodeFieldMergeKey(document.state.selected_flow, activeId, field),
        selectionAfter: [activeId],
      },
    );
  }

  function changeNodeOperation(operation: string) {
    if (!document || !activeNode) {
      return;
    }
    const activeId = activeNode.node_id;
    commitDocument(
      "切换节点类型",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        const node = flow?.nodes.find((item) => item.node_id === activeId);
        if (!node) {
          return;
        }
        const normalized = normalizeNodeForOperation(node, operation);
        Object.assign(node, normalized);
      },
      {
        selectionAfter: [activeId],
      },
    );
  }

  function updateBranchField(field: keyof OperationNodeDTO["branch"], value: string) {
    if (!document || !activeNode) {
      return;
    }
    const activeId = activeNode.node_id;
    commitDocument(
      `编辑分支字段 ${String(field)}`,
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        const node = flow?.nodes.find((item) => item.node_id === activeId);
        if (!node) {
          return;
        }
        node.branch[field] = value;
      },
      {
        mergeKey: `branch:${document.state.selected_flow}:${activeId}:${field}`,
        selectionAfter: [activeId],
      },
    );
  }

  async function captureForNode(mode: "pic" | "ocr" | "point") {
    if (!document || !activeNode) {
      return;
    }
    if (mode === "point") {
      const result = await bridge.capturePoint("请为当前节点拾取屏幕坐标");
      if (!result.ok) {
        setNotice({ tone: "error", text: result.error.message });
        return;
      }
      if (!result.data) {
        return;
      }
      updateNodeField("param_text", result.data.point_text);
      setNotice({ tone: "success", text: `已回填坐标 ${result.data.point_text}。` });
      return;
    }

    const result = await bridge.captureRegion({
      prompt: mode === "pic" ? "请框选当前识图节点的截图区域" : "请框选当前 OCR 节点的识别区域",
      root_path: document.root_path,
      save_image: mode === "pic",
      ocr_preview: mode === "ocr",
    });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    if (!result.data) {
      return;
    }
    const regionText = String(result.data.region_text ?? "");
    const ocrCandidates = Array.isArray(result.data.ocr_candidates)
      ? result.data.ocr_candidates.map((candidate) => String(candidate).trim()).filter(Boolean)
      : [];
    let nextSearchTarget = activeNode.search_target;
    if (mode === "pic") {
      const imagePath = String(result.data.image_path ?? "");
      nextSearchTarget = imagePath.split(/[/\\]/).pop() ?? "";
    } else {
      const suggestedText = String(result.data.suggested_text ?? "");
      if (ocrCandidates.length > 1) {
        setOcrCandidateDialog({
          open: true,
          targetFlow: currentFlow?.filename ?? document.state.selected_flow,
          targetNodeId: activeNode.node_id,
          regionText,
          candidates: ocrCandidates,
          selected: ocrCandidates[0] ?? suggestedText,
        });
        return;
      } else if (suggestedText) {
        nextSearchTarget = suggestedText;
      }
    }
    const activeId = activeNode.node_id;
    commitDocument(
      mode === "pic" ? "回填识图区域" : "回填 OCR 区域",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        const node = flow?.nodes.find((item) => item.node_id === activeId);
        if (!node) {
          return;
        }
        node.region_text = regionText;
        node.search_target = nextSearchTarget;
      },
      { selectionAfter: [activeId] },
    );
    setNotice({ tone: "success", text: mode === "pic" ? "已回填识图区域。" : "已回填 OCR 区域。" });
  }

  async function openImportDialog() {
    setImportDialog({
      open: true,
      rootPath: "",
      document: null,
      selectedFlow: null,
      selectedNodeIds: [],
    });
    setImportSelectionAnchorId(null);
  }

  async function chooseImportDirectory() {
    const chosen = await bridge.chooseConfigDirectory();
    if (!chosen.ok || !chosen.data) {
      if (!chosen.ok) {
        setNotice({ tone: "error", text: chosen.error.message });
      }
      return;
    }
    const result = await bridge.loadDocument(chosen.data);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setImportDialog({
      open: true,
      rootPath: chosen.data,
      document: result.data,
      selectedFlow: result.data.flows[0]?.filename ?? null,
      selectedNodeIds: [],
    });
    setImportSelectionAnchorId(null);
  }

  function handleImportNodeSelection(nodeId: string, gesture: SelectionGesture) {
    const result = resolveSelectionClick(
      importFlowNodes.map((node) => node.node_id),
      importDialog.selectedNodeIds,
      nodeId,
      importSelectionAnchorId,
      gesture,
      { allowEmpty: true },
    );
    setImportDialog((current) => ({
      ...current,
      selectedNodeIds: result.selectedIds,
    }));
    setImportSelectionAnchorId(result.anchorId);
  }

  async function importSelectedNodes() {
    if (!document || !currentFlow || !importDialog.rootPath || !importDialog.selectedFlow || !importDialog.document) {
      return;
    }
    const sourceFlow = flowByName(importDialog.document, importDialog.selectedFlow);
    if (!sourceFlow) {
      setNotice({ tone: "error", text: `无法读取导入流程：${importDialog.selectedFlow}` });
      return;
    }
    const nodeIndexes = sourceFlow.nodes
      .filter((node) => importDialog.selectedNodeIds.includes(node.node_id))
      .map((node) => node.index);
    const result = await bridge.importNodes({
      root_path: importDialog.rootPath,
      flow_name: importDialog.selectedFlow,
      node_indexes: nodeIndexes,
    });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    const cloned = cloneNodesForInsert(result.data, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "导入节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        const anchorIndex = flow.nodes.findIndex((node) => node.node_id === anchorId);
        const insertIndex = anchorIndex >= 0 ? anchorIndex + 1 : flow.nodes.length;
        flow.nodes.splice(insertIndex, 0, ...cloned);
        draft.state.selected_node_id = cloned[0]?.node_id ?? null;
      },
      { selectionAfter: cloned.map((node) => node.node_id) },
    );
    setSelectedNodeIds(cloned.map((node) => node.node_id));
    setNodeSelectionAnchorId(cloned[0]?.node_id ?? null);
    setImportDialog((current) => ({ ...current, open: false }));
    setImportSelectionAnchorId(null);
    setNotice({ tone: "success", text: `已导入 ${cloned.length} 个节点。` });
  }

  async function openRecordingDialog() {
    const windows = await bridge.listVisibleWindows();
    setRecordingDialog((current) => ({
      ...current,
      open: true,
      windows: windows.ok ? windows.data : [],
      session: null,
      recordedNodes: [],
      selectedRecordedNodeIds: [],
      reviewRows: [],
      summary: null,
    }));
    setRecordedSelectionAnchorId(null);
    if (!windows.ok) {
      setNotice({ tone: "warning", text: windows.error.message });
    }
  }

  async function startRecording() {
    if (!document || !currentFlow) {
      return;
    }
    const payload: Record<string, unknown> = {
      source_root: document.root_path,
      source_flow: currentFlow.filename,
      coordinate_mode: recordingDialog.coordinateMode,
      match_child_window: recordingDialog.matchChildWindow,
    };
    if (recordingDialog.coordinateMode === "window" && recordingDialog.selectedWindowHwnd) {
      payload.target_window_hwnd = Number(recordingDialog.selectedWindowHwnd);
    }
    const result = await bridge.startRecording(payload);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setRecordingDialog((current) => ({
      ...current,
      session: result.data,
      recordedNodes: [],
      selectedRecordedNodeIds: [],
      reviewRows: [],
      summary: null,
    }));
    setRecordedSelectionAnchorId(null);
    setNotice({ tone: "success", text: "录制已开始。" });
  }

  async function toggleRecordingPaused(paused: boolean) {
    const sessionId = recordingDialog.session?.session_id;
    if (!sessionId) {
      return;
    }
    const result = await bridge.pauseRecording({ session_id: sessionId, paused });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setRecordingDialog((current) => ({ ...current, session: result.data }));
    setNotice({ tone: "success", text: paused ? "录制已暂停。" : "录制已继续。" });
  }

  async function stopRecording() {
    const sessionId = recordingDialog.session?.session_id;
    if (!sessionId) {
      return;
    }
    const result = await bridge.stopRecording(sessionId);
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setRecordingDialog((current) => ({
      ...current,
      session: result.data.session,
      recordedNodes: result.data.nodes,
      selectedRecordedNodeIds: result.data.nodes.map((node) => node.node_id),
      reviewRows: result.data.review_rows,
      summary: result.data.summary,
    }));
    setRecordedSelectionAnchorId(result.data.nodes[0]?.node_id ?? null);
    setNotice({ tone: "success", text: `录制得到 ${result.data.nodes.length} 个节点。` });
  }

  function confirmOcrCandidateDialog() {
    if (!ocrCandidateDialog.open) {
      return;
    }
    const selected = ocrCandidateDialog.selected.trim();
    if (!selected) {
      setNotice({ tone: "warning", text: "请先选择或输入一个 OCR 候选文本。" });
      return;
    }
    if (!document || !ocrCandidateDialog.targetFlow || !ocrCandidateDialog.targetNodeId) {
      setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
      return;
    }
    const { targetFlow, targetNodeId, regionText } = ocrCandidateDialog;
    commitDocument(
      "确认 OCR 候选",
      (draft) => {
        const flow = flowByName(draft, targetFlow);
        const node = flow?.nodes.find((item) => item.node_id === targetNodeId);
        if (!flow || !node) {
          return;
        }
        draft.state.selected_flow = targetFlow;
        draft.state.selected_node_id = targetNodeId;
        node.region_text = regionText;
        node.search_target = selected;
      },
      { selectionAfter: [targetNodeId] },
    );
    setSelectedNodeIds([targetNodeId]);
    setNodeSelectionAnchorId(targetNodeId);
    setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
    setNotice({ tone: "success", text: "已回填 OCR 文本与区域。" });
  }

  function closeRecordingDialog() {
    if (recordingDialog.session?.close_protected ?? ["recording", "paused"].includes(recordingDialog.session?.status ?? "")) {
      setNotice({ tone: "warning", text: "请先停止录制，再关闭录制窗口。" });
      return;
    }
    setRecordingDialog((current) => ({ ...current, open: false }));
  }

  async function copyRecordedNodes() {
    const sessionId = recordingDialog.session?.session_id;
    if (!sessionId) {
      return;
    }
    const selectedIds = recordingDialog.selectedRecordedNodeIds;
    const result = await bridge.copyRecordedNodes({
      session_id: sessionId,
      node_ids: selectedIds.length ? selectedIds : "all",
      destination: "clipboard",
    });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    const copiedCount = selectedIds.length || recordingDialog.recordedNodes.length;
    setNotice({ tone: "success", text: `已复制 ${copiedCount} 个录制节点。` });
  }

  function insertRecordedNodes() {
    if (!document || !currentFlow || !recordingDialog.recordedNodes.length) {
      return;
    }
    const cloned = cloneNodesForInsert(recordingDialog.recordedNodes, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "插入录制节点",
      (draft) => {
        const flow = flowByName(draft, draft.state.selected_flow);
        if (!flow) {
          return;
        }
        const anchorIndex = flow.nodes.findIndex((node) => node.node_id === anchorId);
        const insertIndex = anchorIndex >= 0 ? anchorIndex + 1 : flow.nodes.length;
        flow.nodes.splice(insertIndex, 0, ...cloned);
        draft.state.selected_node_id = cloned[0]?.node_id ?? null;
      },
      { selectionAfter: cloned.map((node) => node.node_id) },
    );
    setSelectedNodeIds(cloned.map((node) => node.node_id));
    setNodeSelectionAnchorId(cloned[0]?.node_id ?? null);
    setRecordingDialog((current) => ({
      ...current,
      open: false,
      recordedNodes: [],
      selectedRecordedNodeIds: [],
      session: null,
    }));
    setRecordedSelectionAnchorId(null);
    setNotice({ tone: "success", text: `已插入 ${cloned.length} 个录制节点。` });
  }

  function handleRecordedNodeSelection(nodeId: string, gesture: SelectionGesture) {
    const result = resolveSelectionClick(
      recordedNodeIds,
      recordingDialog.selectedRecordedNodeIds,
      nodeId,
      recordedSelectionAnchorId,
      gesture,
      { allowEmpty: true },
    );
    setRecordingDialog((current) => ({
      ...current,
      selectedRecordedNodeIds: result.selectedIds,
    }));
    setRecordedSelectionAnchorId(result.anchorId);
  }

  function issueTone(severity: string): string {
    switch (severity) {
      case "error":
        return "issue issue-error";
      case "warning":
        return "issue issue-warning";
      default:
        return "issue issue-info";
    }
  }

  const inspectorImage = fileUrl(imagePathForNode(document, activeNode));
  const previewImageUrl = fileUrl(previewImagePath);
  const configLabel = labelFromPath(document?.root_path);
  const selectedCount = selectedNodeIds.length || (activeNode ? 1 : 0);
  const confidenceValue = parseConfidence(activeNode?.confidence_text ?? "");
  const recordingSessionActive = Boolean(
    recordingDialog.session?.close_protected ?? (recordingDialog.session && ["recording", "paused"].includes(recordingDialog.session.status)),
  );
  const currentFlowSummary = currentFlow
    ? `${currentFlow.filename} · 可见 ${visibleNodes.length}/${currentFlow.nodes.length} 行`
    : "选择一个流程后开始编辑。";
  const showWaitFields = hasVisibleField(activeNodeMeta, "wait_value") || hasVisibleField(activeNodeMeta, "wait_random");
  const showRetryFields = hasVisibleField(activeNodeMeta, "retry_value") || hasVisibleField(activeNodeMeta, "retry_random");
  const showBranchFields = [
    "branch.trigger",
    "branch.mode",
    "branch.primary_target",
    "branch.secondary_target",
  ].some((field) => hasVisibleField(activeNodeMeta, field));
  const showMoveTimeField =
    activeNode?.operation !== "pic" &&
    activeNode?.operation !== "ocr" &&
    hasVisibleField(activeNodeMeta, "move_time");
  const inspectorImageTitle = activeNode?.search_target || "当前节点图片";
  const supportsWindowControls = Boolean(bootstrap?.capabilities?.window_controls);

  return (
    <div className="app-shell">
      <div className="editor-frame" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
        <div className="stage-shell" style={{ gap: 10 }}>
          <header className="topbar topbar-compact">
            <div className="topbar-copy topbar-copy-compact titlebar-drag-region pywebview-drag-region">
              <strong style={{ fontSize: 15, fontWeight: 800 }}>{bootstrap?.app_name ?? "CsvAutoGui 编辑器"}</strong>
              <span className="status-pill tone-idle">{configLabel}</span>
              <span style={COMMAND_LABEL_STYLE}>{document ? `${document.flows.length} 个流程 · ${totalNodes} 个节点` : "先打开一个配置目录"}</span>
            </div>

            <div className="topbar-actions topbar-actions-compact titlebar-button-region">
              <div style={COMMAND_GROUP_STYLE}>
                <button className="ghost-button accent-teal" style={COMPACT_BUTTON_STYLE} onClick={() => void handleChooseDirectory()}>
                  打开配置
                </button>
                <button
                  className="soft-button accent-teal"
                  style={COMPACT_BUTTON_STYLE}
                  onClick={() => void handleSave()}
                  disabled={!document || busy.save}
                >
                  保存 CSV
                </button>
                <button
                  className="ghost-button accent-amber"
                  style={COMPACT_BUTTON_STYLE}
                  onClick={() => void handleValidate()}
                  disabled={!document || busy.validate}
                >
                  校验
                </button>
                <button className="ghost-button" style={COMPACT_BUTTON_STYLE} onClick={() => void openUnusedAssetsWorkspace()} disabled={!document}>
                  图片管理
                </button>
                <button className="ghost-button" style={COMPACT_BUTTON_STYLE} onClick={() => setActiveToolWindow("csv_preview")} disabled={!document}>
                  CSV 预览
                </button>
                <button
                  className="ghost-button accent-amber"
                  style={COMPACT_BUTTON_STYLE}
                  onClick={() => void openRecordingDialog()}
                  disabled={!document}
                >
                  录制模式
                </button>
              </div>
              <span className={`status-pill tone-${notice.tone}`}>{notice.text}</span>
              <span className={`status-pill ${dirty ? "tone-warning" : "tone-success"}`}>{dirty ? "未保存" : "已保存"}</span>
              {supportsWindowControls && (
                <div className="window-controls">
                  <button type="button" className="window-control-button" title="最小化" onClick={() => void handleWindowMinimize()}>
                    _
                  </button>
                  <button
                    type="button"
                    className="window-control-button"
                    title={windowMaximized ? "还原" : "最大化"}
                    onClick={() => void handleWindowToggleMaximize()}
                  >
                    {windowMaximized ? "❐" : "□"}
                  </button>
                  <button type="button" className="window-control-button danger" title="关闭" onClick={() => void handleWindowClose()}>
                    ×
                  </button>
                </div>
              )}
            </div>
          </header>

          <section className={`workspace-grid compact-shell ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}>
            <aside className={`panel left-column ${leftCollapsed ? "collapsed-panel" : ""}`}>
              <div className="panel-header compact">
                <div>
                  <h2>流程</h2>
                  <p>切换 CSV 与查看校验问题。</p>
                </div>
                <div className="panel-header-actions">
                  <span className="panel-count" style={{ minWidth: 34, minHeight: 34, borderRadius: 12 }}>
                    {document?.flows.length ?? 0}
                  </span>
                  <button className="icon-button" onClick={() => setLeftCollapsed((current) => !current)}>
                    {leftCollapsed ? "展开" : "收起"}
                  </button>
                </div>
              </div>

              {!leftCollapsed && (
                <div style={{ display: "grid", gap: 10, minHeight: 0, flex: 1 }}>
                  <div style={{ display: "grid", gap: 8 }}>
                    <div className="search-field">
                      <input
                        value={flowQuery}
                        onChange={(event) => setFlowQuery(event.target.value)}
                        placeholder="搜索流程文件或节点内容"
                        style={{ padding: "8px 10px" }}
                      />
                    </div>

                    <span style={COMMAND_LABEL_STYLE}>{`${visibleFlows.length} 个流程 · ${issues.length} 个问题 · ${unusedImages.length} 张未使用图片`}</span>
                  </div>

                  <div className="flow-list" style={{ gap: 8 }}>
                    {visibleFlows.map((flow) => (
                      <button
                        key={flow.filename}
                        className={flow.filename === document?.state.selected_flow ? "flow-item active" : "flow-item"}
                        onClick={() => selectFlow(flow.filename)}
                        style={{ padding: "10px 12px", borderRadius: 14, gap: 10 }}
                      >
                        <div className="flow-text" style={{ gap: 4, minWidth: 0 }}>
                          <strong className="flow-name" style={{ fontSize: 14 }}>
                            {flow.filename}
                          </strong>
                          <span className="flow-meta" title={describeFlow(flow)}>
                            {`${flow.nodes.length} 个节点 · ${describeFlow(flow)}`}
                          </span>
                        </div>
                        <strong className="flow-count">{flow.nodes.length}</strong>
                      </button>
                    ))}
                    {!visibleFlows.length && <p className="empty">没有匹配的流程。</p>}
                  </div>

                  <section className="quality-panel" style={{ gap: 8 }}>
                    <div className="panel-header compact">
                      <div>
                        <h3>问题面板</h3>
                        <p>{issues.length ? `${issueSummary.error} 个错误 · ${issueSummary.warning} 个警告` : "校验与素材清理入口。"}</p>
                      </div>
                      <div className="toolbar-actions" style={{ gap: 6 }}>
                        <button
                          className="ghost-button"
                          style={COMPACT_BUTTON_STYLE}
                          onClick={() => void handleValidate()}
                          disabled={!document || busy.validate}
                        >
                          校验
                        </button>
                        <button
                          className="ghost-button"
                          style={COMPACT_BUTTON_STYLE}
                          onClick={() => void openUnusedAssetsWorkspace()}
                          disabled={!document || busy.scan}
                        >
                          图片
                        </button>
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="status-pill tone-warning" style={{ minHeight: 24, padding: "2px 8px", fontSize: 11 }}>
                        {issueSummary.error + issueSummary.warning || 0} 个待处理
                      </span>
                      <span className="status-pill tone-success" style={{ minHeight: 24, padding: "2px 8px", fontSize: 11 }}>
                        {unusedImages.length} 张未使用图片
                      </span>
                    </div>

                    <div className="issues-list" style={{ gap: 6, maxHeight: 120 }}>
                      {issues.slice(0, 3).map((issue, index) => (
                        <button
                          key={`${issue.flow_name}-${issue.node_id}-${index}`}
                          className={issueTone(issue.severity)}
                          style={{ padding: "10px 12px", borderRadius: 14 }}
                          onClick={() => {
                            selectFlow(issue.flow_name);
                            if (issue.node_id) {
                              activateNode(issue.node_id);
                            }
                          }}
                        >
                          <strong>{issue.severity === "error" ? "错误" : issue.severity === "warning" ? "警告" : "提示"}</strong>
                          <span>{issue.message}</span>
                        </button>
                      ))}
                      {issues.length > 3 && <p className="empty">{`还有 ${issues.length - 3} 个问题`}</p>}
                      {!issues.length && <p className="empty">暂无校验问题。</p>}
                    </div>
                  </section>
                </div>
              )}
            </aside>

            <main className="panel center-column center-column-compact">
              <div className="workbench-top" style={{ gap: 8 }}>
                <div className="panel-header compact" style={{ alignItems: "center" }}>
                  <div>
                    <h2>节点表</h2>
                    <p>{currentFlowSummary}</p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span className="status-pill tone-idle" style={{ minHeight: 26, padding: "3px 9px", fontSize: 11 }}>
                      已选 {selectedCount}
                    </span>
                    <span className="status-pill tone-idle" style={{ minHeight: 26, padding: "3px 9px", fontSize: 11 }}>
                      可见 {visibleNodes.length}
                    </span>
                  </div>
                </div>

                <div className="toolbar-strip">
                  <div className="toolbar-actions toolbar-actions-compact">
                    <div style={COMMAND_GROUP_STYLE}>
                      <span style={COMMAND_LABEL_STYLE}>历史</span>
                      <button style={COMPACT_BUTTON_STYLE} onClick={handleUndo} disabled={!canUndoEditorHistory(history)}>
                        撤销
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={handleRedo} disabled={!canRedoEditorHistory(history)}>
                        重做
                      </button>
                    </div>

                    <div style={COMMAND_GROUP_STYLE}>
                      <span style={COMMAND_LABEL_STYLE}>节点</span>
                      <select value={createOperation} onChange={(event) => setCreateOperation(event.target.value)} className="compact-select">
                        {operationEntries.map(([operation, meta]) => (
                          <option key={operation} value={operation}>
                            {meta.label} ({operation})
                          </option>
                        ))}
                      </select>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => addNode(createOperation)} disabled={!document}>
                        新增
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={deleteNodes} disabled={!document}>
                        删除
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => moveSelection(-1)} disabled={!selectedNodeIds.length}>
                        上移
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => moveSelection(1)} disabled={!selectedNodeIds.length}>
                        下移
                      </button>
                    </div>

                    <div style={COMMAND_GROUP_STYLE}>
                      <span style={COMMAND_LABEL_STYLE}>剪贴板</span>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => void copySelection()} disabled={!selectedNodeIds.length}>
                        复制
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => void pasteSelection()} disabled={!document}>
                        粘贴
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => void openImportDialog()} disabled={!document}>
                        导入
                      </button>
                    </div>

                    <div style={COMMAND_GROUP_STYLE}>
                      <span style={COMMAND_LABEL_STYLE}>工具</span>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => setActiveToolWindow("csv_preview")} disabled={!currentFlow}>
                        CSV 预览
                      </button>
                      <button style={COMPACT_BUTTON_STYLE} onClick={() => void openRecordingDialog()} disabled={!document}>
                        录制模式
                      </button>
                    </div>
                    <div className="search-row search-row-compact">
                      <input
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                        placeholder="搜索目标、摘要、跳转标记、备注"
                        style={{ padding: "8px 10px" }}
                      />
                      <span className="search-count">{`${selectedCount} 已选 · ${issues.length} 个问题`}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="node-table-wrap node-table-wrap-compact" style={{ borderRadius: 14 }}>
                <table className="node-table" style={{ tableLayout: "fixed" }}>
                  <thead>
                    <tr>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: 52 }}>序号</th>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: 96 }}>类型</th>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: "13%" }}>跳转标记</th>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: "23%" }}>目标</th>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: "31%" }}>摘要</th>
                      <th style={{ ...TABLE_HEADER_CELL_STYLE, width: "20%" }}>备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleNodes.map((node) => {
                      const rowView = getNodeRowView(node);
                      const noteText = node.note || rowView.secondary_text || "-";
                      const detailText = rowView.timing_text;
                      return (
                        <tr
                          key={node.node_id}
                          className={[
                            selectedNodeIds.includes(node.node_id) ? "selected-row" : "",
                            node.node_id === document?.state.selected_node_id ? "active-row" : "",
                          ].filter(Boolean).join(" ")}
                          onClick={(event) => handleNodeSelection(node.node_id, event)}
                          title={rowView.summary}
                        >
                          <td style={TABLE_BODY_CELL_STYLE}>
                            <span className="index-pill" style={{ minWidth: 28, height: 24, fontSize: 11 }}>
                              {node.index}
                            </span>
                          </td>
                          <td className="node-cell" style={TABLE_BODY_CELL_STYLE} title={`${rowView.operation_label} (${node.operation})`}>
                            <strong>{rowView.operation_label}</strong>
                            <span>{node.operation}</span>
                          </td>
                          <td className="node-cell" style={TABLE_BODY_CELL_STYLE} title={node.jump_mark || "-"}>
                            <span style={TABLE_SINGLE_LINE_STYLE}>{node.jump_mark || "-"}</span>
                          </td>
                          <td className="node-cell" style={TABLE_BODY_CELL_STYLE} title={`${rowView.locator_text} | ${rowView.region_text}`}>
                            <strong>{rowView.locator_text}</strong>
                            <span>{rowView.region_text}</span>
                          </td>
                          <td className="node-cell summary-cell" style={TABLE_BODY_CELL_STYLE} title={`${rowView.summary} | ${detailText}`}>
                            <strong>{rowView.summary}</strong>
                            <span>{detailText}</span>
                          </td>
                          <td className="node-cell" style={TABLE_BODY_CELL_STYLE} title={noteText}>
                            <span style={TABLE_SINGLE_LINE_STYLE}>{noteText}</span>
                          </td>
                        </tr>
                      );
                    })}
                    {!visibleNodes.length && (
                      <tr>
                        <td colSpan={6} className="empty">
                          {document ? "没有匹配当前筛选条件的节点。" : "先打开配置目录后开始编辑。"}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </main>

            <aside className={`panel right-column ${rightCollapsed ? "collapsed-panel" : ""}`}>
              <div className="panel-header compact" style={{ alignItems: "center" }}>
                <div>
                  <h2>节点编辑</h2>
                  <p>按操作类型展示真正可编辑的 CSV 字段。</p>
                </div>
                <div className="panel-header-actions">
                  {activeNode ? (
                    <span className="op-pill" data-operation={activeNode.operation} style={{ minHeight: 24, fontSize: 11 }}>
                      {activeRowView?.operation_label ?? activeNode.operation}
                    </span>
                  ) : (
                    <span className="panel-count" style={{ minWidth: 34, minHeight: 34, borderRadius: 12 }}>
                      0
                    </span>
                  )}
                  <button className="icon-button" onClick={() => setRightCollapsed((current) => !current)}>
                    {rightCollapsed ? "展开" : "收起"}
                  </button>
                </div>
              </div>

              {!rightCollapsed && activeNode ? (
                <div className="inspector inspector-compact" style={{ gap: 10 }}>
                  <section className="inspector-section" style={DENSE_SECTION_STYLE}>
                    <h3>基础信息</h3>
                    <div className="field-grid field-grid-tight">
                      <label>
                        <span>节点类型</span>
                        <select value={activeNode.operation} onChange={(event) => changeNodeOperation(event.target.value)}>
                          {operationEntries.map(([operation, meta]) => (
                            <option key={operation} value={operation}>
                              {meta.label} ({operation})
                            </option>
                          ))}
                        </select>
                      </label>

                      {paramEditorConfig && hasVisibleField(activeNodeMeta, "param_text") && (
                        <label>
                          <span>{paramEditorConfig.label}</span>
                          {paramEditorConfig.kind === "select" ? (
                            <select value={activeNode.param_text} onChange={(event) => updateNodeField("param_text", event.target.value)}>
                              {(paramEditorConfig.options ?? []).map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <div className="inline-field">
                              <input
                                value={activeNode.param_text}
                                onChange={(event) => updateNodeField("param_text", event.target.value)}
                                placeholder={paramEditorConfig.placeholder}
                                list={paramEditorConfig.kind === "jump-target" ? "jump-target-options" : undefined}
                              />
                              {paramEditorConfig.helper === "capture_point" && activeHelpers.includes("capture_point") && (
                                <button style={COMPACT_BUTTON_STYLE} onClick={() => void captureForNode("point")}>
                                  取点
                                </button>
                              )}
                              {paramEditorConfig.kind === "jump-target" && (
                                <datalist id="jump-target-options">
                                  {jumpTargetOptions.map((option) => (
                                    <option key={option} value={option} />
                                  ))}
                                </datalist>
                              )}
                            </div>
                          )}
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "search_target") && (
                        <label>
                          <span>{getSearchTargetLabel(activeNode.operation)}</span>
                          <input
                            value={activeNode.search_target}
                            onChange={(event) => updateNodeField("search_target", event.target.value)}
                            placeholder={activeNode.operation === "pic" ? "图片文件名，如 test.png" : "OCR 目标文本"}
                          />
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "region_text") && (
                        <label>
                          <span>搜索区域</span>
                          <div className="inline-field">
                            <input
                              value={activeNode.region_text}
                              onChange={(event) => updateNodeField("region_text", event.target.value)}
                              placeholder="x;y;width;height"
                            />
                            {(activeHelpers.includes("capture_image_region") || activeHelpers.includes("capture_ocr_region")) && (
                              <button
                                style={COMPACT_BUTTON_STYLE}
                                onClick={() => void captureForNode(activeNode.operation === "ocr" ? "ocr" : "pic")}
                              >
                                框选
                              </button>
                            )}
                          </div>
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "confidence_text") && (
                        <label>
                          <span>识别置信度</span>
                          <input value={activeNode.confidence_text} onChange={(event) => updateNodeField("confidence_text", event.target.value)} />
                        </label>
                      )}

                      {showMoveTimeField && (
                        <label>
                          <span>移动用时</span>
                          <input value={activeNode.move_time} onChange={(event) => updateNodeField("move_time", event.target.value)} />
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "jump_mark") && (
                        <label>
                          <span>跳转标记</span>
                          <input value={activeNode.jump_mark} onChange={(event) => updateNodeField("jump_mark", event.target.value)} />
                        </label>
                      )}
                    </div>
                  </section>

                  {(showWaitFields || showRetryFields) && (
                    <section className="inspector-section" style={DENSE_SECTION_STYLE}>
                      <h3>等待与重试</h3>
                      <div className="field-grid field-grid-tight">
                        {showWaitFields && (
                          <label>
                            <span>完成后等待</span>
                            <div className="split-field">
                              <input value={activeNode.wait_value} onChange={(event) => updateNodeField("wait_value", event.target.value)} placeholder="固定" />
                              <input value={activeNode.wait_random} onChange={(event) => updateNodeField("wait_random", event.target.value)} placeholder="随机" />
                            </div>
                          </label>
                        )}

                        {showRetryFields && (
                          <label>
                            <span>未命中重试</span>
                            <div className="split-field">
                              <input value={activeNode.retry_value} onChange={(event) => updateNodeField("retry_value", event.target.value)} placeholder="固定" />
                              <input value={activeNode.retry_random} onChange={(event) => updateNodeField("retry_random", event.target.value)} placeholder="随机" />
                            </div>
                          </label>
                        )}
                      </div>
                    </section>
                  )}

                  {showBranchFields && (
                    <section className="inspector-section" style={DENSE_SECTION_STYLE}>
                      <h3>分支</h3>
                      <div className="field-grid field-grid-tight">
                        <label>
                          <span>触发条件</span>
                          <select value={activeNode.branch.trigger} onChange={(event) => updateBranchField("trigger", event.target.value)}>
                            <option value="none">无（none）</option>
                            <option value="exist">存在时（exist）</option>
                            <option value="notExist">不存在时（notExist）</option>
                          </select>
                        </label>
                        <label>
                          <span>分支模式</span>
                          <select value={activeNode.branch.mode} onChange={(event) => updateBranchField("mode", event.target.value)}>
                            <option value="none">无（none）</option>
                            <option value="subflow">子流程（subflow）</option>
                            <option value="jump_pair">双跳转（jump_pair）</option>
                          </select>
                        </label>

                        {activeNode.branch.mode !== "none" && (
                          <label>
                            <span>{getBranchPrimaryLabel(activeNode.branch.mode)}</span>
                            <input
                              value={activeNode.branch.primary_target}
                              onChange={(event) => updateBranchField("primary_target", event.target.value)}
                              list="branch-target-options"
                            />
                          </label>
                        )}

                        {activeNode.branch.mode === "jump_pair" && (
                          <label>
                            <span>{getBranchSecondaryLabel(activeNode.branch.mode)}</span>
                            <input
                              value={activeNode.branch.secondary_target}
                              onChange={(event) => updateBranchField("secondary_target", event.target.value)}
                              list="branch-target-options"
                            />
                          </label>
                        )}

                        <datalist id="branch-target-options">
                          {branchTargetOptions.map((option) => (
                            <option key={option} value={option} />
                          ))}
                        </datalist>
                      </div>
                    </section>
                  )}

                  <section className="inspector-section" style={DENSE_SECTION_STYLE}>
                    <h3>补充信息</h3>
                    <div className="field-grid field-grid-tight">
                      {hasVisibleField(activeNodeMeta, "pic_range_random") && (
                        <label className="checkbox-row">
                          <input
                            type="checkbox"
                            checked={activeNode.pic_range_random}
                            onChange={(event) => updateNodeField("pic_range_random", event.target.checked)}
                          />
                          <span>命中后随机落点</span>
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "disable_grayscale") && (
                        <label className="checkbox-row">
                          <input
                            type="checkbox"
                            checked={activeNode.disable_grayscale}
                            onChange={(event) => updateNodeField("disable_grayscale", event.target.checked)}
                          />
                          <span>禁用灰度匹配</span>
                        </label>
                      )}

                      {hasVisibleField(activeNodeMeta, "note") && (
                        <label className="wide-field">
                          <span>备注</span>
                          <input value={activeNode.note} onChange={(event) => updateNodeField("note", event.target.value)} placeholder="仅供编辑时查看" />
                        </label>
                      )}
                    </div>

                    {(inspectorImage || activeNode.operation === "pic") && (
                      <div className="preview-card preview-card-compact preview-card-fixed">
                        <div className="subpanel-head compact">
                          <div>
                            <h3>图片预览</h3>
                            <p>当前 `pic` 节点绑定的图片素材。</p>
                          </div>
                        </div>
                        {inspectorImage ? (
                          <button
                            type="button"
                            className="preview-thumb-button"
                            onClick={() =>
                              setImageLightbox({
                                src: inspectorImage,
                                title: inspectorImageTitle,
                              })
                            }
                          >
                            <div className="preview-thumb-frame">
                              <img src={inspectorImage} alt="当前节点图片预览" />
                            </div>
                            <span className="preview-thumb-caption">点击查看大图</span>
                          </button>
                        ) : (
                          <p className="empty">当前节点暂无可预览图片。</p>
                        )}
                      </div>
                    )}
                  </section>
                </div>
              ) : !rightCollapsed ? (
                <div
                  style={{
                    border: "1px dashed #d6dfdc",
                    borderRadius: 14,
                    padding: "14px 15px",
                    background: "#fbfcf9",
                    color: "#627277",
                  }}
                >
                  选择一个节点后在这里编辑对应的 CSV 字段。
                </div>
              ) : (
                <p className="empty">编辑面板已收起。</p>
              )}
            </aside>
          </section>
        </div>
      </div>

      {importDialog.open && (
        <div className="modal-backdrop">
          <div className="modal">
            <div className="panel-header">
              <h2>导入节点</h2>
              <button onClick={() => setImportDialog((current) => ({ ...current, open: false }))}>关闭</button>
            </div>
            <div className="toolbar-actions">
              <button onClick={() => void chooseImportDirectory()}>选择来源配置</button>
              <span>{importDialog.rootPath || "尚未选择来源"}</span>
            </div>
            <div className="modal-grid">
              <div className="flow-list">
                {importDialog.document?.flows.map((flow) => (
                  <button
                    key={flow.filename}
                    className={importDialog.selectedFlow === flow.filename ? "flow-item active" : "flow-item"}
                    onClick={() => {
                      setImportDialog((current) => ({
                        ...current,
                        selectedFlow: flow.filename,
                        selectedNodeIds: [],
                      }));
                      setImportSelectionAnchorId(null);
                    }}
                  >
                    <span>{flow.filename}</span>
                    <strong>{flow.nodes.length}</strong>
                  </button>
                ))}
              </div>
              <div className="modal-table-wrap">
                <table className="node-table">
                  <thead>
                    <tr>
                      <th>序号</th>
                      <th>类型</th>
                      <th>摘要</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importFlowNodes.map((node) => (
                      <tr
                        key={node.node_id}
                        className={importDialog.selectedNodeIds.includes(node.node_id) ? "selected-row" : ""}
                        onClick={(event) => handleImportNodeSelection(node.node_id, event)}
                      >
                        <td>{node.index}</td>
                        <td>{getNodeRowView(node).operation_label}</td>
                        <td>{getNodeRowView(node).summary}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="toolbar-actions end">
              <button onClick={() => void importSelectedNodes()} disabled={!importDialog.selectedNodeIds.length}>
                导入选中节点
              </button>
            </div>
          </div>
        </div>
      )}

      {activeToolWindow === "csv_preview" && (
        <div className="modal-backdrop">
          <div className="modal wide tool-window">
            <div className="panel-header">
              <div>
                <h2>CSV 原始预览</h2>
                <p>{currentFlow ? `${currentFlow.filename} 的序列化结果` : "当前未选择流程。"}</p>
              </div>
              <button onClick={() => setActiveToolWindow("none")}>关闭</button>
            </div>
            <textarea readOnly value={csvPreview} className="preview-text modal-preview-text" />
          </div>
        </div>
      )}

      {activeToolWindow === "unused_assets" && (
        <div className="modal-backdrop">
          <div className="modal wide tool-window">
            <div className="panel-header">
              <div>
                <h2>未使用图片</h2>
                <p>{document ? `${document.root_path} 下的未使用截图素材` : "当前未加载配置。"}</p>
              </div>
              <div className="toolbar-actions">
                <button className="ghost-button" onClick={() => void handleScanImages()} disabled={!document || busy.scan}>
                  重新扫描
                </button>
                <button onClick={() => void deleteSelectedUnusedImages()} disabled={!selectedUnusedImageNames.length || busy.delete_unused}>
                  删除选中
                </button>
                <button onClick={() => setActiveToolWindow("none")}>关闭</button>
              </div>
            </div>
            <div className="asset-workspace">
              <div className="asset-list">
                {unusedImages.map((image) => (
                  <div
                    key={image.image_path}
                    className={[
                      "asset-row",
                      selectedUnusedImageNames.includes(image.image_name) ? "selected" : "",
                      previewImagePath === image.image_path ? "previewing" : "",
                    ].filter(Boolean).join(" ")}
                    onClick={(event) => handleUnusedImageSelection(image.image_name, event)}
                  >
                    <div className="asset-open-button">
                      <div className="asset-thumbnail">
                        <img src={fileUrl(image.image_path) ?? ""} alt={image.image_name} />
                      </div>
                      <div className="asset-meta">
                        <strong>{image.image_name}</strong>
                        <span>{image.image_path}</span>
                      </div>
                    </div>
                  </div>
                ))}
                {!unusedImages.length && <p className="empty">请先扫描未使用图片。</p>}
              </div>
              <div className="asset-preview-panel">
                <div className="subpanel-head compact">
                  <div>
                    <h3>图片预览</h3>
                    <p>已选 {selectedUnusedImageNames.length} 张</p>
                  </div>
                </div>
                <div className="image-preview large-preview">
                  {previewImageUrl ? <img src={previewImageUrl} alt="未使用图片预览" /> : <p className="empty">尚未选择图片。</p>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {recordingDialog.open && (
        <div className="modal-backdrop">
          <div className="modal wide">
            <div className="panel-header">
              <h2>录制工作流</h2>
              <button onClick={closeRecordingDialog} disabled={recordingSessionActive}>
                关闭
              </button>
            </div>
            <div className="recording-controls">
              <label>
                <span>模式</span>
                <select
                  value={recordingDialog.coordinateMode}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      coordinateMode: event.target.value as "screen" | "window",
                    }))
                  }
                >
                  <option value="screen">屏幕坐标（screen）</option>
                  <option value="window">窗口坐标（window）</option>
                </select>
              </label>
              <label>
                <span>窗口</span>
                <select
                  value={recordingDialog.selectedWindowHwnd}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      selectedWindowHwnd: event.target.value,
                    }))
                  }
                >
                  <option value="">无</option>
                  {recordingDialog.windows.map((windowOption) => (
                    <option key={windowOption.hwnd} value={String(windowOption.hwnd)}>
                      {windowOption.display_text ?? `${windowOption.title} | ${windowOption.process_name}`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={recordingDialog.matchChildWindow}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      matchChildWindow: event.target.checked,
                    }))
                  }
                />
                <span>匹配子窗口</span>
              </label>
              <button onClick={() => void startRecording()} disabled={recordingDialog.session?.status === "recording"}>
                开始
              </button>
              <button
                onClick={() => void toggleRecordingPaused(recordingDialog.session?.status !== "paused")}
                disabled={!recordingDialog.session || !["recording", "paused"].includes(recordingDialog.session.status)}
              >
                {recordingDialog.session?.status === "paused" ? "继续" : "暂停"}
              </button>
              <button
                onClick={() => void stopRecording()}
                disabled={!recordingDialog.session || !["recording", "paused"].includes(recordingDialog.session.status)}
              >
                停止
              </button>
              <span className="status-pill tone-idle">
                {recordingDialog.session ? `${recordingDialog.session.status} · ${recordingDialog.session.buffered_event_count} 条事件` : "空闲"}
              </span>
              {recordingDialog.session && (
                <span className="status-pill tone-idle">
                  {recordingDialog.session.coordinate_mode} · 子窗口 {recordingDialog.session.match_child_window ? "开" : "关"}
                </span>
              )}
              {recordingDialog.session && (
                <span className="status-pill tone-idle">
                  浮窗 {recordingDialog.session.overlay_visible ? "显示" : "隐藏"} · 忽略区 {recordingDialog.session.ignored_region_count ?? 0}
                </span>
              )}
              {recordingDialog.session?.assistant_suppressing_events && (
                <span className="status-pill tone-warning">浮窗正在抑制输入记录</span>
              )}
              {recordingDialog.session?.message && <span className="status-pill tone-idle">{recordingDialog.session.message}</span>}
            </div>
            <div className="recording-controls">
              <button onClick={() => void copyRecordedNodes()} disabled={!recordingDialog.recordedNodes.length}>
                复制选中
              </button>
              <button onClick={insertRecordedNodes} disabled={!recordingDialog.recordedNodes.length}>
                插入录制节点
              </button>
            </div>
            {recordingDialog.summary && (
              <div className="recording-summary">
                <span>{`总计 ${recordingDialog.summary.total}`}</span>
                <span>{`识别 ${recordingDialog.summary.visual_count}`}</span>
                <span>{`等待 ${recordingDialog.summary.wait_count}`}</span>
                <span>{`定位 ${recordingDialog.summary.locator_count}`}</span>
                <span>{`输入 ${recordingDialog.summary.input_count}`}</span>
              </div>
            )}
            <div className="node-table-wrap">
                <table className="node-table">
                  <thead>
                    <tr>
                      <th>序号</th>
                      <th>来源</th>
                      <th>语义</th>
                      <th>操作</th>
                      <th>目标</th>
                      <th>区域</th>
                      <th>策略</th>
                  </tr>
                </thead>
                <tbody>
                  {recordingDialog.recordedNodes.map((node, index) => {
                    const review = recordingDialog.reviewRows[index];
                    return (
                      <tr
                        key={node.node_id}
                        className={recordingDialog.selectedRecordedNodeIds.includes(node.node_id) ? "selected-row" : ""}
                        onClick={(event) => handleRecordedNodeSelection(node.node_id, event)}
                      >
                        <td>{node.index}</td>
                        <td>{review?.source ?? "事件"}</td>
                        <td>{review?.semantic ?? summarizeNode(node)}</td>
                        <td>{node.operation}</td>
                        <td>{review?.target_text || node.search_target || node.param_text}</td>
                        <td>{review?.region_text || node.region_text || "-"}</td>
                        <td>{review?.strategy_text || node.note || "-"}</td>
                      </tr>
                    );
                  })}
                  {!recordingDialog.recordedNodes.length && (
                    <tr>
                      <td colSpan={7} className="empty">
                        开始录制并停止后，这里会显示生成的节点。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {ocrCandidateDialog.open && (
        <div className="modal-backdrop">
          <div className="modal">
            <div className="panel-header">
              <div>
                <h2>OCR 候选文本</h2>
                <p>选择要回填到当前节点中的 OCR 文本。</p>
              </div>
              <button onClick={() => setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG)}>关闭</button>
            </div>
            <div className="flow-list">
              {ocrCandidateDialog.candidates.map((candidate) => (
                <label key={candidate} className={ocrCandidateDialog.selected === candidate ? "flow-item active" : "flow-item"}>
                  <input
                    type="radio"
                    name="ocr-candidate"
                    checked={ocrCandidateDialog.selected === candidate}
                    onChange={() => setOcrCandidateDialog((current) => ({ ...current, selected: candidate }))}
                  />
                  <div className="flow-text">
                    <strong className="flow-name">{candidate}</strong>
                    <span className="flow-meta">{ocrCandidateDialog.regionText}</span>
                  </div>
                </label>
              ))}
            </div>
            <label>
              <span>最终写入文本</span>
              <input
                value={ocrCandidateDialog.selected}
                onChange={(event) => setOcrCandidateDialog((current) => ({ ...current, selected: event.target.value }))}
              />
            </label>
            <div className="toolbar-actions end">
              <button className="ghost-button" onClick={() => setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG)}>
                取消
              </button>
              <button onClick={confirmOcrCandidateDialog}>应用</button>
            </div>
          </div>
        </div>
      )}

      {imageLightbox && (
        <div className="modal-backdrop image-lightbox-backdrop" onClick={() => setImageLightbox(null)}>
          <div className="image-lightbox" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header">
              <div>
                <h2>图片查看</h2>
                <p>{imageLightbox.title}</p>
              </div>
              <button onClick={() => setImageLightbox(null)}>关闭</button>
            </div>
            <div className="image-lightbox-stage">
              <img src={imageLightbox.src} alt={imageLightbox.title} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
