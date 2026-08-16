import { useCallback, useState, type FormEvent } from "react";
import { ArrowRight, GitBranch, LinkSimple, MagnifyingGlass } from "@phosphor-icons/react";
import { useNavigate, useParams } from "react-router-dom";
import { useOperations } from "../app/useOperations";
import { EvidenceDialog } from "../components/EvidenceDialog";
import { Button, EmptyBlock, Panel, ResourceState, StatusBadge } from "../components/ui";
import { usePollingResource } from "../hooks/usePollingResource";
import { formatDateTime, humanize } from "../lib/format";

function TraceDetail({ traceId }: { traceId: string }) {
  const { api } = useOperations();
  const loadTimeline = useCallback((signal: AbortSignal) => api.getTimeline(traceId, signal), [api, traceId]);
  const timeline = usePollingResource(loadTimeline);
  const [decisionId, setDecisionId] = useState<string>();
  return (
    <>
      <Panel title="Decision replay" description={`Trace ${traceId}`} action={<GitBranch size={22} aria-hidden="true" />}>
        <ResourceState
          status={timeline.status}
          error={timeline.error}
          hasData={Boolean(timeline.data)}
          isEmpty={timeline.status === "success" && (timeline.data?.length ?? 0) === 0}
          emptyMessage="Trace chưa có sự kiện."
          onRetry={timeline.refresh}
        >
          {timeline.data?.length ? (
            <ol className="timeline">
              {timeline.data.map((event) => (
                <li key={event.id}>
                  <time dateTime={event.timestamp}>{formatDateTime(event.timestamp)}</time>
                  <div className="timeline__record">
                    <div><StatusBadge status={event.type} label={humanize(event.type)} /><strong>{event.actor}</strong></div>
                    <h2>{event.title}</h2>
                    {event.detail ? <p>{event.detail}</p> : null}
                    <div className="timeline__links">
                      {event.decisionId ? (
                        <button onClick={() => setDecisionId(event.decisionId)}><MagnifyingGlass size={15} aria-hidden="true" /> Vì sao?</button>
                      ) : null}
                      {event.evidenceRefs.map((ref) => <code key={ref}><LinkSimple size={13} aria-hidden="true" /> {ref}</code>)}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : null}
        </ResourceState>
      </Panel>
      <EvidenceDialog api={api} decisionId={decisionId} onClose={() => setDecisionId(undefined)} />
    </>
  );
}

export function TracePage() {
  const params = useParams();
  const { farmState } = useOperations();
  const navigate = useNavigate();
  const routeTraceId = params.traceId;
  const [input, setInput] = useState(routeTraceId ?? farmState.data?.traceId ?? "");
  const activeTraceId = routeTraceId ?? farmState.data?.traceId;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (input.trim()) navigate(`/trace/${encodeURIComponent(input.trim())}`);
  };

  return (
    <div className="page-stack">
      <header className="page-heading"><div><p className="context-label">Trace & Explain</p><h1>Truy vết quyết định</h1><p>Replay proposal, challenge, approval, action, verification và re-plan theo thứ tự thời gian.</p></div></header>
      <form className="trace-search" onSubmit={submit}>
        <label className="field"><span>Trace ID</span><input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Nhập trace ID" /></label>
        <Button type="submit" disabled={!input.trim()}>Mở trace <ArrowRight size={17} aria-hidden="true" /></Button>
      </form>
      {activeTraceId ? <TraceDetail traceId={activeTraceId} /> : <EmptyBlock message="Chưa có active trace. Nhập trace ID hoặc gửi một yêu cầu mới." />}
    </div>
  );
}
