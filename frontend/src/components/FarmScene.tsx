import { useState } from "react";
import { Drop, Lightning, MapPin, Thermometer, Waves } from "@phosphor-icons/react";
import type { FarmWorldViewModel } from "../domain/farmWorldViewModel";
import { DevicePanel } from "./DevicePanel";
import { EmptyBlock, Panel, StatusBadge } from "./ui";

export function FarmScene({ world, available = true }: { world: FarmWorldViewModel; available?: boolean }) {
  const [selectedId, setSelectedId] = useState("AREA_A");
  const selected = world.entities.find((entity) => entity.id === selectedId) ?? world.entities[0];
  if (!available) return <Panel title="Tình trạng hiện tại" className="farm-scene-fallback"><EmptyBlock message="Bản đồ farm tạm không khả dụng. Các trạng thái vận hành vẫn hiển thị dưới dạng danh sách." /><ul>{world.entities.map((entity) => <li key={entity.id}><strong>{entity.label}</strong>: {entity.detail}</li>)}</ul></Panel>;
  return (
    <section className="farm-scene" aria-labelledby="farm-scene-title">
      <div className="farm-scene__header"><div><p className="context-label">Live farm / Area A</p><h2 id="farm-scene-title">Tình trạng hiện tại</h2></div><StatusBadge status={world.expectedActual === "KNOWN" ? "PASS" : "UNKNOWN"} label={world.expectedActual === "KNOWN" ? "Có đối chiếu kỳ vọng / thực tế" : "Chưa đủ dữ liệu đối chiếu"} /></div>
      <div className="farm-scene__canvas" aria-label="Bản đồ vận hành nông trại Area A">
        <span className="scene-land" aria-hidden="true" />
        <span role="img" className={`scene-flow ${world.hasActiveFlow ? "is-active" : ""}`} aria-label={world.hasActiveFlow ? "Đường nước có evidence flow" : "Không có evidence flow"} />
        <button type="button" className={`scene-entity scene-entity--field ${world.soilMoisture === undefined ? "is-unknown" : ""}`} aria-pressed={selectedId === "AREA_A"} onClick={() => setSelectedId("AREA_A")}><MapPin size={22} aria-hidden="true" /><span>Area A</span><small>{world.soilMoisture === undefined ? "Soil chưa có reading" : `Soil ${world.soilMoisture}%`}</small></button>
        <button type="button" className={`scene-entity scene-entity--tank ${world.tankLevel === undefined ? "is-unknown" : ""}`} aria-pressed={selectedId === "TANK_01"} onClick={() => setSelectedId("TANK_01")}><span className="scene-tank-water" style={{ height: `${world.tankLevel ?? 0}%` }} /><Drop size={20} aria-hidden="true" /><span>TANK_01</span><small>{world.tankLevel === undefined ? "Level chưa có" : `${world.tankLevel}%`}</small></button>
        <button type="button" className={`scene-entity scene-entity--pump ${world.hasActiveFlow ? "is-flowing" : ""}`} aria-pressed={selectedId === "PUMP_01"} onClick={() => setSelectedId("PUMP_01")}><Lightning size={23} aria-hidden="true" /><span>PUMP_01</span><small>{world.pumpFlow === undefined ? "Flow chưa có" : `${world.pumpFlow} L/min`}</small></button>
        {world.entities.filter((entity) => ["SOIL_01", "WEATHER_01", "SUN_01", "PH_01"].includes(entity.id)).map((entity) => <button key={entity.id} type="button" className="scene-entity scene-entity--sensor" aria-pressed={selectedId === entity.id} onClick={() => setSelectedId(entity.id)}><Thermometer size={18} aria-hidden="true" /><span>{entity.label}</span><small>{entity.freshness}</small></button>)}
      </div>
      <div className="farm-scene__comparison" aria-label="Kỳ vọng và thực tế của bơm">
        <div><span>Kỳ vọng pump flow</span><strong>{world.expectedPumpFlow === undefined ? "Chưa có trong plan" : `≥ ${world.expectedPumpFlow} L/min`}</strong></div>
        <div><span>Thực tế</span><strong>{world.pumpFlow === undefined ? "Chưa có reading" : `${world.pumpFlow} L/min`}</strong></div>
      </div>
      <aside className="farm-scene__inspector" aria-live="polite"><div><Waves size={19} aria-hidden="true" /><strong>{selected?.label}</strong></div><p>{selected?.detail}</p>{selected?.device ? <DevicePanel device={selected.device} /> : <p className="muted-copy">Area A chỉ tổng hợp từ evidence của các thiết bị; không có số liệu giả định.</p>}</aside>
    </section>
  );
}
