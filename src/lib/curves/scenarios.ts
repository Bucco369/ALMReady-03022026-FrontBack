import type { CurvePoint } from "@/lib/api";

export const CURVE_SCENARIO_IDS = [
  "base",
  "parallel-up",
  "parallel-down",
  "steepener",
  "flattener",
  "short-up",
  "short-down",
  "long-up",
  "long-down",
] as const;

export type CurveScenarioId = (typeof CURVE_SCENARIO_IDS)[number];

const R_PARALLEL = 0.02;
const R_SHORT = 0.025;
const R_LONG = 0.015;

function isRegulatoryScenarioId(value: string): value is CurveScenarioId {
  return (CURVE_SCENARIO_IDS as readonly string[]).includes(value);
}

export function applyScenarioShockRate(
  baseRate: number,
  tYears: number,
  scenarioId: string,
  customShockBps?: number,
  customShockType?: "parallel" | "long"
): number {
  if (!isRegulatoryScenarioId(scenarioId)) {
    if (customShockBps === undefined) return baseRate;
    const customShockDecimal = customShockBps / 10000;
    const customType =
      customShockType ??
      (scenarioId.startsWith("custom-long-") ? "long" : "parallel");

    if (customType === "long") {
      const longFactor = 1 - Math.exp(-tYears / 4);
      return baseRate + customShockDecimal * longFactor;
    }
    return baseRate + customShockDecimal;
  }

  if (scenarioId === "base") {
    return baseRate;
  }

  const deltaShort = R_SHORT * Math.exp(-tYears / 4);
  const deltaLong = R_LONG * (1 - Math.exp(-tYears / 4));

  switch (scenarioId) {
    case "parallel-up":
      return baseRate + R_PARALLEL;
    case "parallel-down":
      return baseRate - R_PARALLEL;
    case "short-up":
      return baseRate + deltaShort;
    case "short-down":
      return baseRate - deltaShort;
    case "long-up":
      return baseRate + deltaLong;
    case "long-down":
      return baseRate - deltaLong;
    case "flattener":
      return baseRate + (0.8 * Math.abs(deltaShort) - 0.6 * Math.abs(deltaLong));
    case "steepener":
      return baseRate + (-0.65 * Math.abs(deltaShort) + 0.9 * Math.abs(deltaLong));
    default:
      return baseRate;
  }
}

export function buildScenarioPoints(
  basePoints: CurvePoint[],
  scenarioId: string,
  customShockBps?: number,
  customShockType?: "parallel" | "long"
): CurvePoint[] {
  return basePoints.map((point) => ({
    tenor: point.tenor,
    t_years: point.t_years,
    rate: applyScenarioShockRate(
      point.rate,
      point.t_years,
      scenarioId,
      customShockBps,
      customShockType
    ),
  }));
}
