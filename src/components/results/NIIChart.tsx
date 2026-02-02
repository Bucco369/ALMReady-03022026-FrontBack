import React, { useState, useMemo } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
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

// Generate placeholder data for NII chart (lines only)
const generateNIIData = (scenario: string, analysisDate: Date | null) => {
  return MONTHS.map((month, index) => {
    // Base values - Interest Income (what bank earns from assets)
    const interestIncome = 25 + Math.sin(index * 0.4) * 8 + index * 0.5;
    // Interest Expense (what bank pays on liabilities)
    const interestExpense = 18 + Math.cos(index * 0.3) * 5 + index * 0.3;
    
    // Scenario adjustments
    const scenarioMultiplier = scenario === 'parallel-up' ? 0.8 
      : scenario === 'parallel-down' ? -0.6 
      : scenario === 'steepener' ? (index / MONTHS.length) * 0.7
      : scenario === 'flattener' ? ((MONTHS.length - index) / MONTHS.length) * 0.6
      : scenario === 'short-up' ? (index < 4 ? 0.5 : 0.15)
      : scenario === 'short-down' ? (index < 4 ? -0.4 : -0.1)
      : scenario === 'worst' ? -0.7
      : 0;
    
    const incomeScenarioAdj = scenarioMultiplier * (3 + index * 0.3);
    const expenseScenarioAdj = scenarioMultiplier * (2 + index * 0.2);
    
    // Final values for lines
    const incomeTotal = interestIncome + incomeScenarioAdj;
    const expenseTotal = interestExpense + expenseScenarioAdj;
    
    // Net Interest Income = Interest Income (Assets) - Interest Expense (Liabilities)
    // This is the TRUE NII margin, mechanically derived
    const netNII = incomeTotal - expenseTotal;

    // Calendar label for this month (only if analysisDate is set)
    const calendarLabel = analysisDate ? getCalendarLabel(analysisDate, month.monthsToAdd) : null;
    
    return {
      month: month.label,
      calendarLabel,
      interestIncome: incomeTotal,
      interestExpense: expenseTotal,
      netNII,
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
  
  const data = useMemo(
    () => generateNIIData(selectedScenario, analysisDate ?? null),
    [selectedScenario, analysisDate]
  );
  
  const formatValue = (value: number) => {
    return `${value.toFixed(1)}M`;
  };

  // Custom X-axis tick with dual labels (only show calendar label if analysisDate is set)
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

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const dataPoint = data.find(d => d.month === label);
    
    const interestIncome = payload.find((p: any) => p.dataKey === 'interestIncome')?.value || 0;
    const interestExpense = payload.find((p: any) => p.dataKey === 'interestExpense')?.value || 0;
    // Calculate NII as the difference to ensure accuracy
    const calculatedNII = interestIncome - interestExpense;
    
    return (
      <div className="rounded-lg border border-border/50 bg-background px-3 py-2 text-xs shadow-xl">
        <div className="font-medium text-foreground mb-1.5">
          {label} {dataPoint?.calendarLabel && <span className="text-muted-foreground font-normal">({dataPoint.calendarLabel})</span>}
        </div>
        <div className="space-y-1">
          <div className="text-success">Interest Income (Assets): {formatValue(interestIncome)}</div>
          <div className="text-destructive">Interest Expense (Liabilities): {formatValue(interestExpense)}</div>
          <div className="text-warning font-medium">Net Interest Income (NII): {formatValue(calculatedNII)}</div>
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
                  tickFormatter={(v) => `${v}`}
                  width={40}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                
                {/* Interest Income (Assets) line - Green */}
                <Line 
                  type="monotone" 
                  dataKey="interestIncome" 
                  name="Interest Income (Assets)"
                  stroke="hsl(var(--success))" 
                  strokeWidth={2}
                  dot={{ r: fullWidth ? 3 : 2, fill: 'hsl(var(--success))' }}
                  activeDot={{ r: fullWidth ? 5 : 4 }}
                />
                
                {/* Interest Expense (Liabilities) line - Red */}
                <Line 
                  type="monotone" 
                  dataKey="interestExpense" 
                  name="Interest Expense (Liabilities)"
                  stroke="hsl(var(--destructive))" 
                  strokeWidth={2}
                  dot={{ r: fullWidth ? 3 : 2, fill: 'hsl(var(--destructive))' }}
                  activeDot={{ r: fullWidth ? 5 : 4 }}
                />
                
                {/* Net Interest Income (NII) line - Orange */}
                <Line 
                  type="monotone" 
                  dataKey="netNII" 
                  name="Net Interest Income (NII)"
                  stroke="hsl(var(--warning))" 
                  strokeWidth={2.5}
                  dot={{ r: fullWidth ? 4 : 3, fill: 'hsl(var(--warning))' }}
                  activeDot={{ r: fullWidth ? 6 : 5 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-4 px-3 py-2 text-[8px] shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-0.5 rounded bg-success" />
              <span className="text-muted-foreground">Interest Income (Assets)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-0.5 rounded bg-destructive" />
              <span className="text-muted-foreground">Interest Expense (Liabilities)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-5 h-0.5 rounded bg-warning" />
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