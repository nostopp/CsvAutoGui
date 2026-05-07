import type { EditorDocumentDTO, FlowDocumentDTO } from "./types";
import type { EditorSelectionDTO, EditorTransaction } from "./editorCommands";

export type AppliedEditorTransaction = {
  transaction: EditorTransaction;
  selectionBefore: EditorSelectionDTO;
  selectionAfter: EditorSelectionDTO;
};

export type EditorHistoryState = {
  present: EditorDocumentDTO | null;
  past: AppliedEditorTransaction[];
  future: AppliedEditorTransaction[];
  cleanIndex: number;
};

export function cloneEditorDocument<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function reindexFlowDocument(flow: FlowDocumentDTO): FlowDocumentDTO {
  return {
    ...flow,
    nodes: flow.nodes.map((node, index) => ({
      ...node,
      index: index + 1,
    })),
  };
}

export function normalizeEditorDocument(document: EditorDocumentDTO): EditorDocumentDTO {
  const cloned = cloneEditorDocument(document);
  cloned.flows = cloned.flows.map(reindexFlowDocument);
  return cloned;
}

export function getEditorSelection(selectedNodeIds: string[]): EditorSelectionDTO {
  return { selectedNodeIds: [...selectedNodeIds] };
}

export function applyEditorSelection(selection: EditorSelectionDTO | null | undefined): EditorSelectionDTO {
  return { selectedNodeIds: [...(selection?.selectedNodeIds ?? [])] };
}

export function createEditorHistoryState(document: EditorDocumentDTO | null): EditorHistoryState {
  return {
    present: document ? normalizeEditorDocument(document) : null,
    past: [],
    future: [],
    cleanIndex: 0,
  };
}

export function resetEditorHistoryState(document: EditorDocumentDTO | null): EditorHistoryState {
  return createEditorHistoryState(document);
}

export function canUndoEditorHistory(history: EditorHistoryState): boolean {
  return history.past.length > 0;
}

export function canRedoEditorHistory(history: EditorHistoryState): boolean {
  return history.future.length > 0;
}

export function isEditorHistoryClean(history: EditorHistoryState): boolean {
  return history.past.length === history.cleanIndex;
}

export function markEditorHistoryClean(history: EditorHistoryState): EditorHistoryState {
  return {
    ...history,
    cleanIndex: history.past.length,
  };
}

export function getTransactionMergeKey(transaction: EditorTransaction): string | null {
  return transaction.mergeKey;
}

export function canMergeEditorTransactions(
  previous: AppliedEditorTransaction | undefined,
  next: EditorTransaction,
): boolean {
  if (!previous) {
    return false;
  }
  const previousMergeKey = getTransactionMergeKey(previous.transaction);
  const nextMergeKey = getTransactionMergeKey(next);
  return Boolean(previousMergeKey && previousMergeKey === nextMergeKey && previous.transaction.label === next.label);
}

export function applyEditorCommands(document: EditorDocumentDTO, transaction: EditorTransaction): EditorDocumentDTO {
  const next = cloneEditorDocument(document);
  for (const command of transaction.commands) {
    command.apply(next);
  }
  return normalizeEditorDocument(next);
}

export function revertEditorCommands(document: EditorDocumentDTO, transaction: EditorTransaction): EditorDocumentDTO {
  const previous = cloneEditorDocument(document);
  for (const command of [...transaction.commands].reverse()) {
    command.revert(previous);
  }
  return normalizeEditorDocument(previous);
}

export function applyEditorTransaction(
  history: EditorHistoryState,
  transaction: EditorTransaction,
  selectionBefore: EditorSelectionDTO,
): {
  history: EditorHistoryState;
  selection: EditorSelectionDTO;
} {
  if (!history.present || !transaction.commands.length) {
    return {
      history,
      selection: applyEditorSelection(transaction.selectionAfter ?? selectionBefore),
    };
  }

  const selectionAfter = applyEditorSelection(transaction.selectionAfter ?? selectionBefore);
  const nextPresent = applyEditorCommands(history.present, transaction);
  const previousEntry = history.past[history.past.length - 1];
  const merged = canMergeEditorTransactions(previousEntry, transaction);
  const nextEntry: AppliedEditorTransaction = {
    transaction,
    selectionBefore: merged ? previousEntry.selectionBefore : applyEditorSelection(selectionBefore),
    selectionAfter,
  };

  return {
    history: {
      present: nextPresent,
      past: merged ? [...history.past.slice(0, -1), nextEntry] : [...history.past, nextEntry],
      future: [],
      cleanIndex: history.cleanIndex,
    },
    selection: selectionAfter,
  };
}

export function undoEditorHistory(history: EditorHistoryState): {
  history: EditorHistoryState;
  selection: EditorSelectionDTO | null;
} {
  const entry = history.past[history.past.length - 1];
  if (!history.present || !entry) {
    return { history, selection: null };
  }

  return {
    history: {
      present: revertEditorCommands(history.present, entry.transaction),
      past: history.past.slice(0, -1),
      future: [entry, ...history.future],
      cleanIndex: history.cleanIndex,
    },
    selection: applyEditorSelection(entry.selectionBefore),
  };
}

export function redoEditorHistory(history: EditorHistoryState): {
  history: EditorHistoryState;
  selection: EditorSelectionDTO | null;
} {
  const entry = history.future[0];
  if (!history.present || !entry) {
    return { history, selection: null };
  }

  return {
    history: {
      present: applyEditorCommands(history.present, entry.transaction),
      past: [...history.past, entry],
      future: history.future.slice(1),
      cleanIndex: history.cleanIndex,
    },
    selection: applyEditorSelection(entry.selectionAfter),
  };
}
