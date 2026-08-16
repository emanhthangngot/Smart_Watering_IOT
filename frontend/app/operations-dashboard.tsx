"use client";

import { useEffect, useState } from "react";
import { activity, agentSteps, devices } from "./mock-data";

type DecisionState = "pending" | "approving" | "verified" | "rejected";

function StatusDot({ warning = false }: { warning?: boolean }) {
  return <span className={warning ? "status-dot status-warning" : "status-dot"} aria-hidden="true" />;
}

export function OperationsDashboard() {
  const [decision, setDecision] = useState<DecisionState>("pending");
  const [partialMode, setPartialMode] = useState(false);

  useEffect(() => {
    if (decision !== "approving") return;
    const timer = window.setTimeout(() => setDecision("verified"), 900);
    return () => window.clearTimeout(timer);
  }, [decision]);

  const confidence = partialMode ? 61 : 82;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">A</span>
          <div><p className="eyebrow">KHU A · ĐIỀU HÀNH NÔNG TRẠI</p><h1>AquaOps Copilot</h1></div>
        </div>
        <div className="topbar-actions">
          <button className={`mode-toggle ${partialMode ? "mode-active" : ""}`} aria-label="Bật hoặc tắt mô phỏng mất dữ liệu SOIL_01" aria-pressed={partialMode} onClick={() => setPartialMode((value) => !value)}>
            <span className="toggle-track" aria-hidden="true"><span /></span>
            Mô phỏng mất SOIL_01
          </button>
          <div className="connection-pill" role="status" aria-label="MQTT đang kết nối"><span className="live-dot" aria-hidden="true" /><span><strong>MQTT trực tuyến</strong><small>Cập nhật 4 giây trước</small></span></div>
        </div>
      </header>

      {partialMode && (
        <div className="partial-banner" role="alert">
          <span className="banner-code">PARTIAL</span>
          <div><strong>Đang vận hành với dữ liệu một phần</strong><small>SOIL_01 quá hạn 18 phút. Hệ thống không suy đoán độ ẩm đất và đã hạ độ tin cậy.</small></div>
        </div>
      )}

      <section className="mission-card" aria-labelledby="mission-title">
        <div className="mission-heading">
          <div><span className="severity">ƯU TIÊN CAO</span><p className="eyebrow">NHIỆM VỤ ĐANG CHỜ QUYẾT ĐỊNH</p><h2 id="mission-title">Xác minh phiên tưới Khu A</h2></div>
          <div className={`confidence ${partialMode ? "confidence-low" : ""}`} aria-label={`Độ tin cậy ${confidence} phần trăm`}><strong>{confidence}%</strong><span>tin cậy</span></div>
        </div>
        <p className="mission-summary">Lưu lượng cấp nước đang thấp hơn mức kỳ vọng trong khi công suất bơm vẫn ổn định. Cần kiểm tra đường tưới hoặc cảm biến trước khi thay đổi lịch vận hành.</p>
        <div className="evidence-grid" aria-label="Bằng chứng IoT">
          <article className="evidence-item"><span>PUMP_01 · LƯU LƯỢNG</span><strong>22.4 <small>L/phút</small></strong><em className="warning-text">↓ 42% so với nền 5 phút</em><small className="freshness">Dữ liệu mới · 4 giây</small></article>
          <article className="evidence-item"><span>PUMP_01 · CÔNG SUẤT</span><strong>742 <small>W</small></strong><em>Trong dải vận hành</em><small className="freshness">Dữ liệu mới · 4 giây</small></article>
          <article className={`evidence-item ${partialMode ? "evidence-stale" : ""}`}><span>{partialMode ? "SOIL_01 · ĐỘ ẨM ĐẤT" : "TANK_01 · MỰC NƯỚC"}</span><strong>{partialMode ? "—" : "63"} <small>{partialMode ? "không dùng" : "%"}</small></strong><em>{partialMode ? "Quá hạn · loại khỏi quyết định" : "Đủ cho phiên tưới"}</em><small className="freshness">{partialMode ? "Lần cuối · 18 phút trước" : "Dữ liệu mới · 7 giây"}</small></article>
        </div>
        <DecisionPanel state={decision} setState={setDecision} partialMode={partialMode} />
      </section>

      <section className="dashboard-grid">
        <div className="panel devices-panel" id="devices">
          <PanelHeader eyebrow="LIVE TELEMETRY" title="Thiết bị & độ tươi dữ liệu" meta="6 / 6 thiết bị" />
          <div className="device-grid">
            {devices.map((device) => {
              const stale = partialMode && device.id === "SOIL_01";
              return (
                <article className={`device-card ${stale ? "device-stale" : ""}`} key={device.id}>
                  <div className="device-title"><span className="device-code" aria-hidden="true">{device.code}</span><div><strong>{device.id}</strong><small>{device.label}</small></div><StatusDot warning={stale || device.tone === "warning"} /></div>
                  <p className="device-value">{stale ? "—" : device.value} <small>{stale ? "không dùng" : device.unit}</small></p>
                  <div className="mini-bars" aria-hidden="true">{[44, 58, 52, 74, 68, 83, 62, 55].map((height, index) => <i key={index} style={{ height: `${stale ? 22 : height}%` }} />)}</div>
                  <small className={stale ? "stale-label" : "freshness"}>{stale ? "STALE · 18 phút" : `Mới · ${device.age}`}</small>
                </article>
              );
            })}
          </div>
        </div>

        <div className="panel agent-panel" id="agents">
          <PanelHeader eyebrow="MULTI-AGENT TRACE" title="Chuỗi phối hợp" meta="5 agents" />
          <ol className="agent-list">
            {agentSteps.map((step, index) => (
              <li key={step.agent} className={step.status === "active" ? "agent-active" : ""}>
                <span className="agent-code">{step.code}</span>
                <div><strong>{step.agent}</strong><p>{partialMode && index === 2 ? "Đánh giá giới hạn do thiếu SOIL_01" : step.action}</p><small>{step.meta}</small></div>
                <span className="agent-state">{step.status === "active" ? "CHỜ" : "XONG"}</span>
              </li>
            ))}
          </ol>
          <div className="collaboration-note"><strong>2 agents cùng xử lý một nhiệm vụ</strong><small>Field IoT cung cấp bằng chứng → Diagnosis đánh giá → Coordinator đặt human gate.</small></div>
        </div>
      </section>

      <section className="lower-grid">
        <div className="panel timeline-panel" id="audit">
          <PanelHeader eyebrow="AUDIT LOG" title="Dòng sự kiện" meta="Theo thời gian thực" />
          <ol className="timeline-list">{activity.map((item) => <li key={item.time + item.title}><time>{item.time}</time><span /><div><strong>{item.title}</strong><small>{item.detail}</small></div></li>)}</ol>
        </div>
        <div className="panel safeguards-panel">
          <PanelHeader eyebrow="OPERATION GUARDRAILS" title="Rào chắn vận hành" meta="3 đang bật" />
          <ul className="guard-list"><li><StatusDot /><span><strong>Human approval</strong><small>Mọi thay đổi vật lý cần phê duyệt</small></span></li><li><StatusDot /><span><strong>Freshness gate</strong><small>Không dùng dữ liệu quá hạn để suy luận</small></span></li><li><StatusDot /><span><strong>API read-back</strong><small>Xác minh kết quả sau mọi tool call</small></span></li></ul>
        </div>
      </section>

      <nav className="mobile-nav" aria-label="Điều hướng chính"><a href="#mission-title" className="nav-active"><span>OP</span>Vận hành</a><a href="#devices"><span>IO</span>Thiết bị</a><a href="#agents"><span>AG</span>Agents</a><a href="#audit"><span>LG</span>Nhật ký</a></nav>
    </main>
  );
}

function PanelHeader({ eyebrow, title, meta }: { eyebrow: string; title: string; meta: string }) {
  return <header className="panel-header"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div><span>{meta}</span></header>;
}

function DecisionPanel({ state, setState, partialMode }: { state: DecisionState; setState: (state: DecisionState) => void; partialMode: boolean }) {
  return (
    <div className={`decision-panel decision-${state}`} aria-live="polite">
      {state === "pending" && <><div><p className="eyebrow">HÀNH ĐỘNG ĐỀ XUẤT</p><strong>{partialMode ? "Tạo phiếu kiểm tra đường tưới + cảm biến đất" : "Tạo phiếu kiểm tra đường tưới tại hiện trường"}</strong><small>Không tự động tắt bơm · Cần người vận hành phê duyệt</small></div><div className="decision-actions"><button className="button button-secondary" onClick={() => setState("rejected")}>Từ chối</button><button className="button button-primary" onClick={() => setState("approving")}>Phê duyệt tạo phiếu</button></div></>}
      {state === "approving" && <div className="decision-result"><span className="spinner" aria-hidden="true" /><div><strong>Đang gọi Farm Task API</strong><small>Tạo task và đọc lại trạng thái từ hệ thống đích…</small></div></div>}
      {state === "verified" && <div className="decision-result verified-result"><span className="result-icon" aria-hidden="true">✓</span><div><strong>TASK-024 đã được tạo và xác minh</strong><small>API 201 Created · Read-back VERIFIED · 08:41:19</small></div><span className="verified-badge">VERIFIED</span></div>}
      {state === "rejected" && <div className="decision-result"><span className="result-icon" aria-hidden="true">×</span><div><strong>Đã từ chối đề xuất</strong><small>Không có thay đổi nào được thực hiện.</small></div><button className="text-button" onClick={() => setState("pending")}>Hoàn tác</button></div>}
    </div>
  );
}
