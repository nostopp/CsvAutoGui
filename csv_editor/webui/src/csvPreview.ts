import type { FlowDocumentDTO, OperationNodeDTO } from "./types";

const CSV_COLUMNS = [
  "序号",
  "操作",
  "操作参数",
  "完成后等待时间",
  "图片/ocr名称",
  "图片/ocr坐标范围",
  "图片/ocr置信度",
  "未找到图片/ocr重试时间",
  "图片/ocr定位移动随机",
  "移动操作用时",
  "跳转标记",
  "图片不使用灰度匹配",
  "备注",
];

export function buildCsvPreview(flow: FlowDocumentDTO): string {
  const rows = [CSV_COLUMNS.join(",")];
  for (const node of flow.nodes) {
    rows.push(
      [
        String(node.index),
        node.operation,
        encodeParam(node),
        encodePair(node.wait_value, node.wait_random),
        node.search_target,
        node.region_text,
        node.confidence_text,
        encodePair(node.retry_value, node.retry_random),
        node.pic_range_random ? "1" : "",
        node.move_time,
        node.jump_mark,
        node.disable_grayscale ? "1" : "",
        node.note,
      ]
        .map(escapeCsv)
        .join(","),
    );
  }
  return rows.join("\r\n");
}

function encodeParam(node: OperationNodeDTO): string {
  if (node.operation === "pic" || node.operation === "ocr") {
    if (node.branch.trigger !== "none" && node.branch.mode !== "none") {
      if (node.branch.mode === "subflow") {
        return `${node.branch.trigger};${node.branch.primary_target}`;
      }
      if (node.branch.mode === "jump_pair") {
        return `${node.branch.trigger};${node.branch.primary_target};${node.branch.secondary_target}`;
      }
    }
  }
  return node.param_text;
}

function encodePair(first: string, second: string): string {
  const left = first.trim();
  const right = second.trim();
  return left && right ? `${left};${right}` : left;
}

function escapeCsv(value: string): string {
  if (value.includes(",") || value.includes("\"") || value.includes("\n")) {
    return `"${value.replaceAll("\"", "\"\"")}"`;
  }
  return value;
}
