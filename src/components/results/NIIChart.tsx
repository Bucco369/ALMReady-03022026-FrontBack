/**
 * NIIChart.tsx – Bar chart for Net Interest Income (NII) over 12 months.
 *
 * === ROLE IN THE SYSTEM ===
 * Renders a Recharts ComposedChart showing monthly interest income (assets,
 * positive bars) vs interest expense (liabilities, negative bars) with a
 * Net Interest Income (NII = income − expense) line overlay.
 * The user can switch between 7 regulatory IRRBB scenarios via popover.
 *
 * === CURRENT LIMITATIONS ===
 * - ALL DATA IS SYNTHETIC: generateRawNIIData() produces deterministic
 *   placeholder values using sin/cos functions. No real NII calculation.
 * - Unlike EVEChart, this chart does NOT integrate What-If modifications.
 *   It only reads analysisDate for calendar labels.
 * - The scenario multipliers are rough visual approximations only.
 * - Phase 1 will replace generateRawNIIData() with real monthly NII
 *   projections returned by the backend engine, broken down by income
 *   and expense components.
 */
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
import { getCalendarLabelFromMonths } from '@/lib/calendarLabels';

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

type AxisTickProps = {
  x: number;
  y: number;
  payload: { value: string | number };
};

type TooltipEntry = {
  value?: number | string;
};

type ChartTooltipProps = {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
};

// Generate raw data for NII chart
const generateRawNIIData = (scenario: string, analysisDate: Date | null) => {
  return MONTHS.map((month, index) => {
    const income = 25 + Math.sin(index * 0.4) * 8 + index * 0.5;
    const expense = 18 + Math.cos(index * 0.3) * 5 + index * 0.3;
    
    const scenarioMultiplier = scenario === 'parallel-up' ? 0.8 
      : scenario === 'parallel-down' ? -0.6 
      : scenario === 'steepener' ? (index / MONTHS.length) * 0.7
      : scenario === 'flattener' ? ((MONTHS.length - index) / MONTHS.length) * 0.6
      : scenario === 'short-up' ? (index < 4 ? 0.5 : 0.15)
      : scenario === 'short-down' ? (index < 4 ? -0.4 : -0.1)
      : scenario === 'worst' ? -0.7
      : 0;
    
    const incomeAdj = scenarioMultiplier * (3 + index * 0.3);
    const expenseAdj = scenarioMultiplier * (2 + index * 0.2);
    
    const calendarLabel = analysisDate ? getCalendarLabelFromMonths(analysisDate, month.monthsToAdd) : null;
    
    return {
      month: month.label,
      calendarLabel,
      income: income + incomeAdj,
      expense: expense + expenseAdj,
    };
  });
};

interface NIIChartProps {
  className?: string;
  fullWidth?: boolean;
  analysisDate?: Date | null;
}

export function NIIChart({ className, fullWidth = false, analysisDate }: NIIChartProps) {
  const [selectedScenario, setSelectedScenario] = useState('worst');
  const [isOpen, setIsOpen] = useState(false);
  
  // Transform data: create expenseNeg and nii
  const data = useMemo(() => {
    const rawData = generateRawNIIData(selectedScenario, analysisDate ?? null);
    return rawData.map(d => {
      const expenseNeg = -Math.abs(d.expense);
      return {
        ...d,
        expenseNeg,
        nii: d.income + expenseNeg, // income - expense
      };
    });
  }, [selectedScenario, analysisDate]);
  
  const formatValue = (value: number) => `${value.toFixed(1)}M`;

  // Custom X-axis tick with dual labels
  const CustomXAxisTick = ({ x, y, payload }: AxisTickProps) => {
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
        {dataPoint?.calendarLabel && (
          <text
            x={0}
            y={0}
            dy={22}
            textAnchor="middle"
            fill="hsl(var(--muted-foreground))"
            fontSize={fullWidth ? 8 : 7}
            opacity={0.7}
          >
            {dataPoint.calendarLabel}
          </text>
        )}
      </g>
    );
  };

  const CustomTooltip = ({ active, payload, label }: ChartTooltipProps) => {
    if (!active || !payload?.length) return null;
    const dataPoint = data.find(d => d.month === label);
    
    const income = dataPoint?.income ?? 0;
    const expense = dataPoint?.expense ?? 0;
    const nii = dataPoint?.nii ?? 0;
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">
          {label} {dataPoint?.calendarLabel && <span className="text-muted-foreground font-normal">({dataPoint.calendarLabel})</span>}
        </div>
        <div className="space-y-1">
          <div className="text-success">Interest Income (Assets): {formatValue(income)}</div>
          <div className="text-destructive">
            Interest Expense (Liabilities): {formatValue(expense)}
            <span className="text-muted-foreground ml-1">(plotted as −{expense.toFixed(1)})</span>
          </div>
          <div className="text-warning font-medium border-t border-border/50 pt-1 mt-1">
            Net Interest Income (NII): {formatValue(nii)}
          </div>
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
                <CartesianGrid 
                  strokeDasharray="3 3" 
                  stroke="hsl(var(--border))" 
                  opacity={0.5}
                />
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
                
                {/* Zero baseline */}
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                
                {/* Interest Income (Assets) - positive stack */}
                <Bar 
                  dataKey="income" 
                  name="Interest Income (Assets)"
                  stackId="main"
                  fill="hsl(var(--success))" 
                  opacity={0.8}
                  radius={[4, 4, 0, 0]}
                  barSize={fullWidth ? 22 : 16}
                />
                
                {/* Interest Expense (Liabilities) - negative stack */}
                <Bar 
                  dataKey="expenseNeg" 
                  name="Interest Expense (Liabilities)"
                  stackId="main"
                  fill="hsl(var(--destructive))" 
                  opacity={0.8}
                  radius={[0, 0, 4, 4]}
                  barSize={fullWidth ? 22 : 16}
                />
                
                {/* Net Interest Income (NII) line */}
                <Line 
                  type="monotone" 
                  dataKey="nii" 
                  name="Net Interest Income (NII)"
                  stroke="hsl(var(--primary))" 
                  strokeWidth={2}
                  dot={{ r: fullWidth ? 3.5 : 3, fill: 'hsl(var(--primary))' }}
                  activeDot={{ r: fullWidth ? 5 : 4, fill: 'hsl(var(--primary))' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-4 px-3 py-2 text-[8px] shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-success" />
              <span className="text-muted-foreground">Interest Income (Assets)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-destructive" />
              <span className="text-muted-foreground">Interest Expense (Liabilities)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-5 h-0.5 rounded bg-primary" />
              <span className="text-muted-foreground">Net Interest Income (NII)</span>
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
