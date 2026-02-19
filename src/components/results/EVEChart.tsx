/**
 * EVEChart.tsx – Dual-stack bar chart for Economic Value of Equity (EVE).
 *
 * === VISUAL DESIGN ===
 * Each tenor bucket shows TWO side-by-side stacked bars:
 *   - "Base" stack (lighter colours)
 *   - "Scenario" stack (darker colours) – whichever scenario is selected
 * Within each stack, assets grow upward (green) and liabilities grow
 * downward (red). What-If impact is rendered as amber segments:
 *   - Increase: amber "outside" the baseline (fill + stroke = amber)
 *   - Decrease: amber "inside" the baseline (fill = amber, stroke = original colour)
 * Two Net EV lines (base=light blue, scenario=dark blue) overlay the bars.
 *
 * === SCENARIO SELECTION ===
 * The scenario is controlled by the parent (ResultsCard) via the
 * `selectedScenario` prop. This chart has no internal scenario selector.
 */
import { useMemo, useCallback } from 'react';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { getCalendarLabelFromMonths } from '@/lib/calendarLabels';

// ─── Constants ───────────────────────────────────────────────────────────────

const TENORS = [
  { label: '1M', months: 1 },
  { label: '3M', months: 3 },
  { label: '6M', months: 6 },
  { label: '1Y', months: 12 },
  { label: '2Y', months: 24 },
  { label: '3Y', months: 36 },
  { label: '5Y', months: 60 },
  { label: '7Y', months: 84 },
  { label: '10Y', months: 120 },
  { label: '15Y', months: 180 },
  { label: '20Y', months: 240 },
  { label: '30Y', months: 360 },
];

// ─── Colours ─────────────────────────────────────────────────────────────────

const C = {
  baseAsset:      '#5bb88a',
  scenarioAsset:  '#3a8a62',
  baseLiab:       '#e07872',
  scenarioLiab:   '#c44d48',
  whatIf:         '#daa44a',
  whatIfStroke:   '#c08e38',
  netBase:        '#6ba3c7',
  netScenario:    '#2e5f8a',
} as const;

const INSIDE_STROKE = 2.5;

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TENOR_MONTHS = TENORS.map(t => t.months);

function allocateWhatIfByTenor(
  modifications: any[],
  analysisDate: Date | null,
): Array<{ dA: number; dL: number }> {
  const perTenor = TENORS.map(() => ({ dA: 0, dL: 0 }));

  modifications.forEach((mod) => {
    const sign = mod.type === 'add' ? 1 : -1;
    const notional = (mod.notional || 0) * sign;
    const key: 'dA' | 'dL' | null =
      mod.category === 'asset' ? 'dA' : mod.category === 'liability' ? 'dL' : null;
    if (!key) return;

    let matMonths: number | null = null;
    if (mod.maturityDate && analysisDate) {
      const mat = new Date(mod.maturityDate);
      matMonths =
        (mat.getFullYear() - analysisDate.getFullYear()) * 12 +
        (mat.getMonth() - analysisDate.getMonth()) +
        (mat.getDate() - analysisDate.getDate()) / 30;
      if (matMonths < 0) matMonths = 0;
    } else if (mod.maturity != null) {
      matMonths = mod.maturity * 12;
    }

    if (matMonths != null) {
      if (matMonths <= TENOR_MONTHS[0]) {
        perTenor[0][key] += notional;
      } else if (matMonths >= TENOR_MONTHS[TENOR_MONTHS.length - 1]) {
        perTenor[TENOR_MONTHS.length - 1][key] += notional;
      } else {
        for (let i = 0; i < TENOR_MONTHS.length - 1; i++) {
          if (matMonths <= TENOR_MONTHS[i + 1]) {
            const span = TENOR_MONTHS[i + 1] - TENOR_MONTHS[i];
            const w = (matMonths - TENOR_MONTHS[i]) / span;
            perTenor[i][key]     += notional * (1 - w);
            perTenor[i + 1][key] += notional * w;
            break;
          }
        }
      }
    } else {
      const share = notional / TENORS.length;
      perTenor.forEach(t => { t[key] += share; });
    }
  });

  return perTenor;
}

function generateBaseline(scenario: string, analysisDate: Date | null) {
  const getScenarioMultiplier = (sc: string, idx: number) => {
    switch (sc) {
      case 'parallel-up':   return 1.2;
      case 'parallel-down': return -0.8;
      case 'steepener':     return (idx / TENORS.length) * 1.5;
      case 'flattener':     return ((TENORS.length - idx) / TENORS.length) * 1.2;
      case 'short-up':      return idx < 4 ? 0.8 : 0.2;
      case 'short-down':    return idx < 4 ? -0.6 : -0.1;
      default:              return 0;
    }
  };

  return TENORS.map((tenor, i) => {
    const assetsBase = 80 + Math.sin(i * 0.5) * 30 + i * 5;
    const liabsBase  = -(70 + Math.cos(i * 0.4) * 25 + i * 4);
    const m = getScenarioMultiplier(scenario, i);
    return {
      tenor: tenor.label,
      calendarLabel: analysisDate ? getCalendarLabelFromMonths(analysisDate, tenor.months) : null,
      assetsBase,
      liabsBase,
      assetsScenario: assetsBase + m * (10 + i * 2),
      liabsScenario:  liabsBase  - m * (8 + i * 1.5),
    };
  });
}

function decomposeStack(A: number, L: number, dA: number, dL: number) {
  const assetReduction = Math.min(-Math.min(dA, 0), A);
  const liabReduction  = Math.min(Math.max(dL, 0), -L);
  return {
    assets_kept:           Math.max(0, A - assetReduction),
    assets_reduced_inside: assetReduction,
    assets_added_outside:  Math.max(dA, 0),
    liabs_kept:            Math.min(0, L + liabReduction),
    liabs_reduced_inside:  -liabReduction,
    liabs_added_outside:   Math.min(dL, 0),
  };
}

function buildEveChartData(
  scenarioId: string,
  perTenorDeltas: Array<{ dA: number; dL: number }>,
  analysisDate: Date | null,
) {
  const baselines = generateBaseline(scenarioId, analysisDate);

  return baselines.map((b, i) => {
    const dA = perTenorDeltas[i].dA / 1e7;
    const dL = -perTenorDeltas[i].dL / 1e7;

    const base = decomposeStack(b.assetsBase, b.liabsBase, dA, dL);
    const scen = decomposeStack(b.assetsScenario, b.liabsScenario, dA, dL);

    return {
      tenor: b.tenor,
      calendarLabel: b.calendarLabel,
      // Base stack
      ak_b: base.assets_kept, ari_b: base.assets_reduced_inside, aao_b: base.assets_added_outside,
      lk_b: base.liabs_kept,  lri_b: base.liabs_reduced_inside,  lao_b: base.liabs_added_outside,
      // Scenario stack
      ak_s: scen.assets_kept, ari_s: scen.assets_reduced_inside, aao_s: scen.assets_added_outside,
      lk_s: scen.liabs_kept,  lri_s: scen.liabs_reduced_inside,  lao_s: scen.liabs_added_outside,
      // Net EV lines (post what-if)
      netBase:     (b.assetsBase     + dA) + (b.liabsBase     + dL),
      netScenario: (b.assetsScenario + dA) + (b.liabsScenario + dL),
      // Tooltip raw
      _assetsBase: b.assetsBase, _liabsBase: b.liabsBase,
      _assetsScenario: b.assetsScenario, _liabsScenario: b.liabsScenario,
      _dA: dA, _dL: dL,
    };
  });
}

// ─── Format helpers ──────────────────────────────────────────────────────────

function fmtVal(v: number) {
  return v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
}

function fmtDelta(v: number) {
  return `${v >= 0 ? '+' : ''}${fmtVal(v)}`;
}

// ─── Custom bar shape ────────────────────────────────────────────────────────

interface StyledBarProps {
  x?: number; y?: number; width?: number; height?: number;
  fillColor: string; strokeColor: string; sw: number; inset?: boolean;
}
function StyledBar({ x = 0, y = 0, width = 0, height = 0, fillColor, strokeColor, sw, inset }: StyledBarProps) {
  if (height === 0 || width === 0) return null;
  const ry = height < 0 ? y + height : y;
  const rh = Math.abs(height);

  if (inset && sw > 0) {
    const half = sw / 2;
    return (
      <g>
        <rect x={x} y={ry} width={width} height={rh} fill={fillColor} />
        <rect
          x={x + half} y={ry + half}
          width={Math.max(0, width - sw)} height={Math.max(0, rh - sw)}
          fill="none" stroke={strokeColor} strokeWidth={sw}
        />
      </g>
    );
  }

  if (sw === 0) {
    return <rect x={x} y={ry - 0.5} width={width} height={rh + 1} fill={fillColor} />;
  }
  return (
    <rect x={x} y={ry} width={width} height={rh}
      fill={fillColor} stroke={strokeColor} strokeWidth={sw} />
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

interface EVEChartProps {
  className?: string;
  fullWidth?: boolean;
  analysisDate?: Date | null;
  selectedScenario: string;
  scenarioLabel: string;
}

export function EVEChart({ className, fullWidth = false, analysisDate, selectedScenario, scenarioLabel }: EVEChartProps) {
  const { modifications } = useWhatIf();

  const perTenorDeltas = useMemo(
    () => allocateWhatIfByTenor(modifications, analysisDate ?? null),
    [modifications, analysisDate],
  );
  const hasWhatIf = modifications.length > 0;

  const chartData = useMemo(
    () => buildEveChartData(selectedScenario, perTenorDeltas, analysisDate ?? null),
    [selectedScenario, perTenorDeltas, analysisDate],
  );

  const CustomXAxisTick = useCallback(({ x, y, payload }: any) => {
    const dp = chartData.find((d) => d.tenor === payload.value);
    return (
      <g transform={`translate(${x},${y})`}>
        <text x={0} y={0} dy={10} textAnchor="middle"
          fill="hsl(var(--muted-foreground))" fontSize={fullWidth ? 10 : 9} fontWeight={500}>
          {payload.value}
        </text>
        {dp?.calendarLabel && (
          <text x={0} y={0} dy={22} textAnchor="middle"
            fill="hsl(var(--muted-foreground))" fontSize={fullWidth ? 8 : 7} opacity={0.6}>
            {dp.calendarLabel}
          </text>
        )}
      </g>
    );
  }, [chartData, fullWidth]);

  const CustomTooltip = useCallback(({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const dp = chartData.find((d) => d.tenor === label);
    if (!dp) return null;

    const sections = [
      { tag: 'Base', a: dp._assetsBase, l: dp._liabsBase, net: dp.netBase, color: C.netBase },
      { tag: scenarioLabel || 'Scenario', a: dp._assetsScenario, l: dp._liabsScenario, net: dp.netScenario, color: C.netScenario },
    ];

    return (
      <div className="rounded-lg border border-border/40 bg-background/95 backdrop-blur-sm px-3 py-2 text-[11px] shadow-xl min-w-[190px]">
        <div className="font-semibold text-foreground mb-1.5 pb-1 border-b border-border/30">
          {label}
          {dp.calendarLabel && (
            <span className="text-muted-foreground font-normal ml-1.5">({dp.calendarLabel})</span>
          )}
        </div>
        {sections.map((s, idx) => (
          <div key={s.tag} className={idx > 0 ? 'mt-1.5 pt-1.5 border-t border-border/20' : ''}>
            <div className="text-muted-foreground font-medium mb-0.5">{s.tag}</div>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-px">
              <span className="text-muted-foreground">Assets:</span>
              <span className="text-right font-mono">{fmtVal(s.a)}</span>
              <span className="text-muted-foreground">Liabilities:</span>
              <span className="text-right font-mono">{fmtVal(Math.abs(s.l))}</span>
              {hasWhatIf && (
                <>
                  <span style={{ color: C.whatIf }}>Δ Assets:</span>
                  <span className="text-right font-mono" style={{ color: C.whatIf }}>{fmtDelta(dp._dA)}</span>
                  <span style={{ color: C.whatIf }}>Δ Liabs:</span>
                  <span className="text-right font-mono" style={{ color: C.whatIf }}>{fmtDelta(dp._dL)}</span>
                </>
              )}
              <span className="font-medium" style={{ color: s.color }}>Net EV:</span>
              <span className="text-right font-mono font-medium" style={{ color: s.color }}>{fmtVal(s.net)}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }, [chartData, hasWhatIf, scenarioLabel]);

  const chartHeight = fullWidth ? 'h-[calc(100%-56px)]' : 'h-[180px]';

  const makeShape = (fill: string, stroke: string, sw: number, inset: boolean) => (props: any) => (
    <StyledBar {...props} fillColor={fill} strokeColor={stroke} sw={sw} inset={inset} />
  );

  const barDefs = [
    // BASE stack
    { key: 'ak_b',  sid: 'base',     fill: C.baseAsset,      stroke: C.baseAsset,      sw: 0, inset: false },
    { key: 'ari_b', sid: 'base',     fill: C.whatIf,          stroke: C.baseAsset,      sw: INSIDE_STROKE, inset: true },
    { key: 'aao_b', sid: 'base',     fill: C.whatIf,          stroke: C.whatIfStroke,    sw: 0, inset: false },
    { key: 'lk_b',  sid: 'base',     fill: C.baseLiab,        stroke: C.baseLiab,       sw: 0, inset: false },
    { key: 'lri_b', sid: 'base',     fill: C.whatIf,          stroke: C.baseLiab,       sw: INSIDE_STROKE, inset: true },
    { key: 'lao_b', sid: 'base',     fill: C.whatIf,          stroke: C.whatIfStroke,    sw: 0, inset: false },
    // SCENARIO stack
    { key: 'ak_s',  sid: 'scenario', fill: C.scenarioAsset,   stroke: C.scenarioAsset,  sw: 0, inset: false },
    { key: 'ari_s', sid: 'scenario', fill: C.whatIf,           stroke: C.scenarioAsset,  sw: INSIDE_STROKE, inset: true },
    { key: 'aao_s', sid: 'scenario', fill: C.whatIf,           stroke: C.whatIfStroke,    sw: 0, inset: false },
    { key: 'lk_s',  sid: 'scenario', fill: C.scenarioLiab,    stroke: C.scenarioLiab,   sw: 0, inset: false },
    { key: 'lri_s', sid: 'scenario', fill: C.whatIf,           stroke: C.scenarioLiab,   sw: INSIDE_STROKE, inset: true },
    { key: 'lao_s', sid: 'scenario', fill: C.whatIf,           stroke: C.whatIfStroke,    sw: 0, inset: false },
  ];

  return (
    <div className={`h-full flex flex-col ${className ?? ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50">
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          Economic Value (EVE)
        </span>
        <span className="text-[9px] text-muted-foreground">
          {scenarioLabel}
          {hasWhatIf && <span className="ml-1 text-warning">(+What-If)</span>}
        </span>
      </div>

      {/* Chart */}
      <div className={`flex-1 px-1 ${fullWidth ? 'min-h-0' : chartHeight}`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 8, right: 10, left: 0, bottom: 25 }}
            stackOffset="sign"
            barGap={0}
            barCategoryGap="25%"
          >
            <CartesianGrid
              strokeDasharray="3 3" stroke="hsl(var(--border))"
              opacity={0.25} vertical={false}
            />
            <XAxis dataKey="tenor" tick={<CustomXAxisTick />}
              axisLine={false} tickLine={false} height={35} />
            <YAxis
              tick={{ fontSize: fullWidth ? 10 : 9, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={false} tickLine={false}
              tickFormatter={(v) => `${Math.abs(v)}`} width={38}
            />
            <Tooltip content={<CustomTooltip />}
              cursor={{ fill: 'hsl(var(--muted-foreground))', opacity: 0.05 }} />
            <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1} />

            {barDefs.map((d) => (
              <Bar key={d.key} dataKey={d.key} stackId={d.sid}
                shape={makeShape(d.fill, d.stroke, d.sw, d.inset)}
                isAnimationActive={false} />
            ))}

            {/* Net EV lines */}
            <Line type="monotone" dataKey="netBase" stroke={C.netBase}
              strokeWidth={1.5} dot={{ r: 2.5, fill: C.netBase, strokeWidth: 0 }}
              activeDot={{ r: 3.5, strokeWidth: 0 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="netScenario" stroke={C.netScenario}
              strokeWidth={2} dot={{ r: 2.5, fill: C.netScenario, strokeWidth: 0 }}
              activeDot={{ r: 3.5, strokeWidth: 0 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 px-3 py-1 text-[9px] shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="flex gap-px">
            <div className="w-2 h-2 rounded-sm" style={{ background: C.baseAsset }} />
            <div className="w-2 h-2 rounded-sm" style={{ background: C.baseLiab }} />
          </div>
          <span className="text-muted-foreground">Base</span>
          <div className="flex gap-px ml-1">
            <div className="w-2 h-2 rounded-sm" style={{ background: C.scenarioAsset }} />
            <div className="w-2 h-2 rounded-sm" style={{ background: C.scenarioLiab }} />
          </div>
          <span className="text-muted-foreground">{scenarioLabel.replace(/ \(Worst\)$/, '')}</span>
        </div>
        {hasWhatIf && (
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-sm" style={{ background: C.whatIf }} />
            <span className="text-muted-foreground">What-If</span>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <svg width="14" height="8"><line x1="0" y1="4" x2="14" y2="4" stroke={C.netBase} strokeWidth="1.5" /></svg>
          <span className="text-muted-foreground">Net Base</span>
          <svg width="14" height="8"><line x1="0" y1="4" x2="14" y2="4" stroke={C.netScenario} strokeWidth="2" /></svg>
          <span className="text-muted-foreground">Net Scen.</span>
        </div>
      </div>
    </div>
  );
}
