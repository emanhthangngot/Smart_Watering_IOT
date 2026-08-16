import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Bell,
  ChartLine,
  ClipboardText,
  Cpu,
  GearSix,
  GitBranch,
  Leaf,
  ListChecks,
  Moon,
  SquaresFour,
  Sun,
  X,
} from "@phosphor-icons/react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { NotificationBanner } from "../components/NotificationBanner";
import { StatusBadge } from "../components/ui";
import { useOperations } from "./useOperations";
import { usePreferences } from "./usePreferences";

function TokenDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { operatorToken, setOperatorToken } = usePreferences();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && dialog && !dialog.open) {
      dialog.showModal();
      inputRef.current?.focus();
    }
    if (!open && dialog?.open) dialog.close();
  }, [open]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setOperatorToken(String(data.get("operatorToken") ?? ""));
    dialogRef.current?.close();
  };

  return (
    <dialog ref={dialogRef} className="dialog token-dialog" aria-labelledby="token-title" onClose={onClose} onCancel={onClose}>
      <form onSubmit={submit}>
        <div className="dialog__header">
          <div><h2 id="token-title">Kết nối quyền vận hành</h2><p>Token chỉ được giữ trong sessionStorage của tab này.</p></div>
          <button type="button" className="icon-button" aria-label="Đóng cài đặt" onClick={() => dialogRef.current?.close()}><X size={20} aria-hidden="true" /></button>
        </div>
        <div className="dialog__body">
          <label className="field">
            <span>Operator token</span>
            <input ref={inputRef} name="operatorToken" type="password" defaultValue={operatorToken} autoComplete="off" placeholder="Nhập token do backend cấp" />
          </label>
          <p className="security-note">Frontend gửi token qua header <code>X-Operator-Token</code>. Không lưu token vào source hay localStorage.</p>
        </div>
        <div className="dialog__footer dialog__footer--split">
          <button type="button" className="button button--ghost" onClick={() => { setOperatorToken(""); dialogRef.current?.close(); }}>Xóa token</button>
          <button className="button button--primary" type="submit">Lưu cho session</button>
        </div>
      </form>
    </dialog>
  );
}

const navigation = [
  { to: "/", label: "Tổng quan", icon: SquaresFour, match: "overview" },
  { to: "/plan", label: "Kế hoạch", icon: ClipboardText, match: "plan" },
  { to: "/inspection-tasks", label: "Nhiệm vụ", icon: ListChecks, match: "inspection-tasks" },
  { to: "/#devices", label: "Thiết bị", icon: Cpu, match: "devices" },
  { to: "/#monitoring", label: "Giám sát", icon: ChartLine, match: "monitoring" },
  { to: "/trace", label: "Lịch sử & Trace", icon: GitBranch, match: "trace" },
] as const;

const mobileNavigation = navigation.filter((item) => ["overview", "plan", "inspection-tasks", "trace"].includes(item.match));

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme, operatorToken } = usePreferences();
  const { farmState, tasks } = useOperations();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const unreadCount = (tasks.data ?? []).filter((task) => task.status === "unread").length;
  const isActive = (match: string) => {
    if (match === "overview") return location.pathname === "/" && !location.hash;
    if (match === "plan") return location.pathname.startsWith("/plan");
    if (match === "devices") return location.pathname === "/" && location.hash === "#devices";
    if (match === "monitoring") return location.pathname === "/" && location.hash === "#monitoring";
    return location.pathname.startsWith(`/${match}`);
  };

  const navigationLinks = (items: readonly typeof navigation[number][]) => items.map(({ to, label, icon: Icon, match }) => {
    const content = <><span className="nav-icon"><Icon size={20} aria-hidden="true" />{match === "inspection-tasks" && unreadCount > 0 ? <b aria-label={`${unreadCount} nhiệm vụ chưa đọc`}>{unreadCount}</b> : null}</span><span>{label}</span></>;
    const active = isActive(match);
    // Hash links are in-page jumps, not routes. NavLink treats them as "/"
    // and would mark them active together with the overview route.
    if (match === "devices" || match === "monitoring") {
      return <Link key={to} to={to} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>{content}</Link>;
    }
    return <NavLink key={to} to={to} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>{content}</NavLink>;
  });

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="FarmOps AI, về Tổng quan">
          <span aria-hidden="true"><Leaf size={28} weight="fill" /></span>
          <span><strong>FarmOps AI</strong><small>Command Center</small></span>
        </NavLink>
        <nav className="sidebar__nav" aria-label="Điều hướng chính">{navigationLinks(navigation)}</nav>
        <div className="sidebar__footer">
          <div className="sidebar__mode"><Sun size={18} aria-hidden="true" /><span>Chế độ sáng</span></div>
          <button className={`sidebar__operator ${operatorToken ? "is-configured" : ""}`} onClick={() => setSettingsOpen(true)} aria-label="Cấu hình operator token">
            <span className="sidebar__operator-avatar" aria-hidden="true">OP</span>
            <span><strong>{operatorToken ? "Quyền vận hành" : "Chưa có quyền"}</strong><small>{operatorToken ? "Token đang dùng" : "Cần token để quyết định"}</small></span>
            <GearSix size={18} aria-hidden="true" />
          </button>
        </div>
      </aside>

      <div className="app-frame">
        <header className="topbar">
          <div className="topbar__location"><span className="topbar__eyebrow">FarmOps AI</span><strong>Command Center</strong></div>
          <div className="topbar__actions">
            <div className="api-state" title={farmState.error?.message}>
              <StatusBadge status={farmState.status === "success" ? "OK" : farmState.status === "error" ? "OFFLINE" : "UNKNOWN"} label={farmState.status === "success" ? "LIVE" : farmState.status === "error" ? "API lỗi" : "Đang nối"} />
            </div>
            <button className="icon-button" onClick={toggleTheme} aria-label={theme === "light" ? "Chuyển sang giao diện tối" : "Chuyển sang giao diện sáng"}>
              {theme === "light" ? <Moon size={20} aria-hidden="true" /> : <Sun size={20} aria-hidden="true" />}
            </button>
            <button className="topbar__alerts" onClick={() => navigate("/inspection-tasks")} aria-label={`${unreadCount} nhiệm vụ chưa đọc`}>
              <Bell size={22} aria-hidden="true" />{unreadCount > 0 ? <b>{unreadCount}</b> : null}
            </button>
          </div>
        </header>

        <NotificationBanner tasks={tasks.data ?? []} />
        <main id="main-content" tabIndex={-1}><Outlet /></main>
      </div>

      <nav className="mobile-nav" aria-label="Điều hướng di động">{navigationLinks(mobileNavigation)}</nav>
      <TokenDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
