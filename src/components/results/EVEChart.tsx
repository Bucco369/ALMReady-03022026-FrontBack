import React, { useState, useMemo } from 'react';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { addMonths, addYears, format } from 'date-fns';

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

const SCENARIOS = [
  { id: 'worst', label: 'Worst Case' },
  { id: 'parallel-up', label: 'Parallel Up' },
  { id: 'parallel-down', label: 'Parallel Down' },
  { id: 'steepener', label: 'Steepener' },
  { id: 'flattener', label: 'Flattener' },
  { id: 'short-up', label: 'Short Up' },
  { id: 'short-down', label: 'Short Down' },
];

// Compute What-If impact from modifications
function computeWhatIfImpact(modifications: any[]) {
  let assetDelta = 0;
  let liabilityDelta = 0;

  modifications.forEach((mod) => {
    const multiplier = mod.type === 'add' ? 1 : -1;
    const notional = (mod.notional || 0) * multiplier;
    
    if (mod.category === 'asset') {
      assetDelta += notional;
    } else if (mod.category === 'liability') {
      liabilityDelta += notional;
    }
  });

  return { assetDelta, liabilityDelta };
}

// Generate calendar label from tenor and analysis date
function getCalendarLabel(analysisDate: Date, monthsToAdd: number): string {
  const targetDate = addMonths(analysisDate, monthsToAdd);
  return format(targetDate, 'MMM yyyy');
}

// Generate placeholder data for EVE chart with What-If support
const generateEVEData = (
  scenario: string, 
  whatIfImpact: { assetDelta: number; liabilityDelta: number },
  analysisDate: Date
) => {
  // Normalize what-if deltas to chart scale (convert from actual values to display units)
  const assetWhatIfNormalized = whatIfImpact.assetDelta / 1e7; // Scale to M units
  const liabilityWhatIfNormalized = whatIfImpact.liabilityDelta / 1e7;

  return TENORS.map((tenor, index) => {
    // Base values - assets positive, liabilities negative
    const assetBase = 80 + Math.sin(index * 0.5) * 30 + index * 5;
    const liabilityBase = -(70 + Math.cos(index * 0.4) * 25 + index * 4);
    
    // Scenario adjustments vary by scenario
    const scenarioMultiplier = scenario === 'parallel-up' ? 1.2 
      : scenario === 'parallel-down' ? -0.8 
      : scenario === 'steepener' ? (index / TENORS.length) * 1.5 
      : scenario === 'flattener' ? ((TENORS.length - index) / TENORS.length) * 1.2
      : scenario === 'short-up' ? (index < 4 ? 0.8 : 0.2)
      : scenario === 'short-down' ? (index < 4 ? -0.6 : -0.1)
      : scenario === 'worst' ? -1.1
      : 0;
    
    const assetScenario = scenarioMultiplier * (10 + index * 2);
    const liabilityScenario = -scenarioMultiplier * (8 + index * 1.5);
    
    // What-If position impact (distributed across tenors with some variation)
    // Positive for buys, negative for sells
    const tenorWeight = 1 + Math.sin(index * 0.3) * 0.3; // Slight variation
    const assetNewPosition = assetWhatIfNormalized * tenorWeight;
    const liabilityNewPosition = -Math.abs(liabilityWhatIfNormalized) * tenorWeight; // Liabilities are negative
    
    // Adjust liability new position sign based on what-if direction
    const adjustedLiabilityNewPosition = whatIfImpact.liabilityDelta >= 0 
      ? liabilityNewPosition 
      : Math.abs(liabilityWhatIfNormalized) * tenorWeight; // Sell reduces liability (positive adjustment)
    
    // Net EV = total assets + total liabilities (liabilityBase is already negative)
    // Include What-If impact in Net EV
    const totalAssets = assetBase + Math.abs(assetScenario) + assetNewPosition;
    const totalLiabilities = liabilityBase + liabilityScenario + adjustedLiabilityNewPosition;
    const netEV = totalAssets + totalLiabilities;

    // Calendar label for this tenor
    const calendarLabel = getCalendarLabel(analysisDate, tenor.months);
    
    return {
      tenor: tenor.label,
      calendarLabel,
      assetBase,
      assetScenario: Math.abs(assetScenario),
      assetNewPosition: Math.max(0, assetNewPosition), // Only show positive for stacking
      assetNewPositionNeg: Math.min(0, assetNewPosition), // Negative reduction
      liabilityBase,
      liabilityScenario: -Math.abs(liabilityScenario),
      liabilityNewPosition: Math.min(0, adjustedLiabilityNewPosition),
      liabilityNewPositionPos: Math.max(0, adjustedLiabilityNewPosition),
      netEV,
    };
  });
};

interface EVEChartProps {
  className?: string;
  fullWidth?: boolean;
  analysisDate?: Date;
}

export function EVEChart({ className, fullWidth = false, analysisDate = new Date() }: EVEChartProps) {
  const [selectedScenario, setSelectedScenario] = useState('worst');
  const [isOpen, setIsOpen] = useState(false);
  const { modifications } = useWhatIf();
  
  // Compute What-If impact from context
  const whatIfImpact = useMemo(() => computeWhatIfImpact(modifications), [modifications]);
  const hasWhatIf = modifications.length > 0;
  
  const data = useMemo(
    () => generateEVEData(selectedScenario, whatIfImpact, analysisDate), 
    [selectedScenario, whatIfImpact, analysisDate]
  );
  
  const formatValue = (value: number) => {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(0)}B`;
    return `${value.toFixed(0)}M`;
  };

  // Custom X-axis tick with dual labels
  const CustomXAxisTick = ({ x, y, payload }: any) => {
    const dataPoint = data.find(d => d.tenor === payload.value);
    return (
      <g transform={`translate(${x},${y})`}>
        <text
          x={0}
          y={0}
          dy={10}
          textAnchor="middle"
          fill="hsl(var(--muted-foreground))"
          fontSize={fullWidth ? 10 : 9}
          fontWeight={500}
        >
          {payload.value}
        </text>
        <text
          x={0}
          y={0}
          dy={22}
          textAnchor="middle"
          fill="hsl(var(--muted-foreground))"
          fontSize={fullWidth ? 8 : 7}
          opacity={0.7}
        >
          {dataPoint?.calendarLabel}
        </text>
      </g>
    );
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    
    const assetBase = payload.find((p: any) => p.dataKey === 'assetBase')?.value || 0;
    const assetNew = payload.find((p: any) => p.dataKey === 'assetNewPosition')?.value || 0;
    const assetNewNeg = payload.find((p: any) => p.dataKey === 'assetNewPositionNeg')?.value || 0;
    const liabilityBase = payload.find((p: any) => p.dataKey === 'liabilityBase')?.value || 0;
    const liabilityNew = payload.find((p: any) => p.dataKey === 'liabilityNewPosition')?.value || 0;
    const liabilityNewPos = payload.find((p: any) => p.dataKey === 'liabilityNewPositionPos')?.value || 0;
    const netEV = payload.find((p: any) => p.dataKey === 'netEV')?.value || 0;
    const dataPoint = data.find(d => d.tenor === label);
    
    const totalAssetWhatIf = assetNew + assetNewNeg;
    const totalLiabilityWhatIf = liabilityNew + liabilityNewPos;
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">
          {label} <span className="text-muted-foreground font-normal">({dataPoint?.calendarLabel})</span>
        </div>
        <div className="space-y-1">
          <div className="text-success">Assets: {formatValue(assetBase)}</div>
          <div className="text-destructive">Liabilities: {formatValue(Math.abs(liabilityBase))}</div>
          {hasWhatIf && (
            <>
              <div className={totalAssetWhatIf >= 0 ? 'text-success' : 'text-destructive'}>
                Asset Δ: {totalAssetWhatIf >= 0 ? '+' : ''}{formatValue(totalAssetWhatIf)}
              </div>
              <div className={totalLiabilityWhatIf <= 0 ? 'text-destructive' : 'text-success'}>
                Liability Δ: {totalLiabilityWhatIf >= 0 ? '+' : ''}{formatValue(totalLiabilityWhatIf)}
              </div>
            </>
          )}
          <div className="text-primary font-medium">Net EV: {formatValue(netEV)}</div>
        </div>
      </div>
    );
  };

  const chartHeight = fullWidth ? 'h-[calc(100%-60px)]' : 'h-[180px]';

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <div className={`cursor-pointer hover:bg-muted/30 rounded-lg transition-colors h-full flex flex-col ${className}`}>
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50">
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
              Economic Value (EVE)
            </span>
            <span className="text-[9px] text-muted-foreground">
              {SCENARIOS.find(s => s.id === selectedScenario)?.label}
              {hasWhatIf && <span className="ml-1 text-warning">(+What-If)</span>}
              {' '}• Click to change
            </span>
          </div>
          <div className={`flex-1 px-2 ${fullWidth ? 'min-h-0' : chartHeight}`}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={data}
                margin={{ top: 10, right: 15, left: 0, bottom: 25 }}
                stackOffset="sign"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis 
                  dataKey="tenor" 
                  tick={<CustomXAxisTick />}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickLine={false}
                  height={35}
                />
                <YAxis 
                  tick={{ fontSize: fullWidth ? 10 : 9, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickLine={false}
                  tickFormatter={(v) => `${Math.abs(v)}`}
                  width={40}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                
                {/* Asset bars (positive, stacked) */}
                <Bar dataKey="assetBase" stackId="main" fill="hsl(var(--success))" opacity={0.8} />
                <Bar dataKey="assetScenario" stackId="main" fill="hsl(var(--success))" opacity={0.5} />
                <Bar dataKey="assetNewPosition" stackId="main" fill="hsl(var(--success))" opacity={0.3} />
                
                {/* Asset reduction from sell (shown in same stack) */}
                {hasWhatIf && whatIfImpact.assetDelta < 0 && (
                  <Bar dataKey="assetNewPositionNeg" stackId="main" fill="hsl(var(--warning))" opacity={0.6} />
                )}
                
                {/* Liability bars (negative, same stack for vertical alignment) */}
                <Bar dataKey="liabilityBase" stackId="main" fill="hsl(var(--destructive))" opacity={0.8} />
                <Bar dataKey="liabilityScenario" stackId="main" fill="hsl(var(--destructive))" opacity={0.5} />
                <Bar dataKey="liabilityNewPosition" stackId="main" fill="hsl(var(--destructive))" opacity={0.3} />
                
                {/* Liability reduction from sell (positive effect) */}
                {hasWhatIf && whatIfImpact.liabilityDelta < 0 && (
                  <Bar dataKey="liabilityNewPositionPos" stackId="main" fill="hsl(var(--warning))" opacity={0.6} />
                )}
                
                {/* Net EV line */}
                <Line 
                  type="monotone" 
                  dataKey="netEV" 
                  stroke="hsl(var(--primary))" 
                  strokeWidth={2}
                  dot={{ r: fullWidth ? 4 : 3, fill: 'hsl(var(--primary))' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-4 px-3 py-2 text-[9px] shrink-0 flex-wrap">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5">
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-80" />
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-50" />
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-30" />
              </div>
              <span className="text-muted-foreground">Assets</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5">
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-80" />
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-50" />
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-30" />
              </div>
              <span className="text-muted-foreground">Liabilities</span>
            </div>
            {hasWhatIf && (
              <div className="flex items-center gap-1">
                <div className="w-2.5 h-2.5 rounded-sm bg-warning opacity-60" />
                <span className="text-muted-foreground">What-If Δ</span>
              </div>
            )}
            <div className="flex items-center gap-1">
              <div className="w-5 h-0.5 rounded bg-primary" />
              <span className="text-muted-foreground">Net EV</span>
            </div>
          </div>
        </div>
      </PopoverTrigger>
      
      <PopoverContent className="w-56" align="start">
        <div className="space-y-3">
          <div className="text-xs font-medium text-foreground">Select Scenario</div>
          <RadioGroup value={selectedScenario} onValueChange={setSelectedScenario}>
            {SCENARIOS.map((scenario) => (
              <div key={scenario.id} className="flex items-center space-x-2">
                <RadioGroupItem value={scenario.id} id={`eve-${scenario.id}`} />
                <Label htmlFor={`eve-${scenario.id}`} className="text-xs cursor-pointer">
                  {scenario.label}
                </Label>
              </div>
            ))}
          </RadioGroup>
        </div>
      </PopoverContent>
    </Popover>
  );
}
