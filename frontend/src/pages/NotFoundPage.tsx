import { ArrowLeft } from "@phosphor-icons/react";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <span>404</span>
      <h1>Không tìm thấy màn hình</h1>
      <p>Đường dẫn này không thuộc bảng điều hành FarmOps.</p>
      <Link className="button button--primary" to="/"><ArrowLeft size={17} aria-hidden="true" /> Về Tổng quan</Link>
    </div>
  );
}
