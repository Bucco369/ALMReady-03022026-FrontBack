import React, { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { NMD_BUCKET_DISTRIBUTION } from './BehaviouralContext';

interface NMDCashflowChartProps {
  coreProportion: number;
  coreAverageMaturity: number;
}

export function NMDCashflowChart({
  coreProportion,
  coreAverageMaturity,
}: NMDCashflowChartProps) {
  // Calculate chart data based on core proportion
  const chartData = useMemo(() => {
    const nonCorePct = 100 - coreProportion;
    const coreBalance = coreProportion;

    // O/N bucket = non-core
    const data = [
      {
        bucket: 'O/N',
        value: nonCorePct,
        isNonCore: true,
      },
    ];

    // Core buckets (1Y to 8Y)
    const buckets = ['1Y', '2Y', '3Y', '4Y', '5Y', '6Y', '7Y', '8Y'] as const;
    buckets.forEach((bucket) => {
      const bucketPct = NMD_BUCKET_DISTRIBUTION[bucket];
      // Convert from % of core to % of total
      const valueOfTotal = (bucketPct / 100) * coreBalance;
      data.push({
        bucket,
        value: valueOfTotal,
        isNonCore: false,
      });
    });

    return data;
  }, [coreProportion]);

  return (
    <div className="rounded-md border border-border/50 bg-background p-3">
      <h4 className="text-xs font-medium mb-2">Behavioural cash-flow profile (NMDs)</h4>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="bucket"
              tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={{ stroke: 'hsl(var(--border))' }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(value) => `${value.toFixed(0)}%`}
              tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={{ stroke: 'hsl(var(--border))' }}
              tickLine={false}
              domain={[0, 'auto']}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const data = payload[0].payload;
                return (
                  <div className="rounded-md border bg-popover px-2 py-1.5 text-xs shadow-md">
                    <div className="font-medium">{data.bucket}</div>
                    <div className="text-muted-foreground">
                      {data.isNonCore ? 'Non-core' : 'Core'}: {data.value.toFixed(2)}%
                    </div>
                  </div>
                );
              }}
            />
            <Bar dataKey="value" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.isNonCore ? 'hsl(var(--muted-foreground))' : 'hsl(var(--primary))'}
                  opacity={entry.isNonCore ? 0.5 : 0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 mt-2 text-[10px]">
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-muted-foreground/50" />
          <span className="text-muted-foreground">Non-core (O/N)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-primary/80" />
          <span className="text-muted-foreground">Core (1Y–8Y)</span>
        </div>
      </div>
    </div>
  );
}
