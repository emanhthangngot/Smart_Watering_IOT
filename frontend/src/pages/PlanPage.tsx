import { useCallback, useState } from "react";
import { ArrowRight, Drop, LinkSimple, Scales, ShieldWarning } from "@phosphor-icons/react";
import { Link, useParams } from "react-router-dom";
import { formatUnknown } from "../api/normalize";
import { useOperations } from "../app/useOperations";
import { usePreferences } from "../app/usePreferences";
import { EvidenceDialog } from "../components/EvidenceDialog";
import { PlanApproval } from "../components/PlanApproval";
import { VerificationPanels } from "../components/VerificationPanels";
import { EmptyBlock, Panel, ResourceState, StatusBadge } from "../components/ui";
import { usePollingResource } from "../hooks/usePollingResource";
import { humanize } from "../lib/format";

function PlanDetailView({ revisionId }: { revisionId: string }) {
  const { api, farmState, refreshAll } = useOperations();
  const { operatorToken } = usePreferences();
  const loadPlan = useCallback((signal: AbortSignal) => api.getPlan(revisionId, signal), [api, revisionId]);
  const resource = usePollingResource(loadPlan);
  const [evidenceDecisionId, setEvidenceDecisionId] = useState<string>();
  const [highlightedEvidenceRefs, setHighlightedEvidenceRefs] = useState<string[]>([]);
  const [evidenceNotice, setEvidenceNotice] = useState<string>();
  const plan = resource.data;

  if (!plan) {
    return <ResourceState status={resource.status} error={resource.error} hasData={false} onRetry={resource.refresh} />;
  }

  const openEvidence = (evidenceRef: string) => {
    if (!plan.decisionId) {
      setEvidenceNotice(`Evidence ${evidenceRef} không phải decision ID. Backend chưa cung cấp decisionId để gọi /explain.`);
      return;
    }
    setEvidenceNotice(undefined);
    setHighlightedEvidenceRefs([evidenceRef]);
    setEvidenceDecisionId(plan.decisionId);
  };
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <p className="context-label">Plan Detail</p>
          <h1>{plan.planRevisionId || revisionId}</h1>
          <p>Revision bất biến trong lineage <code>{plan.planLineageId || "chưa có"}</code>.</p>
        </div>
        <div className="page-heading__status">
          <StatusBadge status={plan.status} />
          {plan.version !== undefined ? <span>Version {plan.version}</span> : null}
        </div>
      </header>

      <ResourceState status={resource.status} error={resource.error} hasData onRetry={resource.refresh}>
        <div className="plan-summary-grid">
          <Panel title="Mục tiêu và confidence" className="plan-goal">
            <dl className="record-grid">
              {Object.entries(plan.goal).map(([key, value]) => (
                <div key={key}><dt>{humanize(key)}</dt><dd>{formatUnknown(value)}</dd></div>
              ))}
              <div><dt>DCS</dt><dd className="numeric">{plan.confidence.dcs === undefined ? "Chưa có" : `${(plan.confidence.dcs <= 1 ? plan.confidence.dcs * 100 : plan.confidence.dcs).toFixed(1)}%`}</dd></div>
              <div><dt>Autonomy tier</dt><dd><StatusBadge status={plan.confidence.tier} /></dd></div>
              <div><dt>World State nguồn</dt><dd className="numeric">#{plan.createdFromStateVersion ?? "N/A"}</dd></div>
            </dl>
          </Panel>
          <Panel title="Ngân sách nước" description="Chỉ dùng phần trăm tank và phút bơm khi chưa có dung tích." className="water-budget">
            <span className="water-budget__icon" aria-hidden="true"><Drop size={25} weight="fill" /></span>
            {Object.keys(plan.waterBudget).length > 0 ? (
              <dl className="record-grid">
                {Object.entries(plan.waterBudget).map(([key, value]) => (
                  <div key={key}><dt>{humanize(key)}</dt><dd className="numeric">{formatUnknown(value)}</dd></div>
                ))}
              </dl>
            ) : <EmptyBlock message="API chưa trả water budget." />}
          </Panel>
        </div>

        <Panel title="Evidence và ràng buộc" description="Chọn evidence để truy ngược lý do quyết định.">
          <div className="evidence-chips">
            {plan.evidenceRefs.length > 0 ? plan.evidenceRefs.map((ref) => (
              <button key={ref} onClick={() => openEvidence(ref)}>
                <LinkSimple size={15} aria-hidden="true" /> <code>{ref}</code>
              </button>
            )) : <span>Chưa có evidence reference.</span>}
          </div>
          {evidenceNotice ? <p className="approval-hint" role="status">{evidenceNotice}</p> : null}
          {plan.constraints.length > 0 ? (
            <ul className="constraint-list">{plan.constraints.map((constraint) => <li key={constraint}><Scales size={17} aria-hidden="true" /> {constraint}</li>)}</ul>
          ) : null}
        </Panel>

        <section aria-labelledby="assumptions-title">
          <div className="section-heading"><div><h2 id="assumptions-title">Plan assumptions</h2><p>Evidence mới có thể làm assumption mất hiệu lực và kích hoạt re-plan.</p></div></div>
          {plan.assumptions.length === 0 ? <EmptyBlock message="Plan chưa có assumption record." /> : (
            <div className="assumption-grid">
              {plan.assumptions.map((assumption) => (
                <Panel key={assumption.assumptionId} as="article" className={`assumption assumption--${assumption.status.toLowerCase()}`}>
                  <div className="record-title">
                    <code>{assumption.assumptionId}</code>
                    <StatusBadge status={assumption.status} />
                  </div>
                  <h3>{assumption.predicate}</h3>
                  {assumption.observationWindow ? <p>Cửa sổ: {assumption.observationWindow}</p> : null}
                  {assumption.invalidatedReason ? <p className="invalid-reason"><ShieldWarning size={17} aria-hidden="true" /> {assumption.invalidatedReason}</p> : null}
                  <div className="evidence-chips evidence-chips--compact">
                    {assumption.evidenceRefs.map((ref) => <button key={ref} onClick={() => openEvidence(ref)}><LinkSimple size={14} aria-hidden="true" /> {ref}</button>)}
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </section>

        <Panel title="Challenge và objection" description="Blocking challenge phải được giải quyết trước APPROVED.">
          {plan.challenges.length === 0 ? <EmptyBlock message="Không có challenge trên revision này." /> : (
            <div className="challenge-list">
              {plan.challenges.map((challenge) => (
                <article key={challenge.challengeId}>
                  <div className="record-title"><strong>{challenge.agent}</strong><StatusBadge status={challenge.blocking ? "CHALLENGED" : challenge.status} label={challenge.blocking ? "Blocking" : challenge.status} /></div>
                  <p>{challenge.reason}</p>
                  {challenge.requestedEvidence ? <span>Yêu cầu evidence: {challenge.requestedEvidence}</span> : null}
                  {challenge.revision ? <span>Revision đề nghị: {challenge.revision}</span> : null}
                </article>
              ))}
            </div>
          )}
        </Panel>

        <div className="plan-record-grid">
          <Panel title="Actions">
            {plan.actions.length === 0 ? <EmptyBlock message="Revision chưa có action." /> : (
              <div className="action-list">
                {plan.actions.map((action) => (
                  <article key={action.actionId}>
                    <div className="record-title"><code>{action.actionId}</code>{action.status ? <StatusBadge status={action.status} /> : null}</div>
                    <strong>{humanize(action.type)}</strong>
                    <pre>{formatUnknown(action.parameters)}</pre>
                  </article>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Expected outcomes">
            {plan.expectedOutcomes.length === 0 ? <EmptyBlock message="Revision chưa có expected outcome." /> : (
              <div className="outcome-list">
                {plan.expectedOutcomes.map((outcome) => (
                  <article key={`${outcome.metric}-${outcome.predicate}`}>
                    <strong>{humanize(outcome.metric)}</strong>
                    <p>{outcome.predicate}</p>
                    <dl>
                      <div><dt>Threshold</dt><dd>{outcome.threshold ?? "N/A"}</dd></div>
                      <div><dt>Tolerance</dt><dd>{outcome.tolerance ?? "N/A"}</dd></div>
                      <div><dt>Cửa sổ</dt><dd>{outcome.observationWindow ?? "N/A"}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <PlanApproval
          api={api}
          plan={plan}
          hasOperatorToken={Boolean(operatorToken)}
          onSuccess={() => {
            resource.refresh();
            refreshAll();
          }}
        />
        <VerificationPanels verifications={plan.verifications} />
        {farmState.data?.traceId ? (
          <Link className="trace-link" to={`/trace/${encodeURIComponent(farmState.data.traceId)}`}>
            Xem decision trace <ArrowRight size={17} aria-hidden="true" />
          </Link>
        ) : null}
      </ResourceState>

      <EvidenceDialog api={api} decisionId={evidenceDecisionId} highlightedEvidenceRefs={highlightedEvidenceRefs} onClose={() => { setEvidenceDecisionId(undefined); setHighlightedEvidenceRefs([]); }} />
    </div>
  );
}

export function PlanPage() {
  const { revisionId } = useParams();
  const { farmState } = useOperations();
  const resolvedRevisionId = revisionId ?? farmState.data?.activePlan?.planRevisionId;
  if (!resolvedRevisionId) {
    return (
      <div className="page-stack">
        <header className="page-heading"><div><p className="context-label">Plan Detail</p><h1>Chưa có kế hoạch hoạt động</h1><p>Gửi yêu cầu từ Tổng quan để bắt đầu vòng proposal và challenge.</p></div></header>
        <EmptyBlock message="World State chưa tham chiếu active plan revision." />
        <Link className="button button--primary self-start" to="/">Về Tổng quan <ArrowRight size={17} aria-hidden="true" /></Link>
      </div>
    );
  }
  return <PlanDetailView revisionId={resolvedRevisionId} />;
}
