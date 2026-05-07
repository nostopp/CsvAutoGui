import type { EditorDocumentDTO, OperationNodeDTO } from "./types";

export type EditorSelectionDTO = {
  selectedNodeIds: string[];
};

export type EditorCommand = {
  id: string;
  label: string;
  mergeKey: string | null;
  apply(draft: EditorDocumentDTO): void;
  revert(draft: EditorDocumentDTO): void;
};

export type EditorTransaction = {
  id: string;
  label: string;
  mergeKey: string | null;
  commands: EditorCommand[];
  selectionAfter: EditorSelectionDTO | null;
};

function uniqueId() {
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`;
}

export function createEditorSelection(selectedNodeIds: string[]): EditorSelectionDTO {
  return { selectedNodeIds: [...selectedNodeIds] };
}

export function createEditorCommand(
  label: string,
  apply: (draft: EditorDocumentDTO) => void,
  revert: (draft: EditorDocumentDTO) => void,
  options?: {
    id?: string;
    mergeKey?: string | null;
  },
): EditorCommand {
  return {
    id: options?.id ?? uniqueId(),
    label,
    mergeKey: options?.mergeKey ?? null,
    apply,
    revert,
  };
}

export function createEditorTransaction(
  label: string,
  commands: EditorCommand[],
  options?: {
    id?: string;
    mergeKey?: string | null;
    selectionAfter?: EditorSelectionDTO | null;
  },
): EditorTransaction {
  return {
    id: options?.id ?? uniqueId(),
    label,
    mergeKey: options?.mergeKey ?? null,
    commands,
    selectionAfter: options?.selectionAfter ?? null,
  };
}

export function asTransaction(command: EditorCommand, selectionAfter?: EditorSelectionDTO | null): EditorTransaction {
  return createEditorTransaction(command.label, [command], {
    mergeKey: command.mergeKey,
    selectionAfter: selectionAfter ?? null,
  });
}

export function nodeFieldMergeKey(flowName: string, nodeId: string, field: keyof OperationNodeDTO): string {
  return `node-field:${flowName}:${nodeId}:${field}`;
}

export function createNodeFieldCommand(
  flowName: string,
  nodeId: string,
  field: keyof OperationNodeDTO,
  beforeValue: OperationNodeDTO[keyof OperationNodeDTO],
  afterValue: OperationNodeDTO[keyof OperationNodeDTO],
  applyNodeField: (draft: EditorDocumentDTO, flowName: string, nodeId: string, field: keyof OperationNodeDTO, value: OperationNodeDTO[keyof OperationNodeDTO]) => void,
): EditorCommand {
  return createEditorCommand(
    `Edit ${String(field)}`,
    (draft) => applyNodeField(draft, flowName, nodeId, field, afterValue),
    (draft) => applyNodeField(draft, flowName, nodeId, field, beforeValue),
    { mergeKey: nodeFieldMergeKey(flowName, nodeId, field) },
  );
}
