from __future__ import annotations

from pathlib import Path
from typing import Collection

from csv_editor.controllers.change_set import (
    ChangeImpact,
    EditorChangeSet,
    change_impact_for_fields,
)
from csv_editor.domain.models import (
    EditorDocument,
    FlowDocument,
    OperationNode,
    ValidationIssue,
)
from csv_editor.domain.node_patch import NodePatch, apply_node_patch as apply_patch_to_node
from csv_editor.io.csv_codec import CsvEditorCodec
from csv_editor.services.validation import (
    validate_document as validate_editor_document,
    validate_flow as validate_editor_flow,
    validate_node as validate_editor_node,
)


class EditorDocumentController:
    def __init__(self, codec: CsvEditorCodec | None = None) -> None:
        self.codec = codec or CsvEditorCodec()
        self._document: EditorDocument | None = None
        self._current_flow_name: str | None = None
        self._current_node_id: str | None = None
        self._issues_by_flow: dict[
            str,
            dict[str | None, tuple[ValidationIssue, ...]],
        ] = {}

    @property
    def document(self) -> EditorDocument | None:
        return self._document

    @property
    def current_flow_name(self) -> str | None:
        return self._current_flow_name

    @property
    def current_node_id(self) -> str | None:
        return self._current_node_id

    @property
    def current_flow(self) -> FlowDocument | None:
        if self._document is None or self._current_flow_name is None:
            return None
        return self._document.get_flow(self._current_flow_name)

    @property
    def current_node(self) -> OperationNode | None:
        flow = self.current_flow
        if flow is None or self._current_node_id is None:
            return None
        return flow.get_node(self._current_node_id)

    @property
    def issues(self) -> list[ValidationIssue]:
        if self._document is None:
            return []
        issues: list[ValidationIssue] = []
        for flow in self._document.flows:
            issues.extend(self.issues_for_flow(flow.filename))
        return issues

    def issues_for_flow(self, flow_name: str) -> list[ValidationIssue]:
        flow = self._get_flow(flow_name)
        buckets = self._issues_by_flow.get(flow_name, {})
        issues: list[ValidationIssue] = []
        emitted_keys: set[str | None] = set()
        for node in flow.nodes:
            issues.extend(buckets.get(node.node_id, ()))
            emitted_keys.add(node.node_id)
        issues.extend(buckets.get(None, ()))
        emitted_keys.add(None)
        for node_id, bucket in buckets.items():
            if node_id not in emitted_keys:
                issues.extend(bucket)
        return issues

    def issue_node_ids(self, flow_name: str) -> frozenset[str]:
        return frozenset(
            issue.node_id
            for issue in self.issues_for_flow(flow_name)
            if issue.node_id is not None
        )

    def open_document(self, root_path: Path) -> EditorChangeSet:
        document = self.codec.load_document(root_path)
        self._document = document
        selected_flow_name = document.state.selected_flow
        if document.get_flow(selected_flow_name) is None:
            selected_flow_name = document.flows[0].filename if document.flows else None
        selected_flow = document.get_flow(selected_flow_name) if selected_flow_name else None
        selected_node_id = document.state.selected_node_id
        if selected_flow is None or selected_flow.get_node(selected_node_id or "") is None:
            selected_node_id = selected_flow.nodes[0].node_id if selected_flow and selected_flow.nodes else None
        self._set_selection(selected_flow_name, selected_node_id)
        self.validate_document()
        return EditorChangeSet(
            impact=ChangeImpact.DOCUMENT_STRUCTURE,
            selected_node_id=self._current_node_id,
        )

    def reload_document(self) -> EditorChangeSet:
        if self._document is None:
            raise RuntimeError("尚未打开编辑器文档")
        return self.open_document(self._document.root_path)

    def save_document(self) -> None:
        if self._document is None:
            raise RuntimeError("尚未打开编辑器文档")
        self.codec.save_document(self._document)
        self.validate_document()

    def flow_to_csv_text(self, flow_name: str | None = None) -> str:
        flow = self._get_flow(flow_name or self._current_flow_name)
        return self.codec.flow_to_csv_text(flow)

    def validate_document(self) -> list[ValidationIssue]:
        if self._document is None:
            self._issues_by_flow = {}
            return []
        issues = validate_editor_document(self._document)
        self._issues_by_flow = _group_issues_by_flow(issues)
        for flow in self._document.flows:
            self._issues_by_flow.setdefault(flow.filename, {})
        return self.issues

    def select_flow(self, flow_name: str) -> None:
        flow = self._get_flow(flow_name)
        selected_node_id = flow.nodes[0].node_id if flow.nodes else None
        self._set_selection(flow.filename, selected_node_id)

    def select_node(self, node_id: str | None) -> None:
        flow = self.current_flow
        if flow is None:
            if node_id is not None:
                raise ValueError("当前没有可选择节点的流程")
            self._set_selection(self._current_flow_name, None)
            return
        if node_id is not None and flow.get_node(node_id) is None:
            raise ValueError(f"节点不属于当前流程: {node_id}")
        self._set_selection(flow.filename, node_id)

    def prepare_node_patch(
        self,
        flow_name: str,
        patch: NodePatch,
    ) -> tuple[OperationNode, OperationNode, frozenset[str]] | None:
        node = self._get_node(flow_name, patch.node_id)
        before = node.clone()
        after = node.clone()
        apply_patch_to_node(after, patch)
        change_impact_for_fields(patch.changed_fields, operation=after.operation)
        actual_fields = frozenset(
            field_name
            for field_name in patch.changed_fields
            if _field_value(before, field_name) != _field_value(after, field_name)
        )
        if not actual_fields:
            return None
        return before, after, actual_fields

    def apply_node_patch(
        self,
        patch: NodePatch,
        flow_name: str | None = None,
    ) -> EditorChangeSet | None:
        target_flow_name = flow_name or self._current_flow_name
        if target_flow_name is None:
            raise RuntimeError("当前没有可编辑流程")
        prepared = self.prepare_node_patch(target_flow_name, patch)
        if prepared is None:
            return None
        _, after, changed_fields = prepared
        return self.apply_node_state(target_flow_name, after, changed_fields)

    def apply_node_state(
        self,
        flow_name: str,
        snapshot: OperationNode,
        changed_fields: Collection[str],
    ) -> EditorChangeSet:
        node = self._get_node(flow_name, snapshot.node_id)
        fields = frozenset(changed_fields)
        change_impact_for_fields(fields, operation=snapshot.operation)
        node.apply_from(snapshot)
        self._set_selection(flow_name, node.node_id)
        change_set = self._node_change_set(flow_name, node, fields)
        self._revalidate_for_change(change_set)
        return change_set

    def insert_node(
        self,
        flow_name: str,
        node: OperationNode,
        index: int,
    ) -> EditorChangeSet:
        flow = self._get_flow(flow_name)
        if flow.get_node(node.node_id) is not None:
            raise ValueError(f"节点已存在: {node.node_id}")
        target_index = min(max(index, 0), len(flow.nodes))
        inserted = node.clone()
        flow.nodes.insert(target_index, inserted)
        flow.reindex()
        self._set_selection(flow_name, inserted.node_id)
        change_set = self._structure_change_set(flow_name, inserted.node_id)
        self._revalidate_for_change(change_set)
        return change_set

    def delete_node(
        self,
        flow_name: str,
        node_id: str,
        *,
        preferred_selection_index: int | None = None,
    ) -> EditorChangeSet:
        flow = self._get_flow(flow_name)
        node_index = _node_index(flow, node_id)
        flow.nodes.pop(node_index)
        flow.reindex()
        selection_index = node_index if preferred_selection_index is None else preferred_selection_index
        if flow.nodes:
            selection_index = min(max(selection_index, 0), len(flow.nodes) - 1)
            selected_node_id = flow.nodes[selection_index].node_id
        else:
            selected_node_id = None
        self._set_selection(flow_name, selected_node_id)
        change_set = self._structure_change_set(flow_name, node_id)
        self._revalidate_for_change(change_set)
        return change_set

    def move_node(
        self,
        flow_name: str,
        node_id: str,
        to_index: int,
    ) -> EditorChangeSet:
        flow = self._get_flow(flow_name)
        if to_index < 0 or to_index >= len(flow.nodes):
            raise IndexError(f"节点目标位置越界: {to_index}")
        from_index = _node_index(flow, node_id)
        node = flow.nodes.pop(from_index)
        flow.nodes.insert(to_index, node)
        flow.reindex()
        self._set_selection(flow_name, node_id)
        change_set = self._structure_change_set(flow_name, node_id)
        self._revalidate_for_change(change_set)
        return change_set

    def _revalidate_for_change(self, change_set: EditorChangeSet) -> None:
        if change_set.impact is ChangeImpact.DISPLAY_ONLY:
            return
        if change_set.impact is ChangeImpact.NODE_VALIDATION:
            if change_set.flow_name is None:
                self.validate_document()
                return
            for node_id in change_set.node_ids:
                self._revalidate_node(change_set.flow_name, node_id)
            return
        if change_set.impact in {
            ChangeImpact.REFERENCE_GRAPH,
            ChangeImpact.FLOW_STRUCTURE,
        }:
            if change_set.flow_name is None:
                self.validate_document()
            else:
                self._revalidate_flow(change_set.flow_name)
            return
        self.validate_document()

    def _revalidate_node(self, flow_name: str, node_id: str) -> None:
        if self._document is None:
            return
        flow = self._get_flow(flow_name)
        node = self._get_node(flow_name, node_id)
        flow_lookup = {item.filename: item for item in self._document.flows}
        issues = validate_editor_node(
            self._document.root_path,
            flow,
            node,
            flow_lookup,
        )
        flow_buckets = self._issues_by_flow.setdefault(flow_name, {})
        if issues:
            flow_buckets[node_id] = tuple(issues)
        else:
            flow_buckets.pop(node_id, None)

    def _revalidate_flow(self, flow_name: str) -> None:
        if self._document is None:
            return
        flow = self._get_flow(flow_name)
        flow_lookup = {item.filename: item for item in self._document.flows}
        issues = validate_editor_flow(
            self._document.root_path,
            flow,
            flow_lookup,
        )
        self._issues_by_flow[flow_name] = _group_flow_issues(issues)

    def _get_flow(self, flow_name: str | None) -> FlowDocument:
        if self._document is None:
            raise RuntimeError("尚未打开编辑器文档")
        if flow_name is None:
            raise ValueError("流程名不能为空")
        flow = self._document.get_flow(flow_name)
        if flow is None:
            raise ValueError(f"流程不存在: {flow_name}")
        return flow

    def _get_node(self, flow_name: str, node_id: str) -> OperationNode:
        flow = self._get_flow(flow_name)
        node = flow.get_node(node_id)
        if node is None:
            raise ValueError(f"节点不存在: {flow_name}/{node_id}")
        return node

    def _set_selection(
        self,
        flow_name: str | None,
        node_id: str | None,
    ) -> None:
        if flow_name is not None:
            flow = self._get_flow(flow_name)
            if node_id is not None and flow.get_node(node_id) is None:
                raise ValueError(f"节点不属于流程 {flow_name}: {node_id}")
        elif node_id is not None:
            raise ValueError("没有流程时不能选择节点")

        self._current_flow_name = flow_name
        self._current_node_id = node_id
        if self._document is not None:
            self._document.state.selected_flow = flow_name or ""
            self._document.state.selected_node_id = node_id

    def _node_change_set(
        self,
        flow_name: str,
        node: OperationNode,
        changed_fields: frozenset[str],
    ) -> EditorChangeSet:
        return EditorChangeSet(
            impact=change_impact_for_fields(
                changed_fields,
                operation=node.operation,
            ),
            flow_name=flow_name,
            node_ids=frozenset({node.node_id}),
            changed_fields=changed_fields,
            selected_node_id=self._current_node_id,
        )

    def _structure_change_set(
        self,
        flow_name: str,
        node_id: str,
    ) -> EditorChangeSet:
        return EditorChangeSet(
            impact=ChangeImpact.FLOW_STRUCTURE,
            flow_name=flow_name,
            node_ids=frozenset({node_id}),
            selected_node_id=self._current_node_id,
        )


def _field_value(node: OperationNode, field_name: str):
    if field_name.startswith("branch."):
        return getattr(node.branch, field_name.removeprefix("branch."))
    return getattr(node, field_name)


def _node_index(flow: FlowDocument, node_id: str) -> int:
    for index, node in enumerate(flow.nodes):
        if node.node_id == node_id:
            return index
    raise ValueError(f"节点不存在: {flow.filename}/{node_id}")


def _group_issues_by_flow(
    issues: list[ValidationIssue],
) -> dict[str, dict[str | None, tuple[ValidationIssue, ...]]]:
    grouped_lists: dict[str, dict[str | None, list[ValidationIssue]]] = {}
    for issue in issues:
        flow_buckets = grouped_lists.setdefault(issue.flow_name, {})
        flow_buckets.setdefault(issue.node_id, []).append(issue)
    return {
        flow_name: {
            node_id: tuple(bucket)
            for node_id, bucket in flow_buckets.items()
        }
        for flow_name, flow_buckets in grouped_lists.items()
    }


def _group_flow_issues(
    issues: list[ValidationIssue],
) -> dict[str | None, tuple[ValidationIssue, ...]]:
    grouped_lists: dict[str | None, list[ValidationIssue]] = {}
    for issue in issues:
        grouped_lists.setdefault(issue.node_id, []).append(issue)
    return {
        node_id: tuple(bucket)
        for node_id, bucket in grouped_lists.items()
    }
