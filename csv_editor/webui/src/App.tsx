import { useEffect, useMemo, useState } from "react";

import { bridge } from "./bridge";
import { buildCsvPreview } from "./csvPreview";
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
  markKind: "pic" | "ocr";
  markAction: "locate" | "wait_exist" | "wait_not_exist";
};

type OcrCandidateDialogState = {
  open: boolean;
  mode: "node_capture" | "recording_mark";
  targetFlow: string | null;
  targetNodeId: string | null;
  regionText: string;
  candidates: string[];
  selected: string;
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
  switch (node.operation) {
    case "click":
      return `Click ${node.param_text || "left"}`;
    case "mDown":
      return `Mouse down ${node.param_text || "left"}`;
    case "mUp":
      return `Mouse up ${node.param_text || "left"}`;
    case "mMove":
      return `Move by ${node.param_text || "0;0"}`;
    case "mMoveTo":
      return `Move to ${node.param_text || "0;0"}`;
    case "press":
      return `Press ${node.param_text || "(unset)"}`;
    case "kDown":
      return `Key down ${node.param_text || "(unset)"}`;
    case "kUp":
      return `Key up ${node.param_text || "(unset)"}`;
    case "write":
      return `Write ${node.param_text || "(empty)"}`;
    case "notify":
      return `Notify ${node.param_text || "(empty)"}`;
    case "jmp":
      return `Jump ${node.param_text || "(unset)"}`;
    case "pic":
      return `Picture ${node.search_target || "(unset)"}`;
    case "ocr":
      return `OCR ${node.search_target || "(unset)"}`;
    default:
      return node.operation || "(empty)";
  }
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
    return "No config loaded";
  }
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function describeFlow(flow: FlowDocumentDTO): string {
  const lower = flow.filename.toLowerCase();
  if (lower.includes("main")) {
    return "main automation flow";
  }
  if (lower.includes("battle")) {
    return "battle routine";
  }
  if (lower.includes("return")) {
    return "return handling flow";
  }
  if (lower.includes("pending")) {
    return "holding area flow";
  }
  return flow.nodes.length <= 12 ? "sub flow" : "automation flow";
}

function summarizeBranch(node: OperationNodeDTO | null): string {
  if (!node) {
    return "No branch configured.";
  }
  const targets = [node.branch.primary_target, node.branch.secondary_target].filter(Boolean).join(" / ");
  if (node.branch.mode === "none" && node.branch.trigger === "none") {
    return "No branch configured.";
  }
  const details = [
    node.branch.trigger !== "none" ? `trigger ${node.branch.trigger}` : "",
    node.branch.mode !== "none" ? `mode ${node.branch.mode}` : "",
    targets,
  ]
    .filter(Boolean)
    .join(" · ");
  return details || "No branch configured.";
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
  mode: "node_capture",
  targetFlow: null,
  targetNodeId: null,
  regionText: "",
  candidates: [],
  selected: "",
};

export default function App() {
  const [bootstrap, setBootstrap] = useState<BootstrapDTO | null>(null);
  const [history, setHistory] = useState(() => createEditorHistoryState(null));
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [flowQuery, setFlowQuery] = useState("");
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [activeToolWindow, setActiveToolWindow] = useState<ToolWindow>("none");
  const [issues, setIssues] = useState<ValidationIssueDTO[]>([]);
  const [unusedImages, setUnusedImages] = useState<UnusedImageDTO[]>([]);
  const [selectedUnusedImageNames, setSelectedUnusedImageNames] = useState<string[]>([]);
  const [previewImagePath, setPreviewImagePath] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>({ tone: "idle", text: "Waiting for bridge bootstrap..." });
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [importDialog, setImportDialog] = useState<ImportDialogState>({
    open: false,
    rootPath: "",
    document: null,
    selectedFlow: null,
    selectedNodeIds: [],
  });
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
    markKind: "pic",
    markAction: "locate",
  });
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
      const haystack = [
        node.index,
        node.operation,
        node.param_text,
        node.search_target,
        node.region_text,
        node.jump_mark,
        node.note,
        summarizeNode(node),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [currentFlow, searchQuery]);

  const visibleFlows = useMemo(() => {
    const flows = document?.flows ?? [];
    const query = flowQuery.trim().toLowerCase();
    if (!query) {
      return flows;
    }
    return flows.filter((flow) => {
      const nodeHaystack = flow.nodes
        .map((node) => [node.operation, node.param_text, node.search_target, node.region_text, node.jump_mark, node.note].join(" "))
        .join(" ");
      const haystack = [flow.filename, describeFlow(flow), flow.nodes.length, nodeHaystack].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [document, flowQuery]);

  const csvPreview = useMemo(() => (currentFlow ? buildCsvPreview(currentFlow) : ""), [currentFlow]);
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
    const result = await bridge.getBootstrap();
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setBootstrap(result.data);
    setNotice({ tone: "success", text: "Bridge ready." });
    if (result.data.initial_root_path) {
      await openDocument(result.data.initial_root_path);
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
    setPreviewImagePath(null);
    setSelectedNodeIds(result.data.state.selected_node_id ? [result.data.state.selected_node_id] : []);
    replaceDocument(result.data);
    setNotice({ tone: "success", text: `Loaded ${rootPath}` });
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
    setNotice({ tone: "success", text: "Document saved." });
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
    setNotice({ tone: "success", text: `Validation finished with ${result.data.length} issues.` });
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
    setPreviewImagePath(result.data[0]?.image_path ?? null);
    setNotice({ tone: "success", text: `Found ${result.data.length} unused images.` });
  }

  function toggleUnusedImageSelection(imageName: string, checked: boolean) {
    setSelectedUnusedImageNames((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(imageName);
      } else {
        next.delete(imageName);
      }
      return [...next];
    });
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
    setPreviewImagePath((current) => {
      const stillExists = nextUnusedImages.some((image) => image.image_path === current);
      if (stillExists) {
        return current;
      }
      return nextUnusedImages[0]?.image_path ?? null;
    });
    const parts = [
      result.data.deleted.length ? `deleted ${result.data.deleted.length}` : "",
      result.data.missing.length ? `missing ${result.data.missing.length}` : "",
      result.data.failed.length ? `failed ${result.data.failed.length}` : "",
    ].filter(Boolean);
    setNotice({ tone: result.data.failed.length ? "warning" : "success", text: `Unused assets update: ${parts.join(" · ")}` });
  }

  function handleUndo() {
    if (!document || !canUndoEditorHistory(history)) {
      return;
    }
    const result = undoEditorHistory(history);
    setHistory(result.history);
    setSelectedNodeIds(result.selection?.selectedNodeIds ?? []);
  }

  function handleRedo() {
    if (!canRedoEditorHistory(history)) {
      return;
    }
    const result = redoEditorHistory(history);
    setHistory(result.history);
    setSelectedNodeIds(result.selection?.selectedNodeIds ?? []);
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
  }

  function toggleNodeSelection(nodeId: string, checked: boolean) {
    setSelectedNodeIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(nodeId);
      } else {
        next.delete(nodeId);
      }
      return [...next];
    });
  }

  function activateNode(nodeId: string) {
    if (!document) {
      return;
    }
    updateDocumentView((draft) => {
      draft.state.selected_node_id = nodeId;
    });
    setSelectedNodeIds((current) => (current.includes(nodeId) ? current : [nodeId]));
  }

  function addNode() {
    if (!document || !currentFlow) {
      return;
    }
    const newNode = cloneDocument(EMPTY_NODE);
    newNode.node_id = uniqueNodeId();
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "Add node",
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
      "Delete nodes",
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
      direction < 0 ? "Move nodes up" : "Move nodes down",
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
      setNotice({ tone: "warning", text: "Select one or more nodes first." });
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
      text: result.ok ? `Copied ${nodes.length} nodes.` : result.error.message,
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
      setNotice({ tone: "warning", text: "Clipboard does not contain editor nodes." });
      return;
    }
    const cloned = cloneNodesForInsert(result.data.nodes, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "Paste nodes",
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
    setNotice({ tone: "success", text: `Pasted ${cloned.length} nodes.` });
  }

  function updateNodeField(field: keyof OperationNodeDTO, value: string | boolean) {
    if (!document || !activeNode) {
      return;
    }
    const activeId = activeNode.node_id;
    commitDocument(
      `Edit ${String(field)}`,
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

  function updateBranchField(field: keyof OperationNodeDTO["branch"], value: string) {
    if (!document || !activeNode) {
      return;
    }
    const activeId = activeNode.node_id;
    commitDocument(
      `Edit branch ${String(field)}`,
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
      const result = await bridge.capturePoint("Pick a coordinate for this node");
      if (!result.ok) {
        setNotice({ tone: "error", text: result.error.message });
        return;
      }
      if (!result.data) {
        return;
      }
      updateNodeField("param_text", result.data.point_text);
      setNotice({ tone: "success", text: `Captured point ${result.data.point_text}.` });
      return;
    }

    const result = await bridge.captureRegion({
      prompt: mode === "pic" ? "Capture a picture region for this node" : "Capture an OCR region for this node",
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
          mode: "node_capture",
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
      `Capture ${mode.toUpperCase()} target`,
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
    setNotice({ tone: "success", text: `Captured ${mode.toUpperCase()} region.` });
  }

  async function openImportDialog() {
    setImportDialog({
      open: true,
      rootPath: "",
      document: null,
      selectedFlow: null,
      selectedNodeIds: [],
    });
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
  }

  async function importSelectedNodes() {
    if (!document || !currentFlow || !importDialog.rootPath || !importDialog.selectedFlow) {
      return;
    }
    const result = await bridge.importNodes({
      root_path: importDialog.rootPath,
      flow_name: importDialog.selectedFlow,
      node_ids: importDialog.selectedNodeIds,
    });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    const cloned = cloneNodesForInsert(result.data, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "Import nodes",
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
    setImportDialog((current) => ({ ...current, open: false }));
    setNotice({ tone: "success", text: `Imported ${cloned.length} nodes.` });
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
    setNotice({ tone: "success", text: "Recording started." });
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
    setNotice({ tone: "success", text: paused ? "Recording paused." : "Recording resumed." });
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
    setNotice({ tone: "success", text: `Recorded ${result.data.nodes.length} nodes.` });
  }

  async function addRecordingVisualMark() {
    if (!document || !recordingDialog.session?.session_id) {
      return;
    }
    const captureResult = await bridge.captureRegion({
      prompt: "Capture a visual marker region",
      root_path: document.root_path,
      save_image: recordingDialog.markKind === "pic",
      ocr_preview: recordingDialog.markKind === "ocr",
    });
    if (!captureResult.ok) {
      setNotice({ tone: "error", text: captureResult.error.message });
      return;
    }
    if (!captureResult.data) {
      return;
    }
    let searchTarget = "";
    let note = "";
    if (recordingDialog.markKind === "pic") {
      const imagePath = String(captureResult.data.image_path ?? "");
      searchTarget = imagePath.split(/[/\\]/).pop() ?? "";
    } else {
      const ocrCandidates = Array.isArray(captureResult.data.ocr_candidates)
        ? captureResult.data.ocr_candidates.map((candidate) => String(candidate).trim()).filter(Boolean)
        : [];
      const suggestedText = String(captureResult.data.suggested_text ?? "").trim();
      if (ocrCandidates.length > 1) {
        setOcrCandidateDialog({
          open: true,
          mode: "recording_mark",
          targetFlow: null,
          targetNodeId: null,
          regionText: String(captureResult.data.region_text ?? ""),
          candidates: ocrCandidates,
          selected: ocrCandidates[0] ?? suggestedText,
        });
        return;
      }
      searchTarget = suggestedText || ocrCandidates[0] || "";
      if (!searchTarget) {
        note = "OCR recording did not resolve a target. Review before inserting nodes.";
      }
    }
    await submitRecordingVisualMark(searchTarget, String(captureResult.data.region_text ?? ""), note);
  }

  async function submitRecordingVisualMark(searchTarget: string, regionText: string, note = "") {
    const result = await bridge.addVisualMark({
      kind: recordingDialog.markKind,
      action: recordingDialog.markAction,
      search_target: searchTarget,
      region_text: regionText,
      note,
    });
    if (!result.ok) {
      setNotice({ tone: "error", text: result.error.message });
      return;
    }
    setRecordingDialog((current) => ({ ...current, session: result.data }));
    setNotice({ tone: "success", text: "Visual mark added." });
  }

  function confirmOcrCandidateDialog() {
    if (!ocrCandidateDialog.open) {
      return;
    }
    const selected = ocrCandidateDialog.selected.trim();
    if (!selected) {
      setNotice({ tone: "warning", text: "Select or enter an OCR candidate first." });
      return;
    }
    if (ocrCandidateDialog.mode === "recording_mark") {
      const regionText = ocrCandidateDialog.regionText;
      const note =
        ocrCandidateDialog.candidates.length > 1
          ? `OCR recording candidates: ${ocrCandidateDialog.candidates.slice(0, 5).join(" | ")}`
          : "";
      setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
      void submitRecordingVisualMark(selected, regionText, note);
      return;
    }
    if (!document || !ocrCandidateDialog.targetFlow || !ocrCandidateDialog.targetNodeId) {
      setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
      return;
    }
    const { targetFlow, targetNodeId, regionText } = ocrCandidateDialog;
    commitDocument(
      "Capture OCR target",
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
    setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG);
    setNotice({ tone: "success", text: "Captured OCR region." });
  }

  function closeRecordingDialog() {
    if (recordingDialog.session?.close_protected ?? ["recording", "paused"].includes(recordingDialog.session?.status ?? "")) {
      setNotice({ tone: "warning", text: "Stop recording before closing the workflow window." });
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
    setNotice({ tone: "success", text: `Copied ${copiedCount} recorded nodes.` });
  }

  function insertRecordedNodes() {
    if (!document || !currentFlow || !recordingDialog.recordedNodes.length) {
      return;
    }
    const cloned = cloneNodesForInsert(recordingDialog.recordedNodes, currentFlow);
    const anchorId = document.state.selected_node_id;
    commitDocument(
      "Insert recorded nodes",
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
    setRecordingDialog((current) => ({
      ...current,
      open: false,
      recordedNodes: [],
      selectedRecordedNodeIds: [],
      session: null,
    }));
    setNotice({ tone: "success", text: `Inserted ${cloned.length} recorded nodes.` });
  }

  function toggleRecordedNodeSelection(nodeId: string, checked: boolean) {
    setRecordingDialog((current) => {
      const next = new Set(current.selectedRecordedNodeIds);
      if (checked) {
        next.add(nodeId);
      } else {
        next.delete(nodeId);
      }
      return { ...current, selectedRecordedNodeIds: [...next] };
    });
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
  const activeNodeDetail = activeNode?.search_target || activeNode?.param_text || "Unset target";
  const recordingSessionActive = Boolean(
    recordingDialog.session?.close_protected ?? (recordingDialog.session && ["recording", "paused"].includes(recordingDialog.session.status)),
  );

  return (
    <div className="app-shell">
      <div className="editor-frame">
        <aside className="nav-rail" aria-hidden="true">
          <div className="rail-brand">C</div>
          <div className="rail-stack">
            <span className="rail-marker active">F</span>
            <span className="rail-marker">N</span>
            <span className="rail-marker">I</span>
          </div>
          <div className="rail-spacer" />
          <span className="rail-marker">?</span>
        </aside>

        <div className="stage-shell">
          <header className="topbar">
            <div className="topbar-copy">
              <p className="eyebrow">Web UI concept / route 2</p>
              <h1>{bootstrap?.app_name ?? "CsvAutoGui Editor"}</h1>
              <p className="subtitle">
                {document ? `Current config: ${document.root_path}` : "Python backend + WebView frontend"}
              </p>
            </div>
            <div className="topbar-actions">
              <button className="ghost-button accent-teal" onClick={() => void handleChooseDirectory()}>
                Open Config
              </button>
              <button className="ghost-button" onClick={() => setDensity((current) => (current === "compact" ? "comfortable" : "compact"))}>
                Density: {density === "compact" ? "Compact" : "Comfort"}
              </button>
              <button className="ghost-button" onClick={() => setActiveToolWindow("csv_preview")} disabled={!document}>
                CSV Preview
              </button>
              <button className="ghost-button" onClick={() => void openUnusedAssetsWorkspace()} disabled={!document}>
                Unused Assets
              </button>
              <button className="ghost-button accent-amber" onClick={() => void openRecordingDialog()} disabled={!document}>
                Record
              </button>
              <button className="ghost-button accent-amber" onClick={() => void handleValidate()} disabled={!document || busy.validate}>
                Validate
              </button>
              <button className="soft-button accent-teal" onClick={() => void handleSave()} disabled={!document || busy.save}>
                Save
              </button>
            </div>
            <div className="status-cluster">
              <span className={`status-pill tone-${notice.tone}`}>{notice.text}</span>
              <span className={`status-pill ${dirty ? "tone-warning" : "tone-success"}`}>
                {dirty ? "Unsaved changes" : "Saved"}
              </span>
            </div>
          </header>

          <section className={`workspace-grid density-${density} ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}>
            <aside className={`panel left-column ${leftCollapsed ? "collapsed-panel" : ""}`}>
              <div className="panel-header stacked">
                <div>
                  <h2>Flows</h2>
                  <p>Browse automation branches and keep an eye on validation health.</p>
                </div>
                <div className="panel-header-actions">
                  <span className="panel-count">{document?.flows.length ?? 0}</span>
                  <button className="icon-button" onClick={() => setLeftCollapsed((current) => !current)}>
                    {leftCollapsed ? "Expand" : "Collapse"}
                  </button>
                </div>
              </div>

              {!leftCollapsed && (
                <>
                  <div className="search-field">
                    <input
                      value={flowQuery}
                      onChange={(event) => setFlowQuery(event.target.value)}
                      placeholder="Search flow or node..."
                    />
                  </div>

                  <div className="flow-list">
                    {visibleFlows.map((flow) => (
                      <button
                        key={flow.filename}
                        className={flow.filename === document?.state.selected_flow ? "flow-item active" : "flow-item"}
                        onClick={() => selectFlow(flow.filename)}
                      >
                        <div className="flow-text">
                          <strong className="flow-name">{flow.filename}</strong>
                          <span className="flow-meta">{`${flow.nodes.length} nodes · ${describeFlow(flow)}`}</span>
                        </div>
                        <strong className="flow-count">{flow.nodes.length}</strong>
                      </button>
                    ))}
                    {!visibleFlows.length && <p className="empty">No flows match the current search.</p>}
                  </div>

                  <section className="quality-panel">
                    <div className="panel-header compact stacked">
                      <div>
                        <h3>Validation</h3>
                        <p>Run checks before save and review detached assets.</p>
                      </div>
                      <div className="toolbar-actions">
                        <button className="ghost-button" onClick={() => void handleValidate()} disabled={!document || busy.validate}>
                          Validate
                        </button>
                        <button className="ghost-button" onClick={() => void openUnusedAssetsWorkspace()} disabled={!document || busy.scan}>
                          Assets
                        </button>
                      </div>
                    </div>

                    <div className="quality-summary">
                      <div className="quality-card quality-warning">
                        <strong>{issueSummary.error + issueSummary.warning || 0} findings</strong>
                        <span>
                          {issues.length
                            ? `${issueSummary.error} errors · ${issueSummary.warning} warnings`
                            : "No validation report yet"}
                        </span>
                      </div>
                      <div className="quality-card quality-success">
                        <strong>{unusedImages.length} unused assets</strong>
                        <span>{unusedImages.length ? "Workspace ready for cleanup." : "Asset scan has not been run."}</span>
                      </div>
                    </div>

                    <div className="issues-list">
                      {issues.map((issue, index) => (
                        <button
                          key={`${issue.flow_name}-${issue.node_id}-${index}`}
                          className={issueTone(issue.severity)}
                          onClick={() => {
                            selectFlow(issue.flow_name);
                            if (issue.node_id) {
                              activateNode(issue.node_id);
                            }
                          }}
                        >
                          <strong>{issue.severity}</strong>
                          <span>{issue.message}</span>
                        </button>
                      ))}
                      {!issues.length && <p className="empty">Run validation to populate issues.</p>}
                    </div>
                  </section>
                </>
              )}
            </aside>

            <main className="panel center-column">
              <div className="workbench-top">
                <div className="panel-header compact">
                  <div>
                    <h2>Node List</h2>
                    <p>{currentFlow ? `${currentFlow.filename} · ${visibleNodes.length} visible nodes` : "Select a flow to start editing."}</p>
                  </div>
                  <div className="view-switch">
                    <span className="view-chip active">Table</span>
                    <span className="view-chip muted">{density === "compact" ? "Dense" : "Comfort"}</span>
                  </div>
                </div>

                <div className="toolbar-actions wide">
                  <button onClick={handleUndo} disabled={!canUndoEditorHistory(history)}>
                    Undo
                  </button>
                  <button onClick={handleRedo} disabled={!canRedoEditorHistory(history)}>
                    Redo
                  </button>
                  <button onClick={addNode} disabled={!document}>
                    Add
                  </button>
                  <button onClick={deleteNodes} disabled={!document}>
                    Delete
                  </button>
                  <button onClick={() => moveSelection(-1)} disabled={!selectedNodeIds.length}>
                    Up
                  </button>
                  <button onClick={() => moveSelection(1)} disabled={!selectedNodeIds.length}>
                    Down
                  </button>
                  <button onClick={() => void copySelection()} disabled={!selectedNodeIds.length}>
                    Copy
                  </button>
                  <button onClick={() => void pasteSelection()} disabled={!document}>
                    Paste
                  </button>
                  <button onClick={() => void openImportDialog()} disabled={!document}>
                    Import
                  </button>
                  <button onClick={() => setActiveToolWindow("csv_preview")} disabled={!currentFlow}>
                    Preview
                  </button>
                  <button onClick={() => void openRecordingDialog()} disabled={!document}>
                    Record
                  </button>
                </div>
              </div>

              <div className="search-block">
                <div className="quick-filters">
                  {quickFilters.map((filter) => (
                    <button
                      key={filter.operation}
                      className={searchQuery.trim().toLowerCase() === filter.operation ? "quick-filter active" : "quick-filter"}
                      onClick={() =>
                        setSearchQuery((current) => (current.trim().toLowerCase() === filter.operation ? "" : filter.operation))
                      }
                    >
                      {filter.operation.toUpperCase()} · {filter.count}
                    </button>
                  ))}
                </div>
                <div className="search-row">
                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Quick filter: OCR / PIC / Click / Move / Branch / Wait"
                  />
                  <span className="search-count">{selectedCount} selected</span>
                </div>
              </div>

              <div className="node-table-wrap">
                <table className="node-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>#</th>
                      <th>Type</th>
                      <th>Param</th>
                      <th>Target</th>
                      <th>Region / Mark</th>
                      <th>Timing</th>
                      <th>Branch</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleNodes.map((node) => (
                      <tr
                        key={node.node_id}
                        className={node.node_id === document?.state.selected_node_id ? "active-row" : ""}
                        onClick={() => activateNode(node.node_id)}
                      >
                        <td className="checkbox-cell">
                          <input
                            type="checkbox"
                            checked={selectedNodeIds.includes(node.node_id)}
                            onChange={(event) => toggleNodeSelection(node.node_id, event.target.checked)}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </td>
                        <td>
                          <span className="index-pill">{node.index}</span>
                        </td>
                        <td>
                          <span className="op-pill" data-operation={node.operation}>
                            {node.operation.toUpperCase()}
                          </span>
                        </td>
                        <td className="node-cell compact-cell">
                          <strong>{node.param_text || "-"}</strong>
                          <span>{node.move_time || "-"}</span>
                        </td>
                        <td className="node-cell">
                          <strong>{node.search_target || node.param_text || "Unset target"}</strong>
                          <span>{node.confidence_text || "No confidence"}</span>
                        </td>
                        <td className="node-cell compact-cell">
                          <strong>{node.region_text || "-"}</strong>
                          <span>{node.jump_mark || "No jump mark"}</span>
                        </td>
                        <td className="node-cell compact-cell">
                          <strong>{node.wait_value || "-"}</strong>
                          <span>{node.retry_value ? `retry ${node.retry_value}` : "No retry"}</span>
                        </td>
                        <td className="node-cell compact-cell">
                          <strong>{node.branch.mode !== "none" ? node.branch.mode : "none"}</strong>
                          <span>{node.branch.trigger !== "none" ? node.branch.trigger : "no trigger"}</span>
                        </td>
                        <td className="node-cell summary-cell">
                          <strong>{summarizeNode(node)}</strong>
                          <span>{node.note || "No note"}</span>
                        </td>
                      </tr>
                    ))}
                    {!visibleNodes.length && (
                      <tr>
                        <td colSpan={9} className="empty">
                          Open a config directory to start editing.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="workbench-footer">
                <span>{`${visibleNodes.length} visible nodes · ${totalNodes} total nodes`}</span>
                <span>{`${selectedCount} selected · ${issues.length} issues · ${unusedImages.length} unused`}</span>
              </div>
            </main>

            <aside className={`panel right-column ${rightCollapsed ? "collapsed-panel" : ""}`}>
              <div className="panel-header stacked compact">
                <div>
                  <h2>Inspector</h2>
                  <p>Selected node details, timing parameters, and branch routing.</p>
                </div>
                <div className="panel-header-actions">
                  {activeNode ? (
                    <span className="op-pill" data-operation={activeNode.operation}>
                      {activeNode.operation.toUpperCase()}
                    </span>
                  ) : (
                    <span className="panel-count">0</span>
                  )}
                  <button className="icon-button" onClick={() => setRightCollapsed((current) => !current)}>
                    {rightCollapsed ? "Expand" : "Collapse"}
                  </button>
                </div>
              </div>
              {!rightCollapsed && activeNode ? (
                <div className="inspector">
                  <div className="inspector-hero">
                    <strong>{summarizeNode(activeNode)}</strong>
                    <span>{`${activeNodeDetail} · ${summarizeBranch(activeNode)}`}</span>
                  </div>

                  <section className="inspector-section">
                    <h3>Locator</h3>
                    <div className="field-grid">
                      <label>
                        <span>Operation</span>
                        <input value={activeNode.operation} onChange={(event) => updateNodeField("operation", event.target.value)} />
                      </label>
                      <label>
                        <span>Search Target</span>
                        <input value={activeNode.search_target} onChange={(event) => updateNodeField("search_target", event.target.value)} />
                      </label>
                      <label className="wide-field">
                        <span>Param</span>
                        <div className="inline-field">
                          <input value={activeNode.param_text} onChange={(event) => updateNodeField("param_text", event.target.value)} />
                          <button onClick={() => void captureForNode("point")}>Pick</button>
                        </div>
                      </label>
                      <label className="wide-field">
                        <span>Region</span>
                        <div className="inline-field">
                          <input value={activeNode.region_text} onChange={(event) => updateNodeField("region_text", event.target.value)} />
                          <button onClick={() => void captureForNode(activeNode.operation === "ocr" ? "ocr" : "pic")}>
                            Capture
                          </button>
                        </div>
                      </label>
                      <label className="wide-field">
                        <span>Confidence</span>
                        <input
                          value={activeNode.confidence_text}
                          onChange={(event) => updateNodeField("confidence_text", event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="metric-card">
                      <div className="metric-header">
                        <span>Match confidence</span>
                        <strong>{activeNode.confidence_text || "0.00"}</strong>
                      </div>
                      <div className="confidence-track">
                        <span style={{ width: `${confidenceValue * 100}%` }} />
                      </div>
                    </div>
                  </section>

                  <section className="inspector-section">
                    <h3>Timing</h3>
                    <div className="field-grid">
                      <label>
                        <span>Wait</span>
                        <div className="split-field">
                          <input value={activeNode.wait_value} onChange={(event) => updateNodeField("wait_value", event.target.value)} />
                          <input value={activeNode.wait_random} onChange={(event) => updateNodeField("wait_random", event.target.value)} />
                        </div>
                      </label>
                      <label>
                        <span>Retry</span>
                        <div className="split-field">
                          <input value={activeNode.retry_value} onChange={(event) => updateNodeField("retry_value", event.target.value)} />
                          <input value={activeNode.retry_random} onChange={(event) => updateNodeField("retry_random", event.target.value)} />
                        </div>
                      </label>
                      <label>
                        <span>Move Time</span>
                        <input value={activeNode.move_time} onChange={(event) => updateNodeField("move_time", event.target.value)} />
                      </label>
                      <label>
                        <span>Jump Mark</span>
                        <input value={activeNode.jump_mark} onChange={(event) => updateNodeField("jump_mark", event.target.value)} />
                      </label>
                    </div>
                  </section>

                  <section className="inspector-section">
                    <h3>Branch</h3>
                    <div className="field-grid">
                      <label>
                        <span>Branch Trigger</span>
                        <select value={activeNode.branch.trigger} onChange={(event) => updateBranchField("trigger", event.target.value)}>
                          <option value="none">none</option>
                          <option value="exist">exist</option>
                          <option value="notExist">notExist</option>
                        </select>
                      </label>
                      <label>
                        <span>Branch Mode</span>
                        <select value={activeNode.branch.mode} onChange={(event) => updateBranchField("mode", event.target.value)}>
                          <option value="none">none</option>
                          <option value="subflow">subflow</option>
                          <option value="jump_pair">jump_pair</option>
                        </select>
                      </label>
                      <label>
                        <span>Primary Target</span>
                        <input
                          value={activeNode.branch.primary_target}
                          onChange={(event) => updateBranchField("primary_target", event.target.value)}
                        />
                      </label>
                      <label>
                        <span>Secondary Target</span>
                        <input
                          value={activeNode.branch.secondary_target}
                          onChange={(event) => updateBranchField("secondary_target", event.target.value)}
                        />
                      </label>
                    </div>
                  </section>

                  <section className="inspector-section">
                    <h3>Notes & Preview</h3>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={activeNode.pic_range_random}
                        onChange={(event) => updateNodeField("pic_range_random", event.target.checked)}
                      />
                      <span>Picture random move</span>
                    </label>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={activeNode.disable_grayscale}
                        onChange={(event) => updateNodeField("disable_grayscale", event.target.checked)}
                      />
                      <span>Disable grayscale</span>
                    </label>
                    <label>
                      <span>Note</span>
                      <textarea value={activeNode.note} onChange={(event) => updateNodeField("note", event.target.value)} />
                    </label>
                    <div className="preview-card">
                      <div className="subpanel-head compact">
                        <div>
                          <h3>Image Preview</h3>
                          <p>Screenshot target tied to the selected picture node.</p>
                        </div>
                      </div>
                      {inspectorImage ? <img src={inspectorImage} alt="Current node target" /> : <p className="empty">No preview available.</p>}
                    </div>
                  </section>
                </div>
              ) : !rightCollapsed ? (
                <p className="empty">Select a node to edit its fields.</p>
              ) : (
                <p className="empty">Inspector collapsed.</p>
              )}
            </aside>
          </section>

          <footer className="status-bar">
            <span>{`Current config: ${configLabel}`}</span>
            <span>{`${document?.flows.length ?? 0} flows · ${totalNodes} nodes`}</span>
            <span>{`${issues.length} issues · ${unusedImages.length} unused images`}</span>
          </footer>
        </div>
      </div>

      {importDialog.open && (
        <div className="modal-backdrop">
          <div className="modal">
            <div className="panel-header">
              <h2>Import Nodes</h2>
              <button onClick={() => setImportDialog((current) => ({ ...current, open: false }))}>Close</button>
            </div>
            <div className="toolbar-actions">
              <button onClick={() => void chooseImportDirectory()}>Choose Source</button>
              <span>{importDialog.rootPath || "No source chosen"}</span>
            </div>
            <div className="modal-grid">
              <div className="flow-list">
                {importDialog.document?.flows.map((flow) => (
                  <button
                    key={flow.filename}
                    className={importDialog.selectedFlow === flow.filename ? "flow-item active" : "flow-item"}
                    onClick={() =>
                      setImportDialog((current) => ({
                        ...current,
                        selectedFlow: flow.filename,
                        selectedNodeIds: [],
                      }))
                    }
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
                      <th></th>
                      <th>#</th>
                      <th>Operation</th>
                      <th>Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flowByName(importDialog.document, importDialog.selectedFlow)?.nodes.map((node) => (
                      <tr key={node.node_id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={importDialog.selectedNodeIds.includes(node.node_id)}
                            onChange={(event) =>
                              setImportDialog((current) => ({
                                ...current,
                                selectedNodeIds: event.target.checked
                                  ? [...current.selectedNodeIds, node.node_id]
                                  : current.selectedNodeIds.filter((item) => item !== node.node_id),
                              }))
                            }
                          />
                        </td>
                        <td>{node.index}</td>
                        <td>{node.operation}</td>
                        <td>{summarizeNode(node)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="toolbar-actions end">
              <button onClick={() => void importSelectedNodes()} disabled={!importDialog.selectedNodeIds.length}>
                Import Selected
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
                <h2>CSV Preview</h2>
                <p>{currentFlow ? `Serialized output for ${currentFlow.filename}` : "No flow selected."}</p>
              </div>
              <button onClick={() => setActiveToolWindow("none")}>Close</button>
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
                <h2>Unused Assets</h2>
                <p>{document ? `Detached screenshots under ${document.root_path}` : "No config loaded."}</p>
              </div>
              <div className="toolbar-actions">
                <button className="ghost-button" onClick={() => void handleScanImages()} disabled={!document || busy.scan}>
                  Rescan
                </button>
                <button onClick={() => void deleteSelectedUnusedImages()} disabled={!selectedUnusedImageNames.length || busy.delete_unused}>
                  Delete Selected
                </button>
                <button onClick={() => setActiveToolWindow("none")}>Close</button>
              </div>
            </div>
            <div className="asset-workspace">
              <div className="asset-list">
                {unusedImages.map((image) => (
                  <label
                    key={image.image_path}
                    className={previewImagePath === image.image_path ? "asset-row active" : "asset-row"}
                  >
                    <input
                      type="checkbox"
                      checked={selectedUnusedImageNames.includes(image.image_name)}
                      onChange={(event) => toggleUnusedImageSelection(image.image_name, event.target.checked)}
                    />
                    <button type="button" className="asset-open-button" onClick={() => setPreviewImagePath(image.image_path)}>
                      <div className="asset-thumbnail">
                        <img src={fileUrl(image.image_path) ?? ""} alt={image.image_name} />
                      </div>
                      <div className="asset-meta">
                        <strong>{image.image_name}</strong>
                        <span>{image.image_path}</span>
                      </div>
                    </button>
                  </label>
                ))}
                {!unusedImages.length && <p className="empty">Run asset scan to populate this workspace.</p>}
              </div>
              <div className="asset-preview-panel">
                <div className="subpanel-head compact">
                  <div>
                    <h3>Preview</h3>
                    <p>{selectedUnusedImageNames.length} selected</p>
                  </div>
                </div>
                <div className="image-preview large-preview">
                  {previewImageUrl ? <img src={previewImageUrl} alt="Unused asset preview" /> : <p className="empty">No image selected.</p>}
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
              <h2>Recording Workflow</h2>
              <button onClick={closeRecordingDialog} disabled={recordingSessionActive}>
                Close
              </button>
            </div>
            <div className="recording-controls">
              <label>
                <span>Mode</span>
                <select
                  value={recordingDialog.coordinateMode}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      coordinateMode: event.target.value as "screen" | "window",
                    }))
                  }
                >
                  <option value="screen">screen</option>
                  <option value="window">window</option>
                </select>
              </label>
              <label>
                <span>Window</span>
                <select
                  value={recordingDialog.selectedWindowHwnd}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      selectedWindowHwnd: event.target.value,
                    }))
                  }
                >
                  <option value="">None</option>
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
                <span>Match child window</span>
              </label>
              <button onClick={() => void startRecording()} disabled={recordingDialog.session?.status === "recording"}>
                Start
              </button>
              <button
                onClick={() => void toggleRecordingPaused(recordingDialog.session?.status !== "paused")}
                disabled={!recordingDialog.session || !["recording", "paused"].includes(recordingDialog.session.status)}
              >
                {recordingDialog.session?.status === "paused" ? "Resume" : "Pause"}
              </button>
              <button
                onClick={() => void stopRecording()}
                disabled={!recordingDialog.session || !["recording", "paused"].includes(recordingDialog.session.status)}
              >
                Stop
              </button>
              <span className="status-pill tone-idle">
                {recordingDialog.session ? `${recordingDialog.session.status} · ${recordingDialog.session.buffered_event_count} events` : "idle"}
              </span>
              {recordingDialog.session && (
                <span className="status-pill tone-idle">
                  {recordingDialog.session.coordinate_mode} · child {recordingDialog.session.match_child_window ? "on" : "off"}
                </span>
              )}
              {recordingDialog.session && (
                <span className="status-pill tone-idle">
                  overlay {recordingDialog.session.overlay_visible ? "on" : "off"} · ignore {recordingDialog.session.ignored_region_count ?? 0}
                </span>
              )}
              {recordingDialog.session?.assistant_suppressing_events && (
                <span className="status-pill tone-warning">assistant suppressing input</span>
              )}
              {recordingDialog.session?.message && <span className="status-pill tone-idle">{recordingDialog.session.message}</span>}
            </div>
            <div className="recording-controls">
              <label>
                <span>Mark Kind</span>
                <select
                  value={recordingDialog.markKind}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      markKind: event.target.value as "pic" | "ocr",
                    }))
                  }
                >
                  <option value="pic">pic</option>
                  <option value="ocr">ocr</option>
                </select>
              </label>
              <label>
                <span>Action</span>
                <select
                  value={recordingDialog.markAction}
                  onChange={(event) =>
                    setRecordingDialog((current) => ({
                      ...current,
                      markAction: event.target.value as "locate" | "wait_exist" | "wait_not_exist",
                    }))
                  }
                >
                  <option value="locate">locate</option>
                  <option value="wait_exist">wait_exist</option>
                  <option value="wait_not_exist">wait_not_exist</option>
                </select>
              </label>
              <button onClick={() => void addRecordingVisualMark()} disabled={recordingDialog.session?.status !== "recording"}>
                Add Visual Mark
              </button>
              <button onClick={() => void copyRecordedNodes()} disabled={!recordingDialog.recordedNodes.length}>
                Copy Selected
              </button>
              <button onClick={insertRecordedNodes} disabled={!recordingDialog.recordedNodes.length}>
                Insert Recorded Nodes
              </button>
            </div>
            {recordingDialog.summary && (
              <div className="recording-summary">
                <span>{`total ${recordingDialog.summary.total}`}</span>
                <span>{`visual ${recordingDialog.summary.visual_count}`}</span>
                <span>{`wait ${recordingDialog.summary.wait_count}`}</span>
                <span>{`locator ${recordingDialog.summary.locator_count}`}</span>
                <span>{`input ${recordingDialog.summary.input_count}`}</span>
              </div>
            )}
            <div className="node-table-wrap">
              <table className="node-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>#</th>
                    <th>Source</th>
                    <th>Semantic</th>
                    <th>Operation</th>
                    <th>Target</th>
                    <th>Region</th>
                    <th>Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {recordingDialog.recordedNodes.map((node, index) => {
                    const review = recordingDialog.reviewRows[index];
                    return (
                    <tr key={node.node_id} className={recordingDialog.selectedRecordedNodeIds.includes(node.node_id) ? "active-row" : ""}>
                      <td>
                        <input
                          type="checkbox"
                          checked={recordingDialog.selectedRecordedNodeIds.includes(node.node_id)}
                          onChange={(event) => toggleRecordedNodeSelection(node.node_id, event.target.checked)}
                        />
                      </td>
                      <td>{node.index}</td>
                      <td>{review?.source ?? "event"}</td>
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
                      <td colSpan={8} className="empty">
                        Start a session, stop it, then insert the generated nodes.
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
                <h2>OCR Candidates</h2>
                <p>Choose the text that should be written back to the editor workflow.</p>
              </div>
              <button onClick={() => setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG)}>Close</button>
            </div>
            <div className="flow-list">
              {ocrCandidateDialog.candidates.map((candidate) => (
                <label key={candidate} className={ocrCandidateDialog.selected === candidate ? "asset-row active" : "asset-row"}>
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
              <span>Selected text</span>
              <input
                value={ocrCandidateDialog.selected}
                onChange={(event) => setOcrCandidateDialog((current) => ({ ...current, selected: event.target.value }))}
              />
            </label>
            <div className="toolbar-actions end">
              <button className="ghost-button" onClick={() => setOcrCandidateDialog(EMPTY_OCR_CANDIDATE_DIALOG)}>
                Cancel
              </button>
              <button onClick={confirmOcrCandidateDialog}>Apply</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
