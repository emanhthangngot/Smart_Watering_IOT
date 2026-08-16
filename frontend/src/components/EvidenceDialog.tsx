import { useEffect, useRef, useState } from "react";
import { ClockCounterClockwise, X } from "@phosphor-icons/react";
import type { EvidenceNode } from "../api/types";
import type { FarmOpsApi } from "../api/client";
import { formatUnknown } from "../api/normalize";
import { formatDateTime, formatDuration } from "../lib/format";
import { Button, EmptyBlock, ErrorBlock, LoadingBlock, StatusBadge } from "./ui";

export function EvidenceDialog({
  api,
  decisionId,
  highlightedEvidenceRefs = [],
  onClose,
}: {
  api: FarmOpsApi;
  decisionId?: string;
  highlightedEvidenceRefs?: string[];
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [nodes, setNodes] = useState<EvidenceNode[]>([]);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<Error>();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (decisionId && dialog && !dialog.open) dialog.showModal();
  }, [decisionId]);

  useEffect(() => {
    if (!decisionId) return;
    const controller = new AbortController();
    setStatus("loading");
    setError(undefined);
    api.explain(decisionId, controller.signal)
      .then((data) => {
        setNodes(data);
        setStatus("success");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason : new Error("Không tải được evidence."));
        setStatus("error");
      });
    return () => controller.abort();
  }, [api, decisionId]);

  if (!decisionId) return null;

  return (
    <dialog
      ref={dialogRef}
      className="dialog evidence-dialog"
      aria-labelledby="evidence-title"
      onCancel={onClose}
      onClose={onClose}
    >
      <div className="dialog__header">
        <div>
          <h2 id="evidence-title">Giải thích decision</h2>
          <code>{decisionId}</code>
        </div>
        <button className="icon-button" aria-label="Đóng evidence" onClick={() => dialogRef.current?.close()}>
          <X size={20} aria-hidden="true" />
        </button>
      </div>
      <div className="dialog__body">
        {status === "loading" ? <LoadingBlock label="Đang truy ngược evidence" /> : null}
        {status === "error" ? <ErrorBlock error={error} /> : null}
        {status === "success" && nodes.length === 0 ? <EmptyBlock message="API không trả node evidence cho quyết định này." /> : null}
        {status === "success" && nodes.length > 0 ? (
          <ol className="evidence-lineage">
            {nodes.map((node) => (
              <li key={node.id} className={highlightedEvidenceRefs.includes(node.id) ? "evidence-lineage__item--highlighted" : undefined}>
                <div className="evidence-lineage__heading">
                  <code>{node.id}</code>
                  <StatusBadge status={node.sourceStatus ?? node.type} />
                </div>
                <strong>{node.label}</strong>
                {node.value !== undefined ? <p className="numeric">{formatUnknown(node.value)}{node.unit ? ` ${node.unit}` : ""}</p> : null}
                <dl>
                  <div><dt>Quan hệ</dt><dd>{node.relation ?? "node gốc"}</dd></div>
                  <div><dt>Event time</dt><dd>{formatDateTime(node.eventTime)}</dd></div>
                  <div>
                    <dt><ClockCounterClockwise size={15} aria-hidden="true" /> Tuổi tại lúc quyết định</dt>
                    <dd>{formatDuration(node.ageAtDecisionSeconds)}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
      <div className="dialog__footer">
        <Button variant="secondary" onClick={() => dialogRef.current?.close()}>Đóng</Button>
      </div>
    </dialog>
  );
}
