import type {
  BootstrapDTO,
  NodeRowViewDTO,
  OperationFieldMetaDTO,
  OperationHelper,
  OperationMetaDTO,
  OperationMetadataDTO,
  OperationNodeDTO,
} from "./types";

const EMPTY_FIELD_META: OperationFieldMetaDTO = { label: "" };
const WAIT_FIELDS = ["wait_value", "wait_random"] as const;
const RETRY_FIELDS = ["retry_value", "retry_random"] as const;
const BRANCH_FIELDS = [
  "branch.trigger",
  "branch.mode",
  "branch.primary_target",
  "branch.secondary_target",
] as const;
const COMMON_FIELDS = [...WAIT_FIELDS, "jump_mark", "note"] as const;
const VISUAL_FIELDS = [
  "search_target",
  "region_text",
  "confidence_text",
  ...RETRY_FIELDS,
  "pic_range_random",
  "move_time",
  "jump_mark",
  "note",
  ...BRANCH_FIELDS,
] as const;

const FALLBACK_OPERATION_METADATA: OperationMetadataDTO = {
  version: 1,
  fields: {
    param_text: { label: "操作参数" },
    wait_value: { label: "完成后等待时间" },
    wait_random: { label: "等待随机时间" },
    search_target: { label: "图片/OCR 目标" },
    region_text: { label: "图片/OCR 坐标范围" },
    confidence_text: { label: "图片/OCR 置信度" },
    retry_value: { label: "未找到后重试时间" },
    retry_random: { label: "重试随机时间" },
    pic_range_random: { label: "图片/OCR 定位移动随机" },
    move_time: { label: "移动操作用时" },
    jump_mark: { label: "跳转标记" },
    disable_grayscale: { label: "图片不使用灰度匹配" },
    note: { label: "备注" },
    "branch.trigger": { label: "分支触发条件" },
    "branch.mode": { label: "分支模式" },
    "branch.primary_target": { label: "分支主目标" },
    "branch.secondary_target": { label: "分支次目标" },
  },
  helpers: {
    capture_point: {
      label: "拾取屏幕坐标点",
      capability: "capture_point",
      target_fields: ["param_text"],
    },
    capture_image_region: {
      label: "框选区域并保存图片",
      capability: "capture_region",
      target_fields: ["search_target", "region_text"],
    },
    capture_ocr_region: {
      label: "框选区域并提取 OCR 候选",
      capability: "capture_region",
      target_fields: ["search_target", "region_text"],
    },
    select_ocr_candidate: {
      label: "从 OCR 候选中选择文本",
      capability: "capture_region",
      target_fields: ["search_target"],
    },
  },
  operations: {
    click: {
      label: "鼠标点击",
      category: "mouse",
      category_label: "鼠标",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    mDown: {
      label: "鼠标按下",
      category: "mouse",
      category_label: "鼠标",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    mUp: {
      label: "鼠标松开",
      category: "mouse",
      category_label: "鼠标",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    mMove: {
      label: "相对移动",
      category: "mouse",
      category_label: "鼠标",
      visible_fields: ["param_text", "move_time", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    mMoveTo: {
      label: "绝对移动",
      category: "mouse",
      category_label: "鼠标",
      visible_fields: ["param_text", "move_time", ...COMMON_FIELDS],
      allowed_helpers: ["capture_point"],
    },
    press: {
      label: "按键",
      category: "keyboard",
      category_label: "键盘",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    kDown: {
      label: "按键按下",
      category: "keyboard",
      category_label: "键盘",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    kUp: {
      label: "按键松开",
      category: "keyboard",
      category_label: "键盘",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    write: {
      label: "输入文本",
      category: "keyboard",
      category_label: "键盘",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    pic: {
      label: "识图",
      category: "visual",
      category_label: "识别",
      visible_fields: [...VISUAL_FIELDS, "disable_grayscale"],
      allowed_helpers: ["capture_image_region"],
    },
    ocr: {
      label: "OCR 识别",
      category: "visual",
      category_label: "识别",
      visible_fields: [...VISUAL_FIELDS],
      allowed_helpers: ["capture_ocr_region", "select_ocr_candidate"],
    },
    notify: {
      label: "通知",
      category: "system",
      category_label: "系统",
      visible_fields: ["param_text", ...COMMON_FIELDS],
      allowed_helpers: [],
    },
    jmp: {
      label: "跳转",
      category: "flow",
      category_label: "流程",
      visible_fields: ["param_text", "jump_mark", "note"],
      allowed_helpers: [],
    },
  },
};

const MOUSE_BUTTON_OPTIONS = ["left", "middle", "right", "x1", "x2"];

export type ParamEditorConfig = {
  label: string;
  placeholder?: string;
  kind: "text" | "select" | "jump-target";
  options?: string[];
  helper?: OperationHelper | null;
};

export function getOperationMetadata(bootstrap: BootstrapDTO | null): OperationMetadataDTO {
  return bootstrap?.operation_metadata ?? FALLBACK_OPERATION_METADATA;
}

export function getOperationEntries(bootstrap: BootstrapDTO | null): Array<[string, OperationMetaDTO]> {
  const metadata = getOperationMetadata(bootstrap);
  const explicitTypes = bootstrap?.operation_types ?? [];
  if (explicitTypes.length) {
    return explicitTypes
      .map((operation) => [operation, normalizeOperationMeta(metadata.operations[operation] ?? createFallbackOperationMeta(operation))] as [string, OperationMetaDTO])
      .filter((entry) => Boolean(entry[0]));
  }
  return Object.entries(metadata.operations).map(([operation, meta]) => [operation, normalizeOperationMeta(meta)]);
}

export function getOperationMeta(
  bootstrap: BootstrapDTO | null,
  operation: string,
): OperationMetaDTO {
  const metadata = getOperationMetadata(bootstrap);
  return normalizeOperationMeta(metadata.operations[operation] ?? createFallbackOperationMeta(operation));
}

export function getFieldLabel(bootstrap: BootstrapDTO | null, key: string): string {
  return getOperationMetadata(bootstrap).fields[key]?.label ?? key;
}

export function getHelperLabel(bootstrap: BootstrapDTO | null, key: OperationHelper): string {
  return getOperationMetadata(bootstrap).helpers[key]?.label ?? key;
}

export function getAllowedHelpers(bootstrap: BootstrapDTO | null, operation: string): OperationHelper[] {
  return [...getOperationMeta(bootstrap, operation).allowed_helpers];
}

export function isFieldVisible(bootstrap: BootstrapDTO | null, operation: string, field: string): boolean {
  return hasVisibleField(getOperationMeta(bootstrap, operation), field);
}

export function hasVisibleField(meta: OperationMetaDTO | null | undefined, field: string): boolean {
  if (!meta) {
    return false;
  }
  const visible = new Set(meta.visible_fields);
  if (visible.has(field as never)) {
    return true;
  }
  if (field === "wait") {
    return WAIT_FIELDS.some((key) => visible.has(key));
  }
  if (field === "retry") {
    return RETRY_FIELDS.some((key) => visible.has(key));
  }
  if (field === "branch") {
    return BRANCH_FIELDS.some((key) => visible.has(key));
  }
  if (WAIT_FIELDS.includes(field as (typeof WAIT_FIELDS)[number])) {
    return visible.has("wait");
  }
  if (RETRY_FIELDS.includes(field as (typeof RETRY_FIELDS)[number])) {
    return visible.has("retry");
  }
  if (BRANCH_FIELDS.includes(field as (typeof BRANCH_FIELDS)[number])) {
    return visible.has("branch");
  }
  return false;
}

export function createNodeForOperation(operation: string): OperationNodeDTO {
  const baseNode: OperationNodeDTO = {
    node_id: "",
    index: 0,
    operation,
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
    branch: {
      trigger: "none",
      mode: "none",
      primary_target: "",
      secondary_target: "",
    },
    raw_extra: {},
  };

  if (["click", "mDown", "mUp"].includes(operation)) {
    baseNode.param_text = "left";
  }
  if (operation === "pic" || operation === "ocr") {
    baseNode.confidence_text = "0.8";
    baseNode.retry_value = "1";
  }
  return baseNode;
}

export function normalizeNodeForOperation(node: OperationNodeDTO, operation: string): OperationNodeDTO {
  const next = { ...createNodeForOperation(operation), ...node, operation, branch: { ...node.branch } };
  if (!["click", "mDown", "mUp", "mMove", "mMoveTo", "press", "kDown", "kUp", "write", "notify", "jmp"].includes(operation)) {
    next.param_text = "";
  }
  if (operation !== "mMove" && operation !== "mMoveTo" && operation !== "pic" && operation !== "ocr") {
    next.move_time = "";
  }
  if (operation !== "pic" && operation !== "ocr") {
    next.search_target = "";
    next.region_text = "";
    next.confidence_text = "";
    next.retry_value = "";
    next.retry_random = "";
    next.pic_range_random = false;
    next.disable_grayscale = false;
    next.branch = {
      trigger: "none",
      mode: "none",
      primary_target: "",
      secondary_target: "",
    };
  }
  if (operation !== "pic") {
    next.disable_grayscale = false;
  }
  return next;
}

export function getParamEditorConfig(operation: string, jumpTargets: string[]): ParamEditorConfig {
  if (["click", "mDown", "mUp"].includes(operation)) {
    return {
      label: "按钮",
      kind: "select",
      options: MOUSE_BUTTON_OPTIONS,
    };
  }
  if (operation === "mMove") {
    return {
      label: "相对坐标",
      placeholder: "x;y",
      kind: "text",
    };
  }
  if (operation === "mMoveTo") {
    return {
      label: "绝对坐标",
      placeholder: "x;y",
      kind: "text",
      helper: "capture_point",
    };
  }
  if (["press", "kDown", "kUp"].includes(operation)) {
    return {
      label: "按键",
      placeholder: "如 enter / esc / a",
      kind: "text",
    };
  }
  if (operation === "write") {
    return {
      label: "输入文本",
      placeholder: "写入文本内容",
      kind: "text",
    };
  }
  if (operation === "notify") {
    return {
      label: "通知文本",
      placeholder: "通知内容",
      kind: "text",
    };
  }
  if (operation === "jmp") {
    return {
      label: "跳转目标",
      placeholder: "序号或跳转标记",
      kind: "jump-target",
      options: jumpTargets,
    };
  }
  return {
    label: "操作参数",
    kind: "text",
  };
}

export function getSearchTargetLabel(operation: string): string {
  if (operation === "pic") {
    return "图片文件";
  }
  if (operation === "ocr") {
    return "OCR 文本";
  }
  return "目标";
}

export function getBranchPrimaryLabel(mode: string): string {
  if (mode === "subflow") {
    return "子流程文件";
  }
  if (mode === "jump_pair") {
    return "命中后跳转";
  }
  return "主目标";
}

export function getBranchSecondaryLabel(mode: string): string {
  if (mode === "jump_pair") {
    return "未命中跳转";
  }
  return "次目标";
}

export function getBranchOptions(flowNames: string[], jumpTargets: string[]): string[] {
  return Array.from(new Set([...flowNames, ...jumpTargets])).filter(Boolean);
}

export function getNodeRowView(node: OperationNodeDTO): NodeRowViewDTO {
  const operationMeta = FALLBACK_OPERATION_METADATA.operations[node.operation] ?? createFallbackOperationMeta(node.operation);
  const persistedView = node.row_view;
  const branchText = buildBranchText(node);
  const summary = buildSummary(node, operationMeta.label);
  const secondaryText = node.note || node.jump_mark || branchText || "-";
  const locatorText = buildLocatorText(node);
  const regionText = node.region_text || "-";
  const timingText = buildTimingText(node);
  return {
    operation_label: persistedView?.operation_label || operationMeta.label,
    category: persistedView?.category || operationMeta.category,
    category_label: persistedView?.category_label || operationMeta.category_label,
    summary,
    secondary_text: secondaryText,
    locator_text: locatorText,
    region_text: regionText,
    timing_text: timingText,
    branch_text: branchText || "-",
    search_text: [node.operation, operationMeta.label, summary, secondaryText, locatorText, regionText, branchText, node.note, node.jump_mark]
      .filter(Boolean)
      .join(" "),
  };
}

function buildSummary(node: OperationNodeDTO, operationLabel: string): string {
  if (node.operation === "pic" || node.operation === "ocr") {
    return `${operationLabel} ${node.search_target || "(未设置)"}`;
  }
  if (node.operation === "jmp") {
    return `跳转到 ${node.param_text || "(未设置)"}`;
  }
  if (node.param_text) {
    return `${operationLabel} ${node.param_text}`;
  }
  return operationLabel;
}

function buildBranchText(node: OperationNodeDTO): string {
  if (node.branch.trigger === "none" || node.branch.mode === "none") {
    return "";
  }
  if (node.branch.mode === "subflow") {
    return `${node.branch.trigger} -> ${node.branch.primary_target || "(未设置)"}`;
  }
  if (node.branch.mode === "jump_pair") {
    return `${node.branch.trigger} -> ${node.branch.primary_target || "(未设置)"} / ${node.branch.secondary_target || "(未设置)"}`;
  }
  return `${node.branch.trigger} -> ${node.branch.primary_target || "(未设置)"}`;
}

function buildLocatorText(node: OperationNodeDTO): string {
  if (node.operation === "jmp") {
    return node.param_text || "(未设置)";
  }

  if ((node.operation === "pic" || node.operation === "ocr") && node.branch.trigger !== "none" && node.branch.mode !== "none") {
    if (node.branch.mode === "jump_pair") {
      const [existTarget, notExistTarget] = branchJumpPairTargets(node);
      return `exist-> ${existTarget} · notExist-> ${notExistTarget}`;
    }
    if (node.branch.mode === "subflow") {
      return `启动 ${node.branch.primary_target || "(未设置)"}`;
    }
  }

  if (node.search_target) {
    return node.search_target;
  }
  if (node.param_text) {
    return node.param_text;
  }
  return "(未设置)";
}

function branchJumpPairTargets(node: OperationNodeDTO): [string, string] {
  const primaryTarget = node.branch.primary_target || "(未设置)";
  const secondaryTarget = node.branch.secondary_target || "(未设置)";
  if (node.branch.trigger === "notExist") {
    return [secondaryTarget, primaryTarget];
  }
  return [primaryTarget, secondaryTarget];
}

function pairText(first: string, second: string): string {
  if (first && second) {
    return `${first};${second}`;
  }
  return first || "-";
}

function buildTimingText(node: OperationNodeDTO): string {
  const waitText = `等待 ${pairText(node.wait_value, node.wait_random)}`;
  if (node.operation === "pic" || node.operation === "ocr") {
    return `${waitText} · 重试 ${pairText(node.retry_value, node.retry_random)}`;
  }
  return waitText;
}

function normalizeOperationMeta(meta: OperationMetaDTO): OperationMetaDTO {
  const visibleFields = new Set(meta.visible_fields);
  if (WAIT_FIELDS.some((field) => visibleFields.has(field))) {
    visibleFields.add("wait");
  }
  if (RETRY_FIELDS.some((field) => visibleFields.has(field))) {
    visibleFields.add("retry");
  }
  if (BRANCH_FIELDS.some((field) => visibleFields.has(field))) {
    visibleFields.add("branch");
  }
  return {
    ...meta,
    visible_fields: [...visibleFields],
  };
}

function createFallbackOperationMeta(operation: string): OperationMetaDTO {
  return {
    label: operation || "未知操作",
    category: "unknown",
    category_label: "未知",
    visible_fields: ["param_text", ...COMMON_FIELDS],
    allowed_helpers: [],
  };
}
