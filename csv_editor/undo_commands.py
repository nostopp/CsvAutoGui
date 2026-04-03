from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from csv_editor.domain.models import FlowDocument, OperationNode


class RefreshAwareCommand(QUndoCommand):
    def __init__(self, window, text: str) -> None:
        super().__init__(text)
        self.window = window

    def _refresh(self, selected_node_id: str | None = None) -> None:
        if selected_node_id is not None:
            self.window.current_node_id = selected_node_id
        self.window._refresh_validation()
        self.window._refresh_node_table()
        self.window._refresh_preview()


class UpdateNodeCommand(RefreshAwareCommand):
    COMMAND_ID = 1001

    def __init__(self, window, flow_name: str, before: OperationNode, after: OperationNode, text: str = "编辑节点") -> None:
        super().__init__(window, text)
        self.flow_name = flow_name
        self.node_id = before.node_id
        self.before = before.clone()
        self.after = after.clone()

    def id(self) -> int:
        return self.COMMAND_ID

    def mergeWith(self, other) -> bool:
        if not isinstance(other, UpdateNodeCommand):
            return False
        if self.flow_name != other.flow_name or self.node_id != other.node_id:
            return False
        self.after = other.after.clone()
        return True

    def undo(self) -> None:
        node = self._resolve_node()
        if node is None:
            return
        node.apply_from(self.before)
        self._refresh(self.node_id)

    def redo(self) -> None:
        node = self._resolve_node()
        if node is None:
            return
        node.apply_from(self.after)
        self._refresh(self.node_id)

    def _resolve_node(self) -> OperationNode | None:
        flow = self._resolve_flow()
        if flow is None:
            return None
        return flow.get_node(self.node_id)

    def _resolve_flow(self) -> FlowDocument | None:
        return self.window.document.get_flow(self.flow_name) if self.window.document else None


class InsertNodeCommand(RefreshAwareCommand):
    def __init__(self, window, flow_name: str, node: OperationNode, index: int, text: str = "新增节点") -> None:
        super().__init__(window, text)
        self.flow_name = flow_name
        self.node = node.clone()
        self.index = index

    def undo(self) -> None:
        flow = self._resolve_flow()
        if flow is None:
            return
        flow.nodes = [item for item in flow.nodes if item.node_id != self.node.node_id]
        flow.reindex()
        next_node_id = flow.nodes[min(self.index - 1, len(flow.nodes) - 1)].node_id if flow.nodes else None
        self._refresh(next_node_id)

    def redo(self) -> None:
        flow = self._resolve_flow()
        if flow is None:
            return
        if flow.get_node(self.node.node_id) is None:
            flow.nodes.insert(min(self.index, len(flow.nodes)), self.node.clone())
        flow.reindex()
        self._refresh(self.node.node_id)

    def _resolve_flow(self) -> FlowDocument | None:
        return self.window.document.get_flow(self.flow_name) if self.window.document else None


class DeleteNodeCommand(RefreshAwareCommand):
    def __init__(self, window, flow_name: str, node: OperationNode, index: int, text: str = "删除节点") -> None:
        super().__init__(window, text)
        self.flow_name = flow_name
        self.node = node.clone()
        self.index = index

    def undo(self) -> None:
        flow = self._resolve_flow()
        if flow is None:
            return
        if flow.get_node(self.node.node_id) is None:
            flow.nodes.insert(min(self.index, len(flow.nodes)), self.node.clone())
        flow.reindex()
        self._refresh(self.node.node_id)

    def redo(self) -> None:
        flow = self._resolve_flow()
        if flow is None:
            return
        flow.nodes = [item for item in flow.nodes if item.node_id != self.node.node_id]
        flow.reindex()
        next_node_id = flow.nodes[min(self.index, len(flow.nodes) - 1)].node_id if flow.nodes else None
        self._refresh(next_node_id)

    def _resolve_flow(self) -> FlowDocument | None:
        return self.window.document.get_flow(self.flow_name) if self.window.document else None


class MoveNodeCommand(RefreshAwareCommand):
    def __init__(self, window, flow_name: str, node_id: str, from_index: int, to_index: int, text: str) -> None:
        super().__init__(window, text)
        self.flow_name = flow_name
        self.node_id = node_id
        self.from_index = from_index
        self.to_index = to_index

    def undo(self) -> None:
        self._move(self.to_index, self.from_index)

    def redo(self) -> None:
        self._move(self.from_index, self.to_index)

    def _move(self, old_index: int, new_index: int) -> None:
        flow = self._resolve_flow()
        if flow is None:
            return
        if old_index < 0 or old_index >= len(flow.nodes) or new_index < 0 or new_index >= len(flow.nodes):
            return
        node = flow.nodes.pop(old_index)
        flow.nodes.insert(new_index, node)
        flow.reindex()
        self._refresh(self.node_id)

    def _resolve_flow(self) -> FlowDocument | None:
        return self.window.document.get_flow(self.flow_name) if self.window.document else None
