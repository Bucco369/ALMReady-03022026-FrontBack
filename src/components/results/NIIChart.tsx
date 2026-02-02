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
import { addMonths, format } from 'date-fns';

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  label: `${i + 1}M`,
  monthsToAdd: i + 1,
}));

const SCENARIOS = [
  { id: 'worst', label: 'Worst Case' },
  { id: 'parallel-up', label: 'Parallel Up' },
  { id: 'parallel-down', label: 'Parallel Down' },
  { id: 'steepener', label: 'Steepener' },
  { id: 'flattener', label: 'Flattener' },
  { id: 'short-up', label: 'Short Up' },
  { id: 'short-down', label: 'Short Down' },
];

// Generate calendar label from month offset and analysis date
function getCalendarLabel(analysisDate: Date, monthsToAdd: number): string {
  const targetDate = addMonths(analysisDate, monthsToAdd);
  return format(targetDate, 'MMM yyyy');
}

// Generate placeholder data for NII chart
const generateNIIData = (scenario: string, analysisDate: Date) => {
  return MONTHS.map((month, index) => {
    // Base values - asset margin positive, liability margin negative
    const assetBase = 25 + Math.sin(index * 0.4) * 8 + index * 0.5;
    const liabilityBase = -(18 + Math.cos(index * 0.3) * 5 + index * 0.3);
    
    // Scenario adjustments
    const scenarioMultiplier = scenario === 'parallel-up' ? 0.8 
      : scenario === 'parallel-down' ? -0.6 
      : scenario === 'steepener' ? (index / MONTHS.length) * 0.7
      : scenario === 'flattener' ? ((MONTHS.length - index) / MONTHS.length) * 0.6
      : scenario === 'short-up' ? (index < 4 ? 0.5 : 0.15)
      : scenario === 'short-down' ? (index < 4 ? -0.4 : -0.1)
      : scenario === 'worst' ? -0.7
      : 0;
    
    const assetScenario = scenarioMultiplier * (3 + index * 0.3);
    const liabilityScenario = -scenarioMultiplier * (2 + index * 0.2);
    
    // New position impact
    const assetNewPosition = 1.5 + Math.random() * 2;
    const liabilityNewPosition = -(1 + Math.random() * 1.5);
    
    // Net NII = asset margin - liability margin (base)
    const netNII = assetBase + liabilityBase;

    // Calendar label for this month
    const calendarLabel = getCalendarLabel(analysisDate, month.monthsToAdd);
    
    return {
      month: month.label,
      calendarLabel,
      assetBase,
      assetScenario: Math.abs(assetScenario),
      assetNewPosition,
      liabilityBase,
      liabilityScenario: -Math.abs(liabilityScenario),
      liabilityNewPosition,
      netNII,
    };
  });
};

interface NIIChartProps {
  className?: string;
  fullWidth?: boolean;
  analysisDate?: Date;
}

export function NIIChart({ className, fullWidth = false, analysisDate = new Date() }: NIIChartProps) {
  const [selectedScenario, setSelectedScenario] = useState('worst');
  const [isOpen, setIsOpen] = useState(false);
  
  const data = useMemo(
    () => generateNIIData(selectedScenario, analysisDate),
    [selectedScenario, analysisDate]
  );
  
  const formatValue = (value: number) => {
    return `${value.toFixed(1)}M`;
  };

  // Custom X-axis tick with dual labels
  const CustomXAxisTick = ({ x, y, payload }: any) => {
    const dataPoint = data.find(d => d.month === payload.value);
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
    const dataPoint = data.find(d => d.month === label);
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">
          {label} <span className="text-muted-foreground font-normal">({dataPoint?.calendarLabel})</span>
        </div>
        <div className="space-y-1">
          <div className="text-success">Asset Margin: {formatValue(payload.find((p: any) => p.dataKey === 'assetBase')?.value || 0)}</div>
          <div className="text-destructive">Liability Margin: {formatValue(Math.abs(payload.find((p: any) => p.dataKey === 'liabilityBase')?.value || 0))}</div>
          <div className="text-primary font-medium">Net NII: {formatValue(payload.find((p: any) => p.dataKey === 'netNII')?.value || 0)}</div>
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
              Net Interest Income (NII)
            </span>
            <span className="text-[9px] text-muted-foreground">
              {SCENARIOS.find(s => s.id === selectedScenario)?.label} • Click to change
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
                  dataKey="month" 
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
                
                {/* Liability bars (negative, same stack for vertical alignment) */}
                <Bar dataKey="liabilityBase" stackId="main" fill="hsl(var(--destructive))" opacity={0.8} />
                <Bar dataKey="liabilityScenario" stackId="main" fill="hsl(var(--destructive))" opacity={0.5} />
                <Bar dataKey="liabilityNewPosition" stackId="main" fill="hsl(var(--destructive))" opacity={0.3} />
                
                {/* Net NII line */}
                <Line 
                  type="monotone" 
                  dataKey="netNII" 
                  stroke="hsl(var(--primary))" 
                  strokeWidth={2}
                  dot={{ r: fullWidth ? 4 : 3, fill: 'hsl(var(--primary))' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-6 px-3 py-2 text-[9px] shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5">
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-80" />
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-50" />
                <div className="w-2.5 h-2.5 rounded-sm bg-success opacity-30" />
              </div>
              <span className="text-muted-foreground">Asset Margin (Base / Scenario / New)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5">
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-80" />
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-50" />
                <div className="w-2.5 h-2.5 rounded-sm bg-destructive opacity-30" />
              </div>
              <span className="text-muted-foreground">Liability Margin (Base / Scenario / New)</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-5 h-0.5 rounded bg-primary" />
              <span className="text-muted-foreground">Net NII</span>
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
                <RadioGroupItem value={scenario.id} id={`nii-${scenario.id}`} />
                <Label htmlFor={`nii-${scenario.id}`} className="text-xs cursor-pointer">
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
