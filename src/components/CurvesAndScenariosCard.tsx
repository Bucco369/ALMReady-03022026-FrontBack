/**
 * CurvesAndScenariosCard.tsx – Upload, manage, and visualize yield curves + IRRBB scenarios.
 *
 * === ROLE IN THE SYSTEM ===
 * The top-right quadrant of the dashboard. Two main responsibilities:
 *
 * 1. CURVES MANAGEMENT:
 *    - Upload Excel files containing yield-curve data (one curve per row).
 *    - Files are sent to POST /api/sessions/{id}/curves/upload (backend parses
 *      tenor columns like ON, 1M, 3M… 50Y and returns CurvesSummaryResponse).
 *    - Users select which curves to include in the calculation (checkboxes).
 *    - Curve points are lazy-loaded via GET /api/sessions/{id}/curves/{curveId}/points.
 *    - A "Details" dialog shows an interactive LineChart with all selected curves
 *      overlaid, plus a maturity-range slider.
 *
 * 2. SCENARIOS MANAGEMENT:
 *    - Lists the 6 standard IRRBB regulatory scenarios with shock magnitudes in bps.
 *    - Users can enable/disable scenarios and add custom ones (parallel or long-end).
 *    - In "Scenarios" chart mode, plots base curve + shocked curves via
 *      buildScenarioPoints() from curves/scenarios.ts.
 *
 * === CURRENT LIMITATIONS ===
 * - Curves are uploaded and visualized but NOT yet consumed by the local
 *   calculationEngine.ts (which uses a flat 2% base rate).
 * - Phase 1: Selected curves will be passed to POST /api/sessions/{id}/calculate
 *   so the backend engine applies proper curve-based discounting.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  TrendingUp,
  Eye,
  CheckCircle2,
  CheckSquare,
  Plus,
  X,
  Upload,
  RotateCcw,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Slider } from '@/components/ui/slider';
import type { Scenario } from '@/types/financial';
import {
  deleteCurves,
  getCurvePoints,
  getCurvesSummary,
  uploadCurvesExcel,
  type CurvePoint,
  type CurvesSummaryResponse,
} from '@/lib/api';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { buildScenarioPoints } from '@/lib/curves/scenarios';
import { getCurveDisplayLabel, getCurveTooltipLabel } from '@/lib/curves/labels';
import { getTenorCalendarDateLabel } from '@/lib/calendarLabels';
import { toast } from 'sonner';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

type ChartMode = 'curves' | 'scenarios';

type ChartSeries = {
  key: string;
  label: string;
  color: string;
  strokeWidth: number;
  dash?: string;
};

type ChartRow = {
  t_years: number;
  tenor: string;
  [key: string]: string | number;
};

type AxisTickProps = {
  x: number;
  y: number;
  payload: { value: number | string };
};

type ChartTooltipEntry = {
  value?: number | string;
  dataKey?: string;
  color?: string;
  name?: string;
};

type ChartTooltipProps = {
  active?: boolean;
  payload?: ChartTooltipEntry[];
  label?: number | string;
};

const DEFAULT_CHART_MATURITY_YEARS = 25;
const MIN_CHART_MATURITY_YEARS = 0.5;
const MIN_Y_AXIS_PADDING_PERCENT = 0.05; // 5bp
const MIN_Y_AXIS_SPAN_PERCENT = 0.25; // 25bp

const CURVE_COLOR_PALETTE = [
  'hsl(215, 50%, 45%)',
  'hsl(152, 45%, 42%)',
  'hsl(280, 45%, 50%)',
  'hsl(38, 70%, 50%)',
  'hsl(340, 50%, 50%)',
  'hsl(180, 45%, 42%)',
  'hsl(25, 80%, 50%)',
  'hsl(260, 55%, 48%)',
];

const SCENARIO_COLORS: Record<string, string> = {
  'parallel-up': 'hsl(0, 55%, 50%)',
  'parallel-down': 'hsl(152, 45%, 42%)',
  steepener: 'hsl(280, 45%, 50%)',
  flattener: 'hsl(38, 70%, 50%)',
  'short-up': 'hsl(340, 50%, 50%)',
  'short-down': 'hsl(180, 45%, 42%)',
  'long-up': 'hsl(25, 70%, 46%)',
  'long-down': 'hsl(200, 52%, 45%)',
  custom: 'hsl(25, 80%, 50%)',
  base: 'hsl(215, 50%, 45%)',
};

function toTimeKey(tYears: number): string {
  return tYears.toFixed(8);
}

const CANONICAL_TICK_TENORS = [
  { tenor: '1M', t_years: 1 / 12 },
  { tenor: '3M', t_years: 0.25 },
  { tenor: '6M', t_years: 0.5 },
  { tenor: '1Y', t_years: 1 },
  { tenor: '2Y', t_years: 2 },
  { tenor: '3Y', t_years: 3 },
  { tenor: '5Y', t_years: 5 },
  { tenor: '7Y', t_years: 7 },
  { tenor: '10Y', t_years: 10 },
  { tenor: '15Y', t_years: 15 },
  { tenor: '20Y', t_years: 20 },
  { tenor: '25Y', t_years: 25 },
  { tenor: '30Y', t_years: 30 },
  { tenor: '40Y', t_years: 40 },
  { tenor: '50Y', t_years: 50 },
];

const EPSILON = 1e-6;

function dedupeSortedYears(values: number[]): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  const out: number[] = [];
  sorted.forEach((value) => {
    const prev = out[out.length - 1];
    if (prev === undefined || Math.abs(prev - value) > EPSILON) {
      out.push(value);
    }
  });
  return out;
}

function nearestAvailableYear(target: number, availableYears: number[]): number | null {
  if (availableYears.length === 0) return null;
  let best = availableYears[0];
  let bestDistance = Math.abs(best - target);

  for (let idx = 1; idx < availableYears.length; idx += 1) {
    const candidate = availableYears[idx];
    const distance = Math.abs(candidate - target);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }

  return best;
}

function snapTickToNearestAvailable(target: number, availableYears: number[]): number {
  const nearest = nearestAvailableYear(target, availableYears);
  if (nearest === null) return target;

  const tolerance = Math.max(0.02, target * 0.04);
  if (Math.abs(nearest - target) <= tolerance) {
    return nearest;
  }
  return target;
}

function buildAdaptiveXAxisTicks(maxYears: number, availableYears: number[]): number[] {
  if (!Number.isFinite(maxYears) || maxYears <= 0) return [];

  let targets: number[] = [];
  if (maxYears > 15) {
    targets = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50];
  } else if (maxYears > 8) {
    targets = [0.5, 1, 2, 3, 5, 7, 10, 12, 15];
  } else if (maxYears > 3) {
    targets = [0.25, 0.5, 1, 2, 3, 4, 5, 6, 7, 8];
  } else if (maxYears > 1) {
    targets = [1 / 12, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3];
  } else {
    targets = [1 / 52, 1 / 12, 2 / 12, 3 / 12, 4 / 12, 6 / 12, 9 / 12, 1];
  }

  const visibleTargets = targets.filter((value) => value <= maxYears + EPSILON);
  if (visibleTargets.length === 0) visibleTargets.push(maxYears);
  if (Math.abs((visibleTargets[visibleTargets.length - 1] ?? 0) - maxYears) > EPSILON) {
    visibleTargets.push(maxYears);
  }

  const snapped = visibleTargets.map((value) => snapTickToNearestAvailable(value, availableYears));
  const sorted = dedupeSortedYears(snapped.filter((value) => value >= 0 && value <= maxYears + EPSILON));

  if (sorted.length <= 2) return sorted;

  // Scale minimum gap with total range so labels never overlap
  const minGapYears =
    maxYears > 15 ? Math.max(2.5, maxYears * 0.08)
      : maxYears > 8 ? 0.8
        : maxYears > 3 ? 0.35
          : maxYears > 1 ? 0.15
            : 0.06;

  const thinned: number[] = [];
  sorted.forEach((value, idx) => {
    const isFirst = idx === 0;
    const isLast = idx === sorted.length - 1;
    if (isFirst || isLast) {
      thinned.push(value);
      return;
    }

    const previousKept = thinned[thinned.length - 1] ?? Number.NEGATIVE_INFINITY;
    if (value - previousKept >= minGapYears) {
      thinned.push(value);
    }
  });

  const last = sorted[sorted.length - 1];
  if (Math.abs((thinned[thinned.length - 1] ?? 0) - last) > EPSILON) {
    thinned.push(last);
  }

  // If the last and second-to-last ticks are too close, drop the second-to-last
  if (thinned.length >= 3) {
    const gap = thinned[thinned.length - 1] - thinned[thinned.length - 2];
    if (gap < minGapYears) {
      thinned.splice(thinned.length - 2, 1);
    }
  }

  return thinned;
}

function formatTenorFromYears(years: number): string {
  if (!Number.isFinite(years) || years <= 0) return 'ON';

  if (years < 1) {
    const months = Math.round(years * 12);
    if (months >= 1) return `${months}M`;
    const weeks = Math.max(1, Math.round(years * 52));
    return `${weeks}W`;
  }

  const wholeYears = Math.round(years);
  if (Math.abs(years - wholeYears) < 0.04) {
    return `${wholeYears}Y`;
  }

  // For non-whole years >= 1, always display in years (one decimal) — never months
  return `${years.toFixed(1)}Y`;
}

function formatMaturityLabel(years: number): string {
  if (Math.abs(years - 0.5) < 1e-9) return '6M';
  if (years < 1) return `${Math.round(years * 12)}M`;
  const whole = Math.round(years);
  if (Math.abs(years - whole) < 1e-9) return `${whole}Y`;
  return `${years.toFixed(1)}Y`;
}

function getScenarioColor(scenarioId: string, shockBps?: number): string {
  if (scenarioId.startsWith('custom-long-')) {
    return (shockBps ?? 0) >= 0
      ? SCENARIO_COLORS['long-up']
      : SCENARIO_COLORS['long-down'];
  }
  return SCENARIO_COLORS[scenarioId] ?? SCENARIO_COLORS.custom;
}

function isNoCurvesUploadedError(error: unknown): boolean {
  const message = (error instanceof Error ? error.message : String(error)).toLowerCase();
  return message.includes('no curves uploaded');
}

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((value, idx) => value === b[idx]);
}

function isExcelFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return lower.endsWith('.xlsx') || lower.endsWith('.xls');
}

interface CurvesAndScenariosCardProps {
  scenarios: Scenario[];
  onScenariosChange: (scenarios: Scenario[]) => void;
  selectedCurves: string[];
  onSelectedCurvesChange: (curves: string[]) => void;
  sessionId: string | null;
  hasCurves: boolean;
  onDataReset?: () => void;
}

export function CurvesAndScenariosCard({
  scenarios,
  onScenariosChange,
  selectedCurves,
  onSelectedCurvesChange,
  sessionId,
  hasCurves,
  onDataReset,
}: CurvesAndScenariosCardProps) {
  const { analysisDate } = useWhatIf();
  const [showDetails, setShowDetails] = useState(false);
  const [chartMode, setChartMode] = useState<ChartMode>('curves');
  const [chartCurves, setChartCurves] = useState<string[]>([]);
  const [chartScenarios, setChartScenarios] = useState<string[]>([]);
  const [baseCurveIdForScenarios, setBaseCurveIdForScenarios] = useState<string>('');
  const [maxMaturityYears, setMaxMaturityYears] = useState<number>(DEFAULT_CHART_MATURITY_YEARS);

  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customShockType, setCustomShockType] = useState<'parallel' | 'long'>('parallel');
  const [customBps, setCustomBps] = useState('');

  const [showUploadDropzone, setShowUploadDropzone] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isRefreshingSummary, setIsRefreshingSummary] = useState(false);

  const [curvesSummary, setCurvesSummary] = useState<CurvesSummaryResponse | null>(null);
  const [curvePointsById, setCurvePointsById] = useState<Record<string, CurvePoint[]>>({});

  const pointsRef = useRef<Record<string, CurvePoint[]>>({});
  const inFlightPointLoadsRef = useRef<Record<string, Promise<void>>>({});
  const dropzoneUploadInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    pointsRef.current = curvePointsById;
  }, [curvePointsById]);

  const availableCurves = useMemo(() => {
    // Keep the exact row order from uploaded Excel.
    return curvesSummary?.curves ?? [];
  }, [curvesSummary]);
  const availableCurveIds = useMemo(() => availableCurves.map((curve) => curve.curve_id), [availableCurves]);
  const curveIdSet = useMemo(() => new Set(availableCurveIds), [availableCurveIds]);

  const scenarioById = useMemo(() => {
    return new Map(scenarios.map((scenario) => [scenario.id, scenario]));
  }, [scenarios]);

  const defaultCurveId = useMemo(() => {
    const preferred = curvesSummary?.default_discount_curve_id;
    if (preferred && curveIdSet.has(preferred)) return preferred;
    return availableCurveIds[0] ?? '';
  }, [curvesSummary?.default_discount_curve_id, availableCurveIds, curveIdSet]);

  const curveColorById = useMemo(() => {
    const mapping: Record<string, string> = {};
    availableCurveIds.forEach((curveId, index) => {
      mapping[curveId] = CURVE_COLOR_PALETTE[index % CURVE_COLOR_PALETTE.length];
    });
    return mapping;
  }, [availableCurveIds]);

  const selectedCurvesCount = useMemo(() => {
    return selectedCurves.filter((curveId) => curveIdSet.has(curveId)).length;
  }, [selectedCurves, curveIdSet]);

  const enabledScenariosCount = useMemo(() => scenarios.filter((scenario) => scenario.enabled).length, [scenarios]);
  const curvesLoaded = availableCurveIds.length > 0;

  const ensureCurvePoints = useCallback(
    async (curveId: string) => {
      if (!curveId || !sessionId) return;
      if (pointsRef.current[curveId]) return;

      if (inFlightPointLoadsRef.current[curveId]) {
        await inFlightPointLoadsRef.current[curveId];
        return;
      }

      const loadPromise = (async () => {
        const response = await getCurvePoints(sessionId, curveId);
        setCurvePointsById((prev) => {
          if (prev[curveId]) return prev;
          return { ...prev, [curveId]: response.points };
        });
      })().finally(() => {
        delete inFlightPointLoadsRef.current[curveId];
      });

      inFlightPointLoadsRef.current[curveId] = loadPromise;
      await loadPromise;
    },
    [sessionId]
  );

  const applyCurvesSummary = useCallback(
    async (summary: CurvesSummaryResponse) => {
      setCurvesSummary(summary);
      setShowUploadDropzone(false);

      const ids = summary.curves.map((curve) => curve.curve_id);
      const idSet = new Set(ids);
      const preferred =
        summary.default_discount_curve_id && idSet.has(summary.default_discount_curve_id)
          ? summary.default_discount_curve_id
          : ids[0] ?? '';

      const normalizedSelected = selectedCurves.filter((curveId) => idSet.has(curveId));
      const nextSelected = normalizedSelected.length > 0
        ? normalizedSelected
        : preferred
          ? [preferred]
          : [];

      if (!arraysEqual(nextSelected, selectedCurves)) {
        onSelectedCurvesChange(nextSelected);
      }

      setChartCurves((prev) => {
        const normalized = prev.filter((curveId) => idSet.has(curveId));
        if (normalized.length > 0) return normalized;
        return preferred ? [preferred] : [];
      });

      setBaseCurveIdForScenarios((prev) => {
        if (prev && idSet.has(prev)) return prev;
        return preferred;
      });

      setChartScenarios((prev) => prev.filter((scenarioId) => scenarioById.has(scenarioId)));

      const maxTenorYears = summary.curves.reduce((max, curve) => Math.max(max, curve.max_t ?? 0), 0);
      const defaultMaxYears =
        maxTenorYears > 0
          ? Math.min(DEFAULT_CHART_MATURITY_YEARS, maxTenorYears)
          : DEFAULT_CHART_MATURITY_YEARS;
      setMaxMaturityYears(defaultMaxYears);

      const prefetchIds = new Set<string>(nextSelected);
      if (preferred) prefetchIds.add(preferred);
      await Promise.all(Array.from(prefetchIds).map((curveId) => ensureCurvePoints(curveId)));
    },
    [ensureCurvePoints, onSelectedCurvesChange, scenarioById, selectedCurves]
  );

  const refreshCurvesSummary = useCallback(async () => {
    if (!sessionId) return;
    setIsRefreshingSummary(true);
    try {
      const summary = await getCurvesSummary(sessionId);
      await applyCurvesSummary(summary);
    } catch (error) {
      if (isNoCurvesUploadedError(error)) {
        setCurvesSummary(null);
        setCurvePointsById({});
        onSelectedCurvesChange([]);
        setChartCurves([]);
        setBaseCurveIdForScenarios('');
        setShowUploadDropzone(true);
        return;
      }
      console.error('[CurvesAndScenariosCard] failed to refresh curves summary', error);
      toast.error('Failed to load curves', {
        description: 'Could not refresh curves data from server.',
      });
    } finally {
      setIsRefreshingSummary(false);
    }
  }, [applyCurvesSummary, onSelectedCurvesChange, sessionId]);

  // Stabilize with a ref so the effect only fires when sessionId or hasCurves
  // actually change – NOT when the callback chain updates during an upload.
  const refreshCurvesSummaryRef = useRef(refreshCurvesSummary);
  useEffect(() => {
    refreshCurvesSummaryRef.current = refreshCurvesSummary;
  }, [refreshCurvesSummary]);

  useEffect(() => {
    if (!sessionId) return;

    if (hasCurves) {
      void refreshCurvesSummaryRef.current();
    } else {
      setShowUploadDropzone(true);
      setCurvesSummary(null);
      setCurvePointsById({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, hasCurves]);

  useEffect(() => {
    if (!showDetails) return;

    if (chartMode === 'curves') {
      void Promise.all(chartCurves.map((curveId) => ensureCurvePoints(curveId)));
      return;
    }

    if (baseCurveIdForScenarios) {
      void ensureCurvePoints(baseCurveIdForScenarios);
    }
  }, [baseCurveIdForScenarios, chartCurves, chartMode, ensureCurvePoints, showDetails]);

  const handleCurveToggle = useCallback(
    (curveId: string) => {
      if (selectedCurves.includes(curveId)) {
        onSelectedCurvesChange(selectedCurves.filter((id) => id !== curveId));
        return;
      }

      onSelectedCurvesChange([...selectedCurves, curveId]);
      void ensureCurvePoints(curveId);
    },
    [ensureCurvePoints, onSelectedCurvesChange, selectedCurves]
  );

  const handleScenarioToggle = useCallback(
    (scenarioId: string) => {
      onScenariosChange(
        scenarios.map((scenario) =>
          scenario.id === scenarioId ? { ...scenario, enabled: !scenario.enabled } : scenario
        )
      );
    },
    [onScenariosChange, scenarios]
  );

  const handleAddCustomScenario = useCallback(() => {
    const bps = Number.parseInt(customBps, 10);
    if (Number.isNaN(bps)) return;

    const labelPrefix = customShockType === 'long' ? 'Custom Long' : 'Custom Parallel';
    const newScenario: Scenario = {
      id: `custom-${customShockType}-${Date.now()}`,
      name: labelPrefix,
      description:
        customShockType === 'long'
          ? 'Custom long-end shaped shock'
          : 'Custom parallel shock',
      shockBps: bps, // bps at long end for long-shape, parallel shift otherwise.
      enabled: true,
    };

    onScenariosChange([...scenarios, newScenario]);
    setCustomBps('');
    setCustomShockType('parallel');
    setShowCustomInput(false);
  }, [customBps, customShockType, onScenariosChange, scenarios]);

  const handleRemoveCustomScenario = useCallback(
    (scenarioId: string) => {
      onScenariosChange(scenarios.filter((scenario) => scenario.id !== scenarioId));
      setChartScenarios((prev) => prev.filter((id) => id !== scenarioId));
    },
    [onScenariosChange, scenarios]
  );

  const handleUploadFile = useCallback(
    async (file: File) => {
      if (!isExcelFile(file) || !sessionId) return;

      setIsUploading(true);
      setUploadProgress(0);
      try {
        const summary = await uploadCurvesExcel(sessionId, file, (pct) => setUploadProgress(pct));
        setUploadProgress(100);
        await applyCurvesSummary(summary);
      } catch (error) {
        console.error('[CurvesAndScenariosCard] failed to upload curves file', error);
        const msg = error instanceof Error ? error.message : String(error);
        toast.error('Curves upload failed', {
          description: msg.includes('Network error')
            ? 'Server may be restarting. Please try again in a moment.'
            : msg.length > 120 ? msg.slice(0, 120) + '…' : msg,
        });
      } finally {
        setIsUploading(false);
        setUploadProgress(0);
      }
    },
    [applyCurvesSummary, sessionId]
  );

  const handleCurveFileUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;
      void handleUploadFile(file);
    },
    [handleUploadFile]
  );

  const handleDropUpload = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const file = event.dataTransfer.files?.[0];
      if (!file) return;
      void handleUploadFile(file);
    },
    [handleUploadFile]
  );

  const handleWheelLoadClick = useCallback(() => {
    // Clear all curves state
    setCurvesSummary(null);
    setCurvePointsById({});
    onSelectedCurvesChange([]);
    setChartCurves([]);
    setShowUploadDropzone(true);
    // Invalidate calculation results
    onDataReset?.();
    // Delete curves from backend
    if (sessionId) {
      deleteCurves(sessionId).catch((err) =>
        console.error("[CurvesAndScenariosCard] deleteCurves failed", err)
      );
    }
  }, [sessionId, onSelectedCurvesChange, onDataReset]);
  const handleDropzoneBrowseClick = useCallback(() => {
    dropzoneUploadInputRef.current?.click();
  }, []);

  const allScenarioKeys = useMemo(() => scenarios.map((scenario) => scenario.id), [scenarios]);

  const toggleChartCurve = useCallback((curveId: string) => {
    setChartCurves((prev) => {
      if (prev.includes(curveId)) {
        if (prev.length === 1) return prev;
        return prev.filter((id) => id !== curveId);
      }
      return [...prev, curveId];
    });
    void ensureCurvePoints(curveId);
  }, [ensureCurvePoints]);

  const toggleChartScenario = useCallback((scenarioId: string) => {
    setChartScenarios((prev) => {
      if (prev.includes(scenarioId)) {
        return prev.filter((id) => id !== scenarioId);
      }
      return [...prev, scenarioId];
    });
  }, []);

  const selectAllChartCurves = useCallback(() => {
    setChartCurves((prev) => {
      if (prev.length === availableCurveIds.length) {
        return defaultCurveId ? [defaultCurveId] : [];
      }
      return [...availableCurveIds];
    });
    void Promise.all(availableCurveIds.map((curveId) => ensureCurvePoints(curveId)));
  }, [availableCurveIds, defaultCurveId, ensureCurvePoints]);

  const selectAllChartScenarios = useCallback(() => {
    setChartScenarios((prev) => {
      if (prev.length === allScenarioKeys.length) return [];
      return [...allScenarioKeys];
    });
  }, [allScenarioKeys]);

  const getScenarioLabel = useCallback(
    (scenarioId: string): string => {
      const scenario = scenarioById.get(scenarioId);
      return scenario?.name ?? scenarioId;
    },
    [scenarioById]
  );

  const getScenarioShock = useCallback(
    (scenarioId: string): number | null => {
      const scenario = scenarioById.get(scenarioId);
      return scenario?.shockBps ?? null;
    },
    [scenarioById]
  );

  const chartModel = useMemo(() => {
    const rows = new Map<string, ChartRow>();
    const series: ChartSeries[] = [];

    const upsertPoint = (seriesKey: string, point: CurvePoint) => {
      const key = toTimeKey(point.t_years);
      const existing = rows.get(key) ?? { t_years: point.t_years, tenor: point.tenor };
      if (!existing.tenor) {
        existing.tenor = point.tenor;
      }
      existing[seriesKey] = point.rate * 100;
      rows.set(key, existing);
    };

    if (chartMode === 'curves') {
      const curveIds = chartCurves.filter((curveId) => curveIdSet.has(curveId));
      curveIds.forEach((curveId) => {
        const points = curvePointsById[curveId] ?? [];
        if (points.length === 0) return;

        const seriesKey = `curve:${curveId}`;
        series.push({
          key: seriesKey,
          label: getCurveDisplayLabel(curveId),
          color: curveColorById[curveId] ?? CURVE_COLOR_PALETTE[0],
          strokeWidth: 2,
        });

        points.forEach((point) => upsertPoint(seriesKey, point));
      });
    } else {
      const baseCurveId = baseCurveIdForScenarios || defaultCurveId;
      const basePoints = baseCurveId ? curvePointsById[baseCurveId] ?? [] : [];

      if (baseCurveId && basePoints.length > 0) {
        const baseSeriesKey = `base:${baseCurveId}`;
        series.push({
          key: baseSeriesKey,
          label: `${getCurveDisplayLabel(baseCurveId)} (Base)`,
          color: SCENARIO_COLORS.base,
          strokeWidth: 2,
        });
        basePoints.forEach((point) => upsertPoint(baseSeriesKey, point));

        chartScenarios.forEach((scenarioId) => {
          const scenario = scenarioById.get(scenarioId);
          const customType = scenarioId.startsWith('custom-long-')
            ? 'long'
            : scenarioId.startsWith('custom-parallel-')
              ? 'parallel'
              : undefined;
          const shockedPoints = buildScenarioPoints(
            basePoints,
            scenarioId,
            scenario?.shockBps,
            customType
          );
          const shock = scenario?.shockBps;
          const shockLabel = shock === undefined
            ? ''
            : ` (${shock > 0 ? '+' : ''}${shock}bp)`;
          const isCustomScenario = scenarioId.startsWith('custom-');
          const color = getScenarioColor(scenarioId, shock);

          const scenarioSeriesKey = `scenario:${scenarioId}`;
          series.push({
            key: scenarioSeriesKey,
            label: `${getScenarioLabel(scenarioId)}${shockLabel}`,
            color,
            strokeWidth: 1.6,
            dash: isCustomScenario ? '3 3' : '5 5',
          });

          shockedPoints.forEach((point) => upsertPoint(scenarioSeriesKey, point));
        });
      }
    }

    const sortedRows = Array.from(rows.values()).sort((a, b) => a.t_years - b.t_years);
    return { rows: sortedRows, series };
  }, [
    baseCurveIdForScenarios,
    chartCurves,
    chartMode,
    chartScenarios,
    curveColorById,
    curveIdSet,
    curvePointsById,
    defaultCurveId,
    getScenarioLabel,
    scenarioById,
  ]);

  const chartRowByTimeKey = useMemo(() => {
    const mapping = new Map<string, ChartRow>();
    chartModel.rows.forEach((row) => mapping.set(toTimeKey(row.t_years), row));
    return mapping;
  }, [chartModel.rows]);

  const availableTickYears = useMemo(() => {
    const dataYears = chartModel.rows.map((row) => row.t_years);
    const canonicalYears = CANONICAL_TICK_TENORS.map((tick) => tick.t_years);
    return dedupeSortedYears([...dataYears, ...canonicalYears]);
  }, [chartModel.rows]);

  const maxAvailableMaturityYears = useMemo(() => {
    const summaryMax = availableCurves.reduce((max, curve) => Math.max(max, curve.max_t ?? 0), 0);
    const chartMax = chartModel.rows.length > 0 ? chartModel.rows[chartModel.rows.length - 1].t_years : 0;
    const maxYears = Math.max(summaryMax, chartMax);
    return maxYears > 0 ? maxYears : DEFAULT_CHART_MATURITY_YEARS;
  }, [availableCurves, chartModel.rows]);

  useEffect(() => {
    setMaxMaturityYears((prev) => {
      const minValue = Math.min(MIN_CHART_MATURITY_YEARS, maxAvailableMaturityYears);
      return Math.min(maxAvailableMaturityYears, Math.max(minValue, prev));
    });
  }, [maxAvailableMaturityYears]);

  const xAxisTicks = useMemo(() => {
    return buildAdaptiveXAxisTicks(maxMaturityYears, availableTickYears);
  }, [availableTickYears, maxMaturityYears]);

  const yAxisDomain = useMemo<[number, number]>(() => {
    const visibleRows = chartModel.rows.filter(
      (row) => row.t_years >= 0 && row.t_years <= maxMaturityYears
    );
    const rowsToInspect = visibleRows.length > 0 ? visibleRows : chartModel.rows;
    const seriesKeys = chartModel.series.map((series) => series.key);

    let minValue = Number.POSITIVE_INFINITY;
    let maxValue = Number.NEGATIVE_INFINITY;

    rowsToInspect.forEach((row) => {
      seriesKeys.forEach((seriesKey) => {
        const value = row[seriesKey];
        if (typeof value === 'number' && Number.isFinite(value)) {
          minValue = Math.min(minValue, value);
          maxValue = Math.max(maxValue, value);
        }
      });
    });

    if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
      return [0, 5];
    }

    let span = maxValue - minValue;
    if (span < MIN_Y_AXIS_SPAN_PERCENT) {
      const center = (maxValue + minValue) / 2;
      minValue = center - MIN_Y_AXIS_SPAN_PERCENT / 2;
      maxValue = center + MIN_Y_AXIS_SPAN_PERCENT / 2;
      span = MIN_Y_AXIS_SPAN_PERCENT;
    }

    const padding = Math.max(MIN_Y_AXIS_PADDING_PERCENT, span * 0.1);
    return [minValue - padding, maxValue + padding];
  }, [chartModel.rows, chartModel.series, maxMaturityYears]);

  const xAxisTick = useCallback(
    ({ x, y, payload }: AxisTickProps) => {
      const tYears = Number(payload?.value);
      if (!Number.isFinite(tYears)) return null;

      const exactRow = chartRowByTimeKey.get(toTimeKey(tYears));
      const tenor = exactRow?.tenor || formatTenorFromYears(tYears);
      const dateLabel = getTenorCalendarDateLabel(analysisDate, tenor);

      return (
        <g transform={`translate(${x},${y})`}>
          <text
            x={0}
            y={0}
            dy={10}
            textAnchor="middle"
            fill="hsl(var(--muted-foreground))"
            fontSize={10}
            fontWeight={500}
          >
            {tenor}
          </text>
          {dateLabel ? (
            <text
              x={0}
              y={0}
              dy={22}
              textAnchor="middle"
              fill="hsl(var(--muted-foreground))"
              fontSize={8}
              opacity={0.75}
            >
              {dateLabel}
            </text>
          ) : null}
        </g>
      );
    },
    [analysisDate, chartRowByTimeKey]
  );

  const customTooltip = useCallback(
    ({ active, payload, label }: ChartTooltipProps) => {
      if (!active || !Array.isArray(payload) || payload.length === 0) return null;

      const tYears = Number(label);
      const row = Number.isFinite(tYears) ? chartRowByTimeKey.get(toTimeKey(tYears)) : null;
      const tenor = row?.tenor ?? '';
      const dateLabel = tenor ? getTenorCalendarDateLabel(analysisDate, tenor) : null;

      return (
        <div
          style={{
            background: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '8px',
            padding: '8px 10px',
            fontSize: '11px',
            minWidth: '180px',
          }}
        >
          <div className="font-medium text-foreground mb-1">
            {tenor}
            {dateLabel ? <span className="text-muted-foreground font-normal"> {' '}• {dateLabel}</span> : null}
          </div>
          <div className="space-y-0.5">
            {payload
              .filter((entry) => typeof entry.value === 'number')
              .map((entry) => (
                <div key={entry.dataKey ?? entry.name ?? String(entry.value)} className="flex items-center justify-between gap-3">
                  <span className="truncate" style={{ color: entry.color }}>
                    {entry.name}
                  </span>
                  <span className="font-medium text-foreground">{Number(entry.value).toFixed(2)}%</span>
                </div>
              ))}
          </div>
        </div>
      );
    },
    [analysisDate, chartRowByTimeKey]
  );

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Curves & Scenarios</span>
            <div className="flex items-center gap-1 ml-2">
              {isUploading || isRefreshingSummary ? (
                <AlertCircle className="h-3 w-3 text-muted-foreground" />
              ) : curvesLoaded ? (
                <CheckCircle2 className="h-3 w-3 text-success" />
              ) : (
                <AlertCircle className="h-3 w-3 text-muted-foreground" />
              )}
              <span className={`text-[9px] ${curvesLoaded ? 'text-success' : 'text-muted-foreground'}`}>
                {curvesLoaded ? 'Curves loaded' : 'No curves'}
              </span>
            </div>
          </div>
          <span className="text-[10px] font-medium text-muted-foreground">
            {selectedCurvesCount} curves • {enabledScenariosCount} scenarios
          </span>
        </div>

        <div className="dashboard-card-content">
          <div className="flex gap-3 flex-1 min-h-0">
            <div className="flex-1 flex flex-col min-w-0">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
                Curves
              </div>

              {showUploadDropzone ? (
                <div
                  className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleDropUpload}
                >
                  <Upload className="h-6 w-6 text-muted-foreground mb-2" />
                  <p className="text-xs text-muted-foreground text-center mb-2">
                    Drop Excel or click to upload
                  </p>
                  <Input
                    ref={dropzoneUploadInputRef}
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    onChange={handleCurveFileUpload}
                    disabled={isUploading}
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDropzoneBrowseClick}
                      className="h-6 text-[10px]"
                      disabled={isUploading}
                    >
                      Browse
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={() => {
                        if (curvesLoaded) {
                          setShowUploadDropzone(false);
                        }
                      }}
                    >
                      Sample
                    </Button>
                  </div>
                  {isUploading && (
                    <div className="mt-3 w-full max-w-xs">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all duration-300"
                            style={{ width: `${uploadProgress}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-medium text-muted-foreground tabular-nums w-7 text-right">
                          {uploadProgress}%
                        </span>
                      </div>
                      <p className="text-[9px] text-muted-foreground mt-1">Uploading curves...</p>
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <ScrollArea className="flex-1">
                    <div className="space-y-1 pr-2">
                      {availableCurves.map((curve) => {
                        const checked = selectedCurves.includes(curve.curve_id);
                        return (
                          <label
                            key={curve.curve_id}
                            className={`flex items-center gap-1.5 py-1 px-1.5 rounded cursor-pointer transition-colors text-xs ${checked ? 'bg-primary/10' : 'hover:bg-muted/50'}`}
                          >
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => handleCurveToggle(curve.curve_id)}
                              className="h-3 w-3 rounded-full border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-transparent [&_svg]:hidden"
                            />
                            <span className={`truncate ${checked ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                              {getCurveDisplayLabel(curve.curve_id)}
                            </span>
                            <span className="ml-auto" />
                            <CheckCircle2 className="h-2.5 w-2.5 text-success shrink-0" />
                          </label>
                        );
                      })}
                      {availableCurves.length === 0 ? (
                        <div className="text-[10px] text-muted-foreground py-2 px-1">
                          Upload a curves Excel file to populate this list.
                        </div>
                      ) : null}
                    </div>
                  </ScrollArea>
                </>
              )}
            </div>

            <div className="w-px bg-border" />

            <div className="flex-1 flex flex-col min-w-0">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Scenarios
                </span>
                <Popover open={showCustomInput} onOpenChange={setShowCustomInput}>
                  <PopoverTrigger asChild>
                    <button className="text-[9px] text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5">
                      <Plus className="h-2.5 w-2.5" />
                      Custom
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="w-48 p-2" align="end">
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-foreground">Add Custom Scenario</div>
                      <div className="space-y-1">
                        <div className="text-[10px] text-muted-foreground">Shock type</div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setCustomShockType('parallel')}
                            className="inline-flex items-center gap-1 text-[10px] text-foreground"
                          >
                            <span
                              className={`h-2.5 w-2.5 rounded-full border ${
                                customShockType === 'parallel'
                                  ? 'bg-primary border-primary'
                                  : 'bg-background border-muted-foreground/40'
                              }`}
                            />
                            Parallel
                          </button>
                          <button
                            type="button"
                            onClick={() => setCustomShockType('long')}
                            className="inline-flex items-center gap-1 text-[10px] text-foreground"
                          >
                            <span
                              className={`h-2.5 w-2.5 rounded-full border ${
                                customShockType === 'long'
                                  ? 'bg-primary border-primary'
                                  : 'bg-background border-muted-foreground/40'
                              }`}
                            />
                            Long
                          </button>
                        </div>
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        {customShockType === 'long'
                          ? 'Long-end shock magnitude (basis points)'
                          : 'Parallel shock (basis points)'}
                      </div>
                      <div className="flex gap-1.5">
                        <Input
                          type="number"
                          placeholder="e.g. +150 or -100"
                          value={customBps}
                          onChange={(event) => setCustomBps(event.target.value)}
                          className="h-7 text-xs"
                        />
                        <Button
                          size="sm"
                          onClick={handleAddCustomScenario}
                          disabled={!customBps || Number.isNaN(Number.parseInt(customBps, 10))}
                          className="h-7 px-2 text-xs"
                        >
                          Add
                        </Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>

              <ScrollArea className="flex-1">
                <div className="space-y-1 pr-2">
                  {scenarios.map((scenario) => {
                    const isCustom = scenario.id.startsWith('custom-');
                    return (
                      <label
                        key={scenario.id}
                        className={`flex items-center gap-1.5 py-1 px-1.5 rounded cursor-pointer transition-colors text-xs ${scenario.enabled ? 'bg-primary/10' : 'hover:bg-muted/50'}`}
                      >
                        <Checkbox
                          checked={scenario.enabled}
                          onCheckedChange={() => handleScenarioToggle(scenario.id)}
                          className="h-3 w-3 rounded-full border-muted-foreground/40 bg-background data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-transparent [&_svg]:hidden"
                        />
                        <span className={`truncate ${scenario.enabled ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                          {scenario.name}
                        </span>
                        <span
                          className={`shrink-0 text-[9px] font-medium ${scenario.shockBps > 0 ? 'text-destructive' : 'text-success'}`}
                        >
                          {scenario.shockBps > 0 ? '+' : ''}
                          {scenario.shockBps}bp
                        </span>
                        {isCustom ? (
                          <button
                            onClick={(event) => {
                              event.preventDefault();
                              handleRemoveCustomScenario(scenario.id);
                            }}
                            className="shrink-0 ml-auto text-muted-foreground hover:text-destructive transition-colors"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>
          </div>

          <div className="pt-2 border-t border-border/30 mt-2 flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleWheelLoadClick}
              className="h-6 w-6 p-0 shrink-0 rounded-full"
              title="Load curves"
            >
              <RotateCcw className="h-3 w-3" />
            </Button>
            <Button size="sm" onClick={() => setShowDetails(true)} className="flex-1 h-6 text-xs">
              <Eye className="mr-1 h-3 w-3" />
              View details
            </Button>
          </div>
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Curve & Scenario Visualization
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 flex flex-col gap-4 overflow-hidden">
            <div className="h-64 w-full">
              {chartModel.rows.length > 0 && chartModel.series.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartModel.rows}
                    margin={{
                      top: 5,
                      right: 30,
                      left: 0,
                      bottom: analysisDate ? 12 : 5,
                    }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      type="number"
                      dataKey="t_years"
                      domain={[0, maxMaturityYears]}
                      allowDataOverflow
                      ticks={xAxisTicks}
                      tick={xAxisTick}
                      tickLine={false}
                      minTickGap={40}
                      interval="preserveStartEnd"
                      stroke="hsl(var(--border))"
                      height={analysisDate ? 36 : 18}
                    />
                    <YAxis
                      domain={yAxisDomain}
                      tick={{
                        fontSize: 10,
                        fill: 'hsl(var(--muted-foreground))',
                      }}
                      stroke="hsl(var(--border))"
                      tickFormatter={(value: number) => `${value.toFixed(2)}%`}
                    />
                    <Tooltip content={customTooltip} />
                    <Legend wrapperStyle={{ fontSize: '9px' }} />

                    {chartModel.series.map((series) => (
                      <Line
                        key={series.key}
                        type="monotone"
                        dataKey={series.key}
                        stroke={series.color}
                        strokeWidth={series.strokeWidth}
                        strokeDasharray={series.dash}
                        dot={false}
                        name={series.label}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full rounded-lg border border-dashed border-border flex items-center justify-center text-xs text-muted-foreground">
                  Upload and select curves to visualize.
                </div>
              )}
            </div>

            <div className="px-1 pb-1">
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                  Max maturity: {formatMaturityLabel(maxMaturityYears)}
                </span>
                <Slider
                  value={[maxMaturityYears]}
                  min={Math.min(MIN_CHART_MATURITY_YEARS, maxAvailableMaturityYears)}
                  max={maxAvailableMaturityYears}
                  step={0.5}
                  onValueChange={(values) => {
                    const value = values[0] ?? maxAvailableMaturityYears;
                    const minValue = Math.min(MIN_CHART_MATURITY_YEARS, maxAvailableMaturityYears);
                    setMaxMaturityYears(Math.min(maxAvailableMaturityYears, Math.max(minValue, value)));
                  }}
                  className="flex-1"
                />
              </div>
            </div>

            <ScrollArea className="flex-1 min-h-0">
              <div className="border-t border-border pt-3 space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center h-6 p-0.5 bg-primary rounded-md w-fit">
                    <button
                      onClick={() => setChartMode('curves')}
                      className={`h-5 px-3 text-[10px] font-medium rounded-sm transition-all ${
                        chartMode === 'curves'
                          ? 'bg-background text-foreground shadow-sm'
                          : 'text-primary-foreground/70 hover:text-primary-foreground'
                      }`}
                    >
                      Curves
                    </button>
                    <button
                      onClick={() => setChartMode('scenarios')}
                      className={`h-5 px-3 text-[10px] font-medium rounded-sm transition-all ${
                        chartMode === 'scenarios'
                          ? 'bg-background text-foreground shadow-sm'
                          : 'text-primary-foreground/70 hover:text-primary-foreground'
                      }`}
                    >
                      Scenarios
                    </button>
                  </div>

                  {chartMode === 'scenarios' ? (
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                        Base curve
                      </span>
                      <select
                        value={baseCurveIdForScenarios}
                        onChange={(event) => {
                          const curveId = event.target.value;
                          setBaseCurveIdForScenarios(curveId);
                          void ensureCurvePoints(curveId);
                        }}
                        className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground"
                      >
                        {availableCurves.map((curve) => (
                          <option key={curve.curve_id} value={curve.curve_id}>
                            {getCurveDisplayLabel(curve.curve_id)}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : null}
                </div>

                {chartMode === 'curves' ? (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                        Display Curves
                      </span>
                      <button
                        onClick={selectAllChartCurves}
                        className="inline-flex items-center gap-1 text-[9px] text-primary hover:text-primary/80 transition-colors"
                      >
                        <CheckSquare className="h-3 w-3" />
                        {chartCurves.length === availableCurveIds.length ? 'Deselect all' : 'Select all'}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {availableCurves.map((curve) => {
                        const curveId = curve.curve_id;
                        const selected = chartCurves.includes(curveId);
                        return (
                          <button
                            key={curveId}
                            onClick={() => toggleChartCurve(curveId)}
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                              selected
                                ? 'bg-primary/15 text-primary border border-primary/30'
                                : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                            }`}
                            title={getCurveTooltipLabel(curveId)}
                          >
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: curveColorById[curveId] ?? CURVE_COLOR_PALETTE[0] }}
                            />
                            {getCurveDisplayLabel(curveId)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                          Display Scenarios
                        </span>
                        <button
                          onClick={selectAllChartScenarios}
                          className="inline-flex items-center gap-1 text-[9px] text-primary hover:text-primary/80 transition-colors"
                        >
                          <CheckSquare className="h-3 w-3" />
                          {chartScenarios.length === allScenarioKeys.length ? 'Deselect all' : 'Select all'}
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {scenarios.map((scenario) => {
                          const selected = chartScenarios.includes(scenario.id);
                          return (
                            <button
                              key={scenario.id}
                              onClick={() => toggleChartScenario(scenario.id)}
                              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                                selected
                                  ? 'bg-primary/15 text-primary border border-primary/30'
                                  : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                              }`}
                            >
                              <span
                                className="h-2 w-2 rounded-full"
                                style={{
                                  backgroundColor: getScenarioColor(
                                    scenario.id,
                                    scenario.shockBps
                                  ),
                                }}
                              />
                              {scenario.name}
                              {getScenarioShock(scenario.id) !== null ? (
                                <span
                                  className={`text-[8px] ${
                                    (getScenarioShock(scenario.id) ?? 0) > 0 ? 'text-destructive' : 'text-success'
                                  }`}
                                >
                                  ({(getScenarioShock(scenario.id) ?? 0) > 0 ? '+' : ''}
                                  {getScenarioShock(scenario.id)}bp)
                                </span>
                              ) : null}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
