from __future__ import annotations

import csv
import io
from pathlib import Path

from csv_editor.domain.enums import BranchMode, BranchTrigger, OperationType
from csv_editor.domain.models import BranchConfig, EditorDocument, FlowDocument, OperationNode

CSV_COLUMNS = [
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
]


class CsvEditorCodec:
    def load_document(self, root_path: Path) -> EditorDocument:
        flows: list[FlowDocument] = []
        for csv_path in sorted(root_path.glob("*.csv"), key=lambda path: (path.name != "main.csv", path.name.lower())):
            flows.append(self.load_flow(csv_path))

        document = EditorDocument(root_path=root_path, flows=flows)
        document.ensure_main_first()
        return document

    def load_flow(self, path: Path) -> FlowDocument:
        nodes: list[OperationNode] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                nodes.append(self._decode_row(row))
        flow = FlowDocument(filename=path.name, nodes=nodes)
        flow.reindex()
        return flow

    def save_document(self, document: EditorDocument) -> None:
        for flow in document.flows:
            self.save_flow(document.root_path / flow.filename, flow)

    def save_flow(self, path: Path, flow: FlowDocument) -> None:
        flow.reindex()
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for node in flow.nodes:
                writer.writerow(self._encode_row(node))

    def flow_to_csv_text(self, flow: FlowDocument) -> str:
        flow.reindex()
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for node in flow.nodes:
            writer.writerow(self._encode_row(node))
        return buffer.getvalue()

    def _decode_row(self, row: dict[str, str]) -> OperationNode:
        branch = self._decode_branch((row.get("操作参数") or "").strip(), (row.get("操作") or "").strip())
        wait_value, wait_random = self._split_pair((row.get("完成后等待时间") or "").strip())
        retry_value, retry_random = self._split_pair((row.get("未找到图片/ocr重试时间") or "").strip())
        return OperationNode(
            index=self._safe_int((row.get("序号") or "").strip()),
            operation=(row.get("操作") or "").strip(),
            param_text=self._decode_param_text((row.get("操作参数") or "").strip(), (row.get("操作") or "").strip(), branch),
            wait_value=wait_value,
            wait_random=wait_random,
            search_target=(row.get("图片/ocr名称") or "").strip(),
            region_text=(row.get("图片/ocr坐标范围") or "").strip(),
            confidence_text=(row.get("图片/ocr置信度") or "").strip(),
            retry_value=retry_value,
            retry_random=retry_random,
            pic_range_random=(row.get("图片/ocr定位移动随机") or "").strip() == "1",
            move_time=(row.get("移动操作用时") or "").strip(),
            jump_mark=(row.get("跳转标记") or "").strip(),
            disable_grayscale=(row.get("图片不使用灰度匹配") or "").strip() == "1",
            note=(row.get("备注") or "").strip(),
            branch=branch,
        )

    def _encode_row(self, node: OperationNode) -> dict[str, str]:
        return {
            "序号": str(node.index),
            "操作": node.operation,
            "操作参数": self._encode_param_text(node),
            "完成后等待时间": self._join_pair(node.wait_value, node.wait_random),
            "图片/ocr名称": node.search_target,
            "图片/ocr坐标范围": node.region_text,
            "图片/ocr置信度": node.confidence_text,
            "未找到图片/ocr重试时间": self._join_pair(node.retry_value, node.retry_random),
            "图片/ocr定位移动随机": "1" if node.pic_range_random else "",
            "移动操作用时": node.move_time,
            "跳转标记": node.jump_mark,
            "图片不使用灰度匹配": "1" if node.disable_grayscale else "",
            "备注": node.note,
        }

    def _decode_branch(self, raw_param: str, operation: str) -> BranchConfig:
        if operation not in {OperationType.PIC.value, OperationType.OCR.value} or not raw_param:
            return BranchConfig()

        parts = raw_param.split(";")
        if len(parts) == 2 and parts[0] in {BranchTrigger.EXIST.value, BranchTrigger.NOT_EXIST.value}:
            return BranchConfig(
                trigger=BranchTrigger(parts[0]),
                mode=BranchMode.SUBFLOW,
                primary_target=parts[1],
            )
        if len(parts) == 3 and parts[0] in {BranchTrigger.EXIST.value, BranchTrigger.NOT_EXIST.value}:
            return BranchConfig(
                trigger=BranchTrigger(parts[0]),
                mode=BranchMode.JUMP_PAIR,
                primary_target=parts[1],
                secondary_target=parts[2],
            )
        return BranchConfig()

    def _decode_param_text(self, raw_param: str, operation: str, branch: BranchConfig) -> str:
        if operation in {OperationType.PIC.value, OperationType.OCR.value} and branch.is_enabled:
            return ""
        return raw_param

    def _encode_param_text(self, node: OperationNode) -> str:
        if node.operation in {OperationType.PIC.value, OperationType.OCR.value} and node.branch.is_enabled:
            if node.branch.mode is BranchMode.SUBFLOW:
                return f"{node.branch.trigger.value};{node.branch.primary_target}"
            if node.branch.mode is BranchMode.JUMP_PAIR:
                return f"{node.branch.trigger.value};{node.branch.primary_target};{node.branch.secondary_target}"
        return node.param_text.strip()

    @staticmethod
    def _split_pair(text: str) -> tuple[str, str]:
        if not text:
            return "", ""
        if ";" in text:
            first, second = text.split(";", 1)
            return first.strip(), second.strip()
        return text.strip(), ""

    @staticmethod
    def _join_pair(first: str, second: str) -> str:
        first = first.strip()
        second = second.strip()
        if first and second:
            return f"{first};{second}"
        return first

    @staticmethod
    def _safe_int(text: str) -> int:
        try:
            return int(text)
        except ValueError:
            return 0
