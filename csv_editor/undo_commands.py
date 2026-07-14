from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from csv_editor.controllers.change_set import EditorChangeSet
from csv_editor.controllers.document_controller import EditorDocumentController
from csv_editor.domain.models import OperationNode
from csv_editor.domain.node_patch import NodePatch


ChangeCallback = Callable[[EditorChangeSet], None]


class ControllerCommand(QUndoCommand):
    def __init__(
        self,
        controller: EditorDocumentController,
        *,
        on_change: ChangeCallback | None,
        text: str,
    ) -> None:
        super().__init__(text)
        self.controller = controller
        self._on_change = on_change

    def _publish(self, change_set: EditorChangeSet) -> None:
        if self._on_change is not None:
            self._on_change(change_set)


class UpdateNodeCommand(ControllerCommand):
    COMMAND_ID = 1001

    def __init__(
        self,
        controller: EditorDocumentController,
        flow_name: str,
        before: OperationNode,
        after: OperationNode,
        changed_fields: frozenset[str],
        *,
        on_change: ChangeCallback | None = None,
        text: str = "编辑节点",
    ) -> None:
        super().__init__(controller, on_change=on_change, text=text)
        self.flow_name = flow_name
        self.node_id = before.node_id
        self.before = before.clone()
        self.after = after.clone()
        self.changed_fields = frozenset(changed_fields)

    @classmethod
    def from_patch(
        cls,
        controller: EditorDocumentController,
        flow_name: str,
        patch: NodePatch,
        *,
        on_change: ChangeCallback | None = None,
        text: str = "编辑节点",
    ) -> "UpdateNodeCommand | None":
        prepared = controller.prepare_node_patch(flow_name, patch)
        if prepared is None:
            return None
        before, after, changed_fields = prepared
        return cls(
            controller,
            flow_name,
            before,
            after,
            changed_fields,
            on_change=on_change,
            text=text,
        )

    def id(self) -> int:
        return self.COMMAND_ID

    def mergeWith(self, other) -> bool:
        if not isinstance(other, UpdateNodeCommand):
            return False
        if self.controller is not other.controller:
            return False
        if self.flow_name != other.flow_name or self.node_id != other.node_id:
            return False
        self.after = other.after.clone()
        self.changed_fields = self.changed_fields | other.changed_fields
        return True

    def undo(self) -> None:
        self._publish(
            self.controller.apply_node_state(
                self.flow_name,
                self.before,
                self.changed_fields,
            )
        )

    def redo(self) -> None:
        self._publish(
            self.controller.apply_node_state(
                self.flow_name,
                self.after,
                self.changed_fields,
            )
        )


class InsertNodeCommand(ControllerCommand):
    def __init__(
        self,
        controller: EditorDocumentController,
        flow_name: str,
        node: OperationNode,
        index: int,
        *,
        on_change: ChangeCallback | None = None,
        text: str = "新增节点",
    ) -> None:
        super().__init__(controller, on_change=on_change, text=text)
        self.flow_name = flow_name
        self.node = node.clone()
        self.index = index

    def undo(self) -> None:
        self._publish(
            self.controller.delete_node(
                self.flow_name,
                self.node.node_id,
                preferred_selection_index=self.index - 1,
            )
        )

    def redo(self) -> None:
        self._publish(
            self.controller.insert_node(
                self.flow_name,
                self.node,
                self.index,
            )
        )


class DeleteNodeCommand(ControllerCommand):
    def __init__(
        self,
        controller: EditorDocumentController,
        flow_name: str,
        node: OperationNode,
        index: int,
        *,
        on_change: ChangeCallback | None = None,
        text: str = "删除节点",
    ) -> None:
        super().__init__(controller, on_change=on_change, text=text)
        self.flow_name = flow_name
        self.node = node.clone()
        self.index = index

    def undo(self) -> None:
        self._publish(
            self.controller.insert_node(
                self.flow_name,
                self.node,
                self.index,
            )
        )

    def redo(self) -> None:
        self._publish(
            self.controller.delete_node(
                self.flow_name,
                self.node.node_id,
                preferred_selection_index=self.index,
            )
        )


class MoveNodeCommand(ControllerCommand):
    def __init__(
        self,
        controller: EditorDocumentController,
        flow_name: str,
        node_id: str,
        from_index: int,
        to_index: int,
        *,
        on_change: ChangeCallback | None = None,
        text: str,
    ) -> None:
        super().__init__(controller, on_change=on_change, text=text)
        self.flow_name = flow_name
        self.node_id = node_id
        self.from_index = from_index
        self.to_index = to_index

    def undo(self) -> None:
        self._publish(
            self.controller.move_node(
                self.flow_name,
                self.node_id,
                self.from_index,
            )
        )

    def redo(self) -> None:
        self._publish(
            self.controller.move_node(
                self.flow_name,
                self.node_id,
                self.to_index,
            )
        )
