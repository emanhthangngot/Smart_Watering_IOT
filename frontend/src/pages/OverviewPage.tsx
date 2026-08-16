import { useCallback, useState, type CSSProperties, type FormEvent } from "react";
import { ArrowRight, CheckCircle, ClipboardText, CloudWarning, Database, Drop, GitBranch, ListChecks, Path, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import type { FarmRequestResult, FarmState, InspectionTask, PlanDetail, TimelineEvent, TrustVerdict } from "../api/types";
import { formatUnknown } from "../api/normalize";
import { useOperations } from "../app/useOperations";
import { usePreferences } from "../app/usePreferences";
import { FarmScene } from "../components/FarmScene";
import { Button, EmptyBlock, Panel, ResourceState, StatusBadge } from "../components/ui";
import { VerificationPanels } from "../components/VerificationPanels";
import { createFarmWorldViewModel } from "../domain/farmWorldViewModel";
import { usePollingResource } from "../hooks/usePollingResource";
import { formatDateTime, formatNumber, humanize } from "../lib/format";

const priorities = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 } as const;

function metricText(device: FarmState["devices"][number] | undefined, names: string[]) {
  const reading = device?.metrics.find((item) => names.includes(item.name.toLowerCase()));
  if (!reading || reading.value === undefined || reading.value === null) return undefined;
  const value = typeof reading.value === "number" ? formatNumber(reading.value) : String(reading.value);
  return value + (reading.unit ? " " + reading.unit : "");
}

function averageDcs(state: FarmState, trust: TrustVerdict[]) {
  const values = [...trust.map((item) => item.dcs), ...state.devices.map((item) => item.dcs)].filter((value): value is number => value !== undefined);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined;
}

function AttentionPanel({ state, plan }: { state: FarmState; plan?: PlanDetail }) {
  const pump = state.devices.find((device) => device.deviceCode.toUpperCase() === "PUMP_01");
  const actual = metricText(pump, ["flow_rate", "flow"]);
  const target = plan?.expectedOutcomes.find((outcome) => /flow/i.test(outcome.metric))?.threshold;
  const invalid = plan?.assumptions.find((assumption) => assumption.status === "INVALIDATED");
  const failed = plan?.verifications.find((item) => item.layer === "OUTCOME" && item.result === "FAIL");
  const anomaly = state.anomalies[0];
  const hasConcern = Boolean(invalid || failed || anomaly);
  const title = failed ? "Kết quả thực tế không đạt kỳ vọng" : invalid ? "Giả định kế hoạch đã mất hiệu lực" : anomaly ? "Có bất thường cần xử lý" : "Chưa có cảnh báo từ hệ thống";
  const reason = failed ? "Outcome Verification: " + formatUnknown(failed.observed) + " so với " + formatUnknown(failed.expected) + "." : invalid?.invalidatedReason ?? anomaly;
  return <Panel className={"attention-panel " + (hasConcern ? "attention-panel--active" : "")} as="article">
    <div className="attention-panel__heading"><div><span className="section-kicker">Cần chú ý ngay</span><h2>{title}</h2></div><WarningCircle size={28} weight="fill" aria-hidden="true" /></div>
    <p className={reason ? "" : "muted-copy"}>{reason ?? "Telemetry và plan hiện chưa báo điều kiện cần can thiệp."}</p>
    {(actual || target !== undefined) ? <dl className="attention-panel__metrics"><div><dt>Thực tế {pump?.deviceCode ?? ""}</dt><dd>{actual ?? "Chưa có reading"}</dd></div><div><dt>Kỳ vọng plan</dt><dd>{target === undefined ? "Chưa có target" : "≥ " + target + " L/min"}</dd></div></dl> : null}
    {invalid ? <p className="attention-panel__assumption">Giả định ảnh hưởng: <code>{invalid.assumptionId}</code></p> : null}
    {plan ? <Link className="button button--danger attention-panel__action" to={"/plans/" + encodeURIComponent(plan.planRevisionId)}>Xem chi tiết & xử lý <ArrowRight size={18} aria-hidden="true" /></Link> : null}
  </Panel>;
}

function ActivePlanPanel({ plan, revisionId, loading }: { plan?: PlanDetail; revisionId?: string; loading: boolean }) {
  if (!revisionId) return <Panel className="active-plan-card" as="article"><span className="section-kicker">Kế hoạch đang hoạt động</span><h2>Chưa có kế hoạch</h2><p className="muted-copy">Gửi yêu cầu để Coordinator bắt đầu workflow có kiểm chứng.</p></Panel>;
  if (!plan) return <Panel className="active-plan-card" as="article"><span className="section-kicker">Kế hoạch đang hoạt động</span><h2>{revisionId}</h2><p className="muted-copy">{loading ? "Đang tải revision từ backend." : "Không lấy được chi tiết revision."}</p><Link className="trace-link" to={"/plans/" + encodeURIComponent(revisionId)}>Mở chi tiết plan <ArrowRight size={17} aria-hidden="true" /></Link></Panel>;
  const target = plan.expectedOutcomes.find((outcome) => /flow/i.test(outcome.metric))?.threshold;
  const duration = plan.waterBudget.plannedPumpMinutes;
  const goal = Object.entries(plan.goal).map(([key, value]) => humanize(key) + ": " + formatUnknown(value)).join(" · ");
  return <Panel className="active-plan-card" as="article">
    <div className="active-plan-card__heading"><span className="section-kicker">Kế hoạch đang hoạt động</span><StatusBadge status={plan.status} label={plan.status === "PROPOSED" ? "Chờ phê duyệt" : humanize(plan.status)} /></div>
    <h2>{plan.planRevisionId}</h2><p>{goal || "Backend chưa có mô tả mục tiêu."}</p>
    <dl className="active-plan-card__details"><div><dt>Revision</dt><dd>V{plan.version ?? "?"}</dd></div><div><dt>Thời lượng</dt><dd>{typeof duration === "number" ? duration + " phút" : "Chưa có"}</dd></div><div><dt>Target flow</dt><dd>{target === undefined ? "Chưa có" : "≥ " + target + " L/min"}</dd></div><div><dt>DCS</dt><dd>{plan.confidence.dcs === undefined ? "Chưa có" : formatNumber(plan.confidence.dcs)}</dd></div></dl>
    <Link className="button button--primary active-plan-card__action" to={"/plans/" + encodeURIComponent(plan.planRevisionId)}>Xem kế hoạch & phê duyệt <ArrowRight size={18} aria-hidden="true" /></Link>
  </Panel>;
}

function DataHealthPanel({ state }: { state: FarmState }) {
  const count = (status: string) => state.devices.filter((device) => device.freshness === status).length;
  const reason = state.evidenceHealth.state === "UNKNOWN" ? "Chưa có đánh giá evidence của Coordinator." : state.evidenceHealth.reasons[0] ?? "Evidence " + state.evidenceHealth.state + ".";
  return <Panel className="data-health-card" as="article"><div className="panel__header"><div><span className="section-kicker">Sức khỏe dữ liệu</span><h2>Evidence hiện trường</h2></div><Database size={22} aria-hidden="true" /></div><div className="data-health-card__body"><div className="health-ring" aria-hidden="true"><strong>{state.devices.length}</strong><span>thiết bị</span></div><dl><div><dt><i className="status-dot status-dot--fresh" />Fresh</dt><dd>{count("FRESH")}</dd></div><div><dt><i className="status-dot status-dot--stale" />Stale</dt><dd>{count("STALE")}</dd></div><div><dt><i className="status-dot status-dot--offline" />Offline</dt><dd>{count("OFFLINE") + count("MISSING")}</dd></div></dl></div><p className="data-health-card__note">{reason}</p></Panel>;
}

function TrustPanel({ state, trust, plan }: { state: FarmState; trust: TrustVerdict[]; plan?: PlanDetail }) {
  const score = plan?.confidence.dcs ?? averageDcs(state, trust);
  const tier = plan?.confidence.tier ?? "UNKNOWN";
  const style = score === undefined ? undefined : { "--dcs-progress": String(Math.max(0, Math.min(100, score <= 1 ? score * 100 : score))) + "%" } as CSSProperties;
  const autonomy = tier === "PROPOSE" ? "Hành động quan trọng cần phê duyệt." : tier === "INVESTIGATE" ? "Cần thêm evidence hoặc xác minh thủ công." : tier === "AUTO" ? "Backend cho phép tự động theo policy." : "Backend chưa cung cấp autonomy tier.";
  return <Panel className="trust-card" as="article"><div><span className="section-kicker">Độ tin cậy (DCS)</span><h2>Đủ cơ sở để hành động?</h2></div><div className="trust-card__score"><div className="dcs-dial" style={style}><strong>{score === undefined ? "—" : formatNumber(score)}</strong><span>DCS</span></div><div><StatusBadge status={tier} /><p>{plan ? "Nguồn: " + plan.planRevisionId : "Chưa có confidence cho active plan."}</p></div></div><div className="trust-card__autonomy"><span>Mức tự chủ</span><StatusBadge status={tier} /><p>{autonomy}</p></div></Panel>;
}

function PriorityTask({ task }: { task?: InspectionTask }) {
  if (!task) return <Panel className="priority-task-card" as="article"><span className="section-kicker">Nhiệm vụ ưu tiên</span><h2>Không có nhiệm vụ mở</h2><p className="muted-copy">Hệ thống chưa yêu cầu kiểm tra hiện trường.</p></Panel>;
  return <Panel className="priority-task-card" as="article"><div className="priority-task-card__heading"><span className="section-kicker">Nhiệm vụ ưu tiên</span><StatusBadge status={task.priority} /></div><code>{task.id}</code><h2>{task.title}</h2><p>{task.deviceCode ? task.deviceCode + " · " : ""}{task.reason}</p><span className="priority-task-card__time">Tạo lúc {formatDateTime(task.createdAt)}</span><Link className="button button--secondary" to="/inspection-tasks"><ListChecks size={18} aria-hidden="true" /> Xem nhiệm vụ</Link></Panel>;
}

function AgentActivity({ events, traceId, loading }: { events: TimelineEvent[]; traceId?: string; loading: boolean }) {
  return <Panel className="agent-activity" as="article"><div className="panel__header"><div><span className="section-kicker">Hoạt động của Agent</span><h2>Phối hợp và quyết định</h2></div><GitBranch size={22} aria-hidden="true" /></div>{events.length ? <ol className="agent-activity__track">{events.slice(-4).map((event) => <li key={event.id}><span className={"agent-activity__icon agent-activity__icon--" + event.type.toLowerCase()}><Path size={17} aria-hidden="true" /></span><div><strong>{humanize(event.type)}</strong><span>{event.actor}</span><small>{formatDateTime(event.timestamp)}</small></div><p>{event.title}</p></li>)}</ol> : <EmptyBlock message={loading ? "Đang tải trace hoạt động." : "Trace chưa có sự kiện để hiển thị."} />}{traceId ? <Link className="trace-link" to={"/trace/" + encodeURIComponent(traceId)}>Xem lịch sử đề xuất <ArrowRight size={17} aria-hidden="true" /></Link> : null}</Panel>;
}

function Assumptions({ plan }: { plan?: PlanDetail }) {
  if (!plan) return null;
  return <Panel className="assumptions-preview" as="article"><div className="panel__header"><div><span className="section-kicker">Giả định quan trọng</span><h2>Điều kiện giữ plan an toàn</h2></div><Link className="trace-link" to={"/plans/" + encodeURIComponent(plan.planRevisionId)}>Evidence <ArrowRight size={16} aria-hidden="true" /></Link></div>{plan.assumptions.length ? <ul>{plan.assumptions.slice(0, 4).map((assumption) => <li key={assumption.assumptionId}><StatusBadge status={assumption.status} /><div><code>{assumption.assumptionId}</code><span>{assumption.predicate}</span>{assumption.invalidatedReason ? <small>{assumption.invalidatedReason}</small> : null}</div></li>)}</ul> : <EmptyBlock message="Backend chưa có assumption cho revision này." />}</Panel>;
}

function RequestPlan({ operatorToken, requestText, setRequestText, intent, setIntent, scope, setScope, requestStatus, requestError, requestResult, onSubmit }: { operatorToken: string; requestText: string; setRequestText: (value: string) => void; intent: string; setIntent: (value: string) => void; scope: string; setScope: (value: string) => void; requestStatus: "idle" | "loading" | "error" | "success"; requestError?: string; requestResult?: FarmRequestResult; onSubmit: (event: FormEvent) => void }) {
  const navigate = useNavigate();
  return <section className="request-card" aria-labelledby="request-title"><div className="request-card__intro"><span className="request-card__icon" aria-hidden="true"><ClipboardText size={25} /></span><div><span className="section-kicker">Bắt đầu workflow</span><h2 id="request-title">Tạo yêu cầu vận hành</h2><p>Coordinator sẽ thu evidence, tiếp nhận challenge và tạo revision để quản lý phê duyệt.</p></div></div><form className="request-form" onSubmit={onSubmit}><div className="form-row"><label className="field"><span>Ý định</span><select value={intent} onChange={(event) => setIntent(event.target.value)}><option value="IRRIGATION">Lập kế hoạch tưới</option><option value="INSPECTION">Yêu cầu kiểm tra</option><option value="DIAGNOSIS">Chẩn đoán bất thường</option></select></label><label className="field"><span>Phạm vi</span><select value={scope} onChange={(event) => setScope(event.target.value)}><option value="AREA_A">Khu A</option><option value="FARM">Toàn nông trại</option><option value="PUMP_01">PUMP_01</option></select></label></div><label className="field"><span>Nội dung yêu cầu</span><textarea value={requestText} onChange={(event) => setRequestText(event.target.value)} placeholder="Nêu mục tiêu, phạm vi và điều kiện an toàn cần giữ." rows={3} maxLength={800} required /></label>{!operatorToken ? <p className="form-hint">Cần operator token trong Cài đặt để gửi yêu cầu.</p> : null}{requestStatus === "error" ? <p className="form-error" role="alert">{requestError}</p> : null}{requestStatus === "success" && requestResult ? <div className="request-success" role="status"><span><CheckCircle size={19} aria-hidden="true" /> Workflow đã bắt đầu: <code>{requestResult.planLineageId || "đang tạo"}</code></span>{requestResult.traceId ? <Button type="button" variant="secondary" onClick={() => navigate("/trace/" + encodeURIComponent(requestResult.traceId))}>Xem trace <ArrowRight size={17} aria-hidden="true" /></Button> : null}</div> : null}<Button type="submit" busy={requestStatus === "loading"} disabled={!operatorToken || !requestText.trim()}>Gửi yêu cầu cho Coordinator <ArrowRight size={18} aria-hidden="true" /></Button></form></section>;
}

function CommandCenter({ state, trust, tasks }: { state: FarmState; trust: TrustVerdict[]; tasks: InspectionTask[] }) {
  const { api } = useOperations();
  const revisionId = state.activePlan?.planRevisionId;
  const loadPlan = useCallback((signal: AbortSignal) => revisionId ? api.getPlan(revisionId, signal) : Promise.resolve(undefined), [api, revisionId]);
  const planResource = usePollingResource<PlanDetail | undefined>(loadPlan);
  const loadTimeline = useCallback((signal: AbortSignal) => state.traceId ? api.getTimeline(state.traceId, signal) : Promise.resolve([]), [api, state.traceId]);
  const timelineResource = usePollingResource<TimelineEvent[]>(loadTimeline);
  const plan = planResource.data;
  const task = tasks.filter((item) => item.status !== "resolved").sort((a, b) => priorities[b.priority] - priorities[a.priority])[0];
  return <><section className="command-overview-grid" aria-label="Farm command center"><FarmScene world={createFarmWorldViewModel(state, plan)} /><AttentionPanel state={state} plan={plan} /><ActivePlanPanel plan={plan} revisionId={revisionId} loading={planResource.status === "loading" || planResource.status === "idle"} /></section><section className="command-secondary-grid"><DataHealthPanel state={state} /><TrustPanel state={state} trust={trust} plan={plan} /><PriorityTask task={task} /><AgentActivity events={timelineResource.data ?? []} traceId={state.traceId} loading={timelineResource.status === "loading" || timelineResource.status === "idle"} /></section><Assumptions plan={plan} />{plan ? <section className="command-verification" aria-labelledby="verification-title"><div className="section-heading"><div><span className="section-kicker">Xác minh</span><h2 id="verification-title">Action và Outcome là hai lớp riêng</h2><p>Tool/API có thể thành công trong khi kết quả thực tế vẫn không đạt kỳ vọng.</p></div></div><VerificationPanels verifications={plan.verifications} /></section> : null}</>;
}

export function OverviewPage() {
  const { api, farmState, trust, tasks, refreshAll } = useOperations();
  const { operatorToken } = usePreferences();
  const [intent, setIntent] = useState("IRRIGATION");
  const [scope, setScope] = useState("AREA_A");
  const [requestText, setRequestText] = useState("");
  const [requestStatus, setRequestStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [requestError, setRequestError] = useState<string>();
  const [requestResult, setRequestResult] = useState<FarmRequestResult>();
  const submitRequest = async (event: FormEvent) => {
    event.preventDefault();
    if (!requestText.trim()) return;
    setRequestStatus("loading"); setRequestError(undefined);
    try { const result = await api.requestPlan({ intent, scope, text: requestText.trim() }); setRequestResult(result); setRequestStatus("success"); refreshAll(); }
    catch (error) { setRequestStatus("error"); setRequestError(error instanceof Error ? error.message : "Không gửi được yêu cầu."); }
  };
  const updateText = farmState.data?.updatedAt ? "Cập nhật: " + formatDateTime(farmState.data.updatedAt) : "Đang chờ World State từ FarmOps API.";
  return <div className="page-stack overview-page"><header className="overview-header"><div><h1>Tổng quan trang trại <StatusBadge status="OK" label="LIVE" /></h1><p>{updateText}<span aria-hidden="true"> · </span>Tự động làm mới 5 phút</p></div><div className="overview-header__facts"><div><CloudWarning size={20} aria-hidden="true" /><span>Evidence</span><strong>{farmState.data?.evidenceHealth.state ?? "UNKNOWN"}</strong></div><div><Drop size={20} aria-hidden="true" /><span>Area</span><strong>{scope.replace("_", " ")}</strong></div><div><ShieldCheck size={20} aria-hidden="true" /><span>Mode</span><strong>{farmState.data?.partialMode ? "PARTIAL" : "NORMAL"}</strong></div></div></header><ResourceState status={farmState.status} error={farmState.error} hasData={Boolean(farmState.data)} onRetry={farmState.refresh}>{farmState.data ? <CommandCenter state={farmState.data} trust={trust.data ?? []} tasks={tasks.data ?? []} /> : null}</ResourceState><RequestPlan operatorToken={operatorToken} requestText={requestText} setRequestText={setRequestText} intent={intent} setIntent={setIntent} scope={scope} setScope={setScope} requestStatus={requestStatus} requestError={requestError} requestResult={requestResult} onSubmit={(event) => void submitRequest(event)} /></div>;
}
