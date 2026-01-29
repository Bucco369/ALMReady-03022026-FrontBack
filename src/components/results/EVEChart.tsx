import React, { useState } from 'react';
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
  Cell,
} from 'recharts';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';

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

// Generate placeholder data for EVE chart
const generateEVEData = (scenario: string) => {
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
    
    // New position impact (smaller, illustrative)
    const assetNewPosition = 5 + Math.random() * 8;
    const liabilityNewPosition = -(4 + Math.random() * 6);
    
    // Net EV = total assets - total liabilities (for base)
    const netEV = assetBase + liabilityBase; // liabilityBase is already negative
    
    return {
      tenor,
      assetBase,
      assetScenario: Math.abs(assetScenario),
      assetNewPosition,
      liabilityBase,
      liabilityScenario: -Math.abs(liabilityScenario),
      liabilityNewPosition,
      netEV,
    };
  });
};

interface EVEChartProps {
  className?: string;
}

export function EVEChart({ className }: EVEChartProps) {
  const [selectedScenario, setSelectedScenario] = useState('worst');
  const [isOpen, setIsOpen] = useState(false);
  
  const data = generateEVEData(selectedScenario);
  
  const formatValue = (value: number) => {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(0)}B`;
    return `${value.toFixed(0)}M`;
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">{label}</div>
        <div className="space-y-1">
          <div className="text-success">Assets: {formatValue(payload.find((p: any) => p.dataKey === 'assetBase')?.value || 0)}</div>
          <div className="text-destructive">Liabilities: {formatValue(Math.abs(payload.find((p: any) => p.dataKey === 'liabilityBase')?.value || 0))}</div>
          <div className="text-primary font-medium">Net EV: {formatValue(payload.find((p: any) => p.dataKey === 'netEV')?.value || 0)}</div>
        </div>
      </div>
    );
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <div className={`cursor-pointer hover:bg-muted/30 rounded-lg transition-colors ${className}`}>
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50">
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
              Economic Value (EVE)
            </span>
            <span className="text-[9px] text-muted-foreground">
              {SCENARIOS.find(s => s.id === selectedScenario)?.label}
            </span>
          </div>
          <div className="h-[180px] px-2">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={data}
                margin={{ top: 10, right: 10, left: -10, bottom: 5 }}
                stackOffset="sign"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis 
                  dataKey="tenor" 
                  tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickLine={false}
                />
                <YAxis 
                  tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickLine={false}
                  tickFormatter={(v) => `${v > 0 ? '' : ''}${Math.abs(v)}`}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                
                {/* Asset columns (positive) */}
                <Bar dataKey="assetBase" stackId="assets" fill="hsl(var(--success))" opacity={0.8} />
                <Bar dataKey="assetScenario" stackId="assets" fill="hsl(var(--success))" opacity={0.5} />
                <Bar dataKey="assetNewPosition" stackId="assets" fill="hsl(var(--success))" opacity={0.3} />
                
                {/* Liability columns (negative) */}
                <Bar dataKey="liabilityBase" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.8} />
                <Bar dataKey="liabilityScenario" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.5} />
                <Bar dataKey="liabilityNewPosition" stackId="liabilities" fill="hsl(var(--destructive))" opacity={0.3} />
                
                {/* Net EV line */}
                <Line 
                  type="monotone" 
                  dataKey="netEV" 
                  stroke="hsl(var(--primary))" 
                  strokeWidth={2}
                  dot={{ r: 3, fill: 'hsl(var(--primary))' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-4 px-3 py-1.5 text-[9px]">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-sm bg-success opacity-80" />
              <span className="text-muted-foreground">Assets</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-sm bg-destructive opacity-80" />
              <span className="text-muted-foreground">Liabilities</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-4 h-0.5 rounded bg-primary" />
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
