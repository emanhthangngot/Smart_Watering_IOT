import { ArrowsClockwise, Wrench } from "@phosphor-icons/react";
import type { Verification, VerificationLayer } from "../api/types";
import { formatUnknown } from "../api/normalize";
import { EmptyBlock, Panel, StatusBadge } from "./ui";

function VerificationGroup({
  title,
  description,
  layer,
  items,
}: {
  title: string;
  description: string;
  layer: VerificationLayer;
  items: Verification[];
}) {
  const Icon = layer === "ACTION" ? Wrench : ArrowsClockwise;
  return (
    <Panel title={title} description={description} className="verification-panel">
      <span className="verification-panel__icon" aria-hidden="true"><Icon size={21} /></span>
      {items.length === 0 ? <EmptyBlock message="Chưa có verification record cho lớp này." /> : (
        <div className="verification-list">
          {items.map((verification) => (
            <article key={verification.id} className="verification-record">
              <div>
                <code>{verification.id}</code>
                <StatusBadge status={verification.result} />
              </div>
              <dl>
                <div><dt>Kỳ vọng</dt><dd>{formatUnknown(verification.expected)}</dd></div>
                <div><dt>Quan sát</dt><dd>{formatUnknown(verification.observed)}</dd></div>
                {verification.window ? <div><dt>Cửa sổ</dt><dd>{verification.window}</dd></div> : null}
              </dl>
              {verification.evidenceRefs.length > 0 ? (
                <p className="record-refs">Evidence: {verification.evidenceRefs.join(", ")}</p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function VerificationPanels({ verifications }: { verifications: Verification[] }) {
  const action = verifications.filter((item) => item.layer === "ACTION");
  const outcome = verifications.filter((item) => item.layer === "OUTCOME");
  return (
    <div className="verification-grid" aria-label="Hai lớp verification">
      <VerificationGroup
        title="Action Verification"
        description="Tool/API đã tạo đúng entity và tham số chưa?"
        layer="ACTION"
        items={action}
      />
      <VerificationGroup
        title="Outcome Verification"
        description="Thực tế sau action có khớp expected outcome không?"
        layer="OUTCOME"
        items={outcome}
      />
    </div>
  );
}
