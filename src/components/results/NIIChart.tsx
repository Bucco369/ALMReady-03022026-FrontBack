/**
 * NIIChart.tsx – Dual-stack bar chart for Net Interest Income (NII).
 *
 * === VISUAL DESIGN ===
 * Same architecture as EVEChart but for 12 monthly projection buckets.
 * Scenario is controlled by the parent (ResultsCard) via props.
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

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  label: `${i + 1}M`,
  monthsToAdd: i + 1,
}));

// ─── Colours ─────────────────────────────────────────────────────────────────

const C = {
  baseIncome:     '#5bb88a',
  scenarioIncome: '#3a8a62',
  baseExpense:    '#e07872',
  scenarioExpense:'#c44d48',
  whatIf:         '#daa44a',
  whatIfStroke:   '#c08e38',
  netBase:        '#6ba3c7',
  netScenario:    '#2e5f8a',
} as const;

const INSIDE_STROKE = 2.5;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function allocateWhatIfByMonth(
  modifications: any[],
  analysisDate: Date | null,
): Array<{ dI: number; dE: number }> {
  const perMonth = MONTHS.map(() => ({ dI: 0, dE: 0 }));

  modifications.forEach((mod) => {
    const sign = mod.type === 'add' ? 1 : -1;
    const notional = (mod.notional || 0) * sign;
    const rate = mod.rate || (mod.spread ? mod.spread / 10000 : 0) || 0.03;
    const monthlyInterest = notional * rate / 12;

    const key: 'dI' | 'dE' | null =
      mod.category === 'asset' ? 'dI' : mod.category === 'liability' ? 'dE' : null;
    if (!key) return;

    let matMonths: number | null = null;
    if (mod.maturityDate && analysisDate) {
      const mat = new Date(mod.maturityDate);
      matMonths =
        (mat.getFullYear() - analysisDate.getFullYear()) * 12 +
        (mat.getMonth() - analysisDate.getMonth()) +
        (mat.getDate() - analysisDate.getDate()) / 30;
      if (matMonths < 1) matMonths = 1;
    } else if (mod.maturity != null) {
      matMonths = mod.maturity * 12;
    }

    const affectedMonths = matMonths != null ? Math.min(Math.ceil(matMonths), 12) : 12;
    for (let m = 0; m < affectedMonths; m++) {
      perMonth[m][key] += monthlyInterest;
    }
  });

  return perMonth;
}

function generateNIIBaseline(scenario: string, analysisDate: Date | null) {
  const getMultiplier = (sc: string, idx: number) => {
    switch (sc) {
      case 'parallel-up':   return 0.8;
      case 'parallel-down': return -0.6;
      case 'steepener':     return (idx / 12) * 0.7;
      case 'flattener':     return ((12 - idx) / 12) * 0.6;
      case 'short-up':      return idx < 4 ? 0.5 : 0.15;
      case 'short-down':    return idx < 4 ? -0.4 : -0.1;
      default:              return 0;
    }
  };

  return MONTHS.map((month, i) => {
    const incomeBase  = 25 + Math.sin(i * 0.4) * 8 + i * 0.5;
    const expenseBase = -(18 + Math.cos(i * 0.3) * 5 + i * 0.3);
    const m = getMultiplier(scenario, i);
    return {
      month: month.label,
      calendarLabel: analysisDate
        ? getCalendarLabelFromMonths(analysisDate, month.monthsToAdd)
        : null,
      incomeBase,
      expenseBase,
      incomeScenario:  incomeBase  + m * (3 + i * 0.3),
      expenseScenario: expenseBase - m * (2 + i * 0.2),
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

function buildNiiChartData(
  scenarioId: string,
  perMonthDeltas: Array<{ dI: number; dE: number }>,
  analysisDate: Date | null,
) {
  const baselines = generateNIIBaseline(scenarioId, analysisDate);

  return baselines.map((b, i) => {
    const dA = perMonthDeltas[i].dI / 1e6;
    const dL = -perMonthDeltas[i].dE / 1e6;

    const base = decomposeStack(b.incomeBase, b.expenseBase, dA, dL);
    const scen = decomposeStack(b.incomeScenario, b.expenseScenario, dA, dL);

    return {
      month: b.month,
      calendarLabel: b.calendarLabel,
      ik_b: base.assets_kept, iri_b: base.assets_reduced_inside, iao_b: base.assets_added_outside,
      ek_b: base.liabs_kept,  eri_b: base.liabs_reduced_inside,  eao_b: base.liabs_added_outside,
      ik_s: scen.assets_kept, iri_s: scen.assets_reduced_inside, iao_s: scen.assets_added_outside,
      ek_s: scen.liabs_kept,  eri_s: scen.liabs_reduced_inside,  eao_s: scen.liabs_added_outside,
      netBase:     (b.incomeBase     + dA) + (b.expenseBase     + dL),
      netScenario: (b.incomeScenario + dA) + (b.expenseScenario + dL),
      _incomeBase: b.incomeBase, _expenseBase: b.expenseBase,
      _incomeScenario: b.incomeScenario, _expenseScenario: b.expenseScenario,
      _dI: dA, _dE: dL,
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

interface NIIChartProps {
  className?: string;
  fullWidth?: boolean;
  analysisDate?: Date | null;
  selectedScenario: string;
  scenarioLabel: string;
}

export function NIIChart({ className, fullWidth = false, analysisDate, selectedScenario, scenarioLabel }: NIIChartProps) {
  const { modifications } = useWhatIf();

  const perMonthDeltas = useMemo(
    () => allocateWhatIfByMonth(modifications, analysisDate ?? null),
    [modifications, analysisDate],
  );
  const hasWhatIf = modifications.length > 0;

  const chartData = useMemo(
    () => buildNiiChartData(selectedScenario, perMonthDeltas, analysisDate ?? null),
    [selectedScenario, perMonthDeltas, analysisDate],
  );

  const CustomXAxisTick = useCallback(({ x, y, payload }: any) => {
    const dp = chartData.find((d) => d.month === payload.value);
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
    const dp = chartData.find((d) => d.month === label);
    if (!dp) return null;

    const sections = [
      { tag: 'Base', inc: dp._incomeBase, exp: dp._expenseBase, net: dp.netBase, color: C.netBase },
      { tag: scenarioLabel || 'Scenario', inc: dp._incomeScenario, exp: dp._expenseScenario, net: dp.netScenario, color: C.netScenario },
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
              <span className="text-muted-foreground">Income:</span>
              <span className="text-right font-mono">{fmtVal(s.inc)}</span>
              <span className="text-muted-foreground">Expense:</span>
              <span className="text-right font-mono">{fmtVal(Math.abs(s.exp))}</span>
              {hasWhatIf && (
                <>
                  <span style={{ color: C.whatIf }}>Δ Income:</span>
                  <span className="text-right font-mono" style={{ color: C.whatIf }}>{fmtDelta(dp._dI)}</span>
                  <span style={{ color: C.whatIf }}>Δ Expense:</span>
                  <span className="text-right font-mono" style={{ color: C.whatIf }}>{fmtDelta(dp._dE)}</span>
                </>
              )}
              <span className="font-medium" style={{ color: s.color }}>Net NII:</span>
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
    { key: 'ik_b',  sid: 'base',     fill: C.baseIncome,      stroke: C.baseIncome,      sw: 0, inset: false },
    { key: 'iri_b', sid: 'base',     fill: C.whatIf,           stroke: C.baseIncome,      sw: INSIDE_STROKE, inset: true },
    { key: 'iao_b', sid: 'base',     fill: C.whatIf,           stroke: C.whatIfStroke,     sw: 0, inset: false },
    { key: 'ek_b',  sid: 'base',     fill: C.baseExpense,      stroke: C.baseExpense,     sw: 0, inset: false },
    { key: 'eri_b', sid: 'base',     fill: C.whatIf,           stroke: C.baseExpense,     sw: INSIDE_STROKE, inset: true },
    { key: 'eao_b', sid: 'base',     fill: C.whatIf,           stroke: C.whatIfStroke,     sw: 0, inset: false },
    { key: 'ik_s',  sid: 'scenario', fill: C.scenarioIncome,   stroke: C.scenarioIncome,  sw: 0, inset: false },
    { key: 'iri_s', sid: 'scenario', fill: C.whatIf,            stroke: C.scenarioIncome,  sw: INSIDE_STROKE, inset: true },
    { key: 'iao_s', sid: 'scenario', fill: C.whatIf,            stroke: C.whatIfStroke,     sw: 0, inset: false },
    { key: 'ek_s',  sid: 'scenario', fill: C.scenarioExpense,  stroke: C.scenarioExpense, sw: 0, inset: false },
    { key: 'eri_s', sid: 'scenario', fill: C.whatIf,            stroke: C.scenarioExpense, sw: INSIDE_STROKE, inset: true },
    { key: 'eao_s', sid: 'scenario', fill: C.whatIf,            stroke: C.whatIfStroke,     sw: 0, inset: false },
  ];

  return (
    <div className={`h-full flex flex-col ${className ?? ''}`}>
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50">
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          Net Interest Income (NII)
        </span>
        <span className="text-[9px] text-muted-foreground">
          {scenarioLabel}
          {hasWhatIf && <span className="ml-1 text-warning">(+What-If)</span>}
        </span>
      </div>

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
            <XAxis dataKey="month" tick={<CustomXAxisTick />}
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

            <Line type="monotone" dataKey="netBase" stroke={C.netBase}
              strokeWidth={1.5} dot={{ r: 2.5, fill: C.netBase, strokeWidth: 0 }}
              activeDot={{ r: 3.5, strokeWidth: 0 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="netScenario" stroke={C.netScenario}
              strokeWidth={2} dot={{ r: 2.5, fill: C.netScenario, strokeWidth: 0 }}
              activeDot={{ r: 3.5, strokeWidth: 0 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center justify-center gap-4 px-3 py-1 text-[9px] shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="flex gap-px">
            <div className="w-2 h-2 rounded-sm" style={{ background: C.baseIncome }} />
            <div className="w-2 h-2 rounded-sm" style={{ background: C.baseExpense }} />
          </div>
          <span className="text-muted-foreground">Base</span>
          <div className="flex gap-px ml-1">
            <div className="w-2 h-2 rounded-sm" style={{ background: C.scenarioIncome }} />
            <div className="w-2 h-2 rounded-sm" style={{ background: C.scenarioExpense }} />
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
