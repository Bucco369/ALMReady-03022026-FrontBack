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

const TENORS = ['1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '15Y', '20Y', '30Y'];

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

// Generate placeholder data for EVE chart with What-If support
const generateEVEData = (
  scenario: string, 
  whatIfImpact: { assetDelta: number; liabilityDelta: number }
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
    
    return {
      tenor,
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
}

export function EVEChart({ className, fullWidth = false }: EVEChartProps) {
  const [selectedScenario, setSelectedScenario] = useState('worst');
  const [isOpen, setIsOpen] = useState(false);
  const { modifications } = useWhatIf();
  
  // Compute What-If impact from context
  const whatIfImpact = useMemo(() => computeWhatIfImpact(modifications), [modifications]);
  const hasWhatIf = modifications.length > 0;
  
  const data = useMemo(
    () => generateEVEData(selectedScenario, whatIfImpact), 
    [selectedScenario, whatIfImpact]
  );
  
  const formatValue = (value: number) => {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(0)}B`;
    return `${value.toFixed(0)}M`;
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
    
    const totalAssetWhatIf = assetNew + assetNewNeg;
    const totalLiabilityWhatIf = liabilityNew + liabilityNewPos;
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">{label}</div>
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
                margin={{ top: 10, right: 15, left: 0, bottom: 5 }}
                stackOffset="sign"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis 
                  dataKey="tenor" 
                  tick={{ fontSize: fullWidth ? 10 : 9, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickLine={false}
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
                
                {/* Asset columns (positive) */}
                <Bar dataKey="assetBase" stackId="assets" fill="hsl(var(--success))" opacity={0.8} />
                <Bar dataKey="assetScenario" stackId="assets" fill="hsl(var(--success))" opacity={0.5} />
                <Bar dataKey="assetNewPosition" stackId="assets" fill="hsl(var(--success))" opacity={0.3} />
                
                {/* Asset reduction from sell (shown separately) */}
                {hasWhatIf && whatIfImpact.assetDelta < 0 && (
                  <Bar dataKey="assetNewPositionNeg" stackId="assets" fill="hsl(var(--warning))" opacity={0.6} />
                )}
                
                {/* Liability columns (negative) */}
                <Bar dataKey="liabilityBase" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.8} />
                <Bar dataKey="liabilityScenario" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.5} />
                <Bar dataKey="liabilityNewPosition" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.3} />
                
                {/* Liability reduction from sell (positive effect) */}
                {hasWhatIf && whatIfImpact.liabilityDelta < 0 && (
                  <Bar dataKey="liabilityNewPositionPos" stackId="liabilities" fill="hsl(var(--warning))" opacity={0.6} />
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
