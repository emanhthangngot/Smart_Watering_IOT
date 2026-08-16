import type { DeviceSnapshot, FarmState, PlanDetail } from "../api/types";

export interface FarmWorldEntity {
  id: "AREA_A" | "SOIL_01" | "WEATHER_01" | "PUMP_01" | "TANK_01" | "SUN_01" | "PH_01";
  label: string;
  device?: DeviceSnapshot;
  detail: string;
  value?: number;
  unit?: string;
  freshness: string;
}

export interface FarmWorldViewModel {
  entities: FarmWorldEntity[];
  tankLevel?: number;
  pumpFlow?: number;
  expectedPumpFlow?: number;
  soilMoisture?: number;
  hasActiveFlow: boolean;
  expectedActual: "KNOWN" | "UNKNOWN";
}

function device(state: FarmState, code: string): DeviceSnapshot | undefined {
  return state.devices.find((item) => item.deviceCode.toUpperCase() === code);
}
function metric(snapshot: DeviceSnapshot | undefined, names: string[]): { value?: number; unit?: string } {
  const found = snapshot?.metrics.find((item) => names.includes(item.name.toLowerCase()));
  return { value: typeof found?.value === "number" ? found.value : undefined, unit: found?.unit };
}

export function createFarmWorldViewModel(state: FarmState, plan?: PlanDetail): FarmWorldViewModel {
  const soil = device(state, "SOIL_01"); const weather = device(state, "WEATHER_01"); const pump = device(state, "PUMP_01"); const tank = device(state, "TANK_01"); const sun = device(state, "SUN_01"); const ph = device(state, "PH_01");
  const soilMoisture = metric(soil, ["moisture", "soil_moisture"]); const tankLevel = metric(tank, ["level", "tank_level"]); const pumpFlow = metric(pump, ["flow_rate", "flow"]);
  const expectedPumpFlow = plan?.expectedOutcomes.find((outcome) => /flow/i.test(outcome.metric))?.threshold;
  const outcomeKnown = expectedPumpFlow !== undefined && pumpFlow.value !== undefined;
  const entity = (id: FarmWorldEntity["id"], label: string, snapshot?: DeviceSnapshot, observation?: { value?: number; unit?: string }): FarmWorldEntity => ({
    id, label, device: snapshot, value: observation?.value, unit: observation?.unit,
    freshness: snapshot?.freshness ?? "UNKNOWN",
    detail: observation?.value === undefined ? "Chưa có evidence đo được" : `${observation.value}${observation.unit ? ` ${observation.unit}` : ""}`,
  });
  return {
    entities: [entity("AREA_A", "Area A"), entity("SOIL_01", "SOIL_01", soil, soilMoisture), entity("WEATHER_01", "WEATHER_01", weather), entity("PUMP_01", "PUMP_01", pump, pumpFlow), entity("TANK_01", "TANK_01", tank, tankLevel), entity("SUN_01", "SUN_01", sun), entity("PH_01", "PH_01", ph, metric(ph, ["ph"]))],
    tankLevel: tankLevel.unit === "%" && tankLevel.value !== undefined && tankLevel.value >= 0 && tankLevel.value <= 100 ? tankLevel.value : undefined,
    pumpFlow: pumpFlow.value,
    expectedPumpFlow,
    soilMoisture: soilMoisture.unit === "%" && soilMoisture.value !== undefined && soilMoisture.value >= 0 && soilMoisture.value <= 100 ? soilMoisture.value : undefined,
    hasActiveFlow: Boolean(pumpFlow.value && pumpFlow.value > 0), expectedActual: outcomeKnown ? "KNOWN" : "UNKNOWN",
  };
}
