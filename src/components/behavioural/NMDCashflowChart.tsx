/**
 * NMDCashflowChart.tsx – Bar chart showing NMD maturity distribution across
 * the 19 EBA regulatory time buckets. Updates in real-time as the user edits
 * bucket weights in the modal.
 */
import { useMemo } from 'react';
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
import { NMD_BUCKETS } from './BehaviouralContext';

interface NMDCashflowChartProps {
  distribution: Record<string, number>; // bucket_id -> % of total
  nonCorePct: number;                   // auto-computed O/N bucket value
}

export function NMDCashflowChart({ distribution, nonCorePct }: NMDCashflowChartProps) {
  const chartData = useMemo(() => {
    return NMD_BUCKETS.map((b) => ({
      bucket: b.label,
      value: b.id === 'ON' ? nonCorePct : (distribution[b.id] ?? 0),
      isNonCore: b.id === 'ON',
    }));
  }, [distribution, nonCorePct]);

  const hasData = chartData.some((d) => d.value > 0);

  if (!hasData) {
    return (
      <div className="rounded-md border border-border/50 bg-background p-3 text-center text-[10px] text-muted-foreground py-6">
        Enter bucket weights above to see the distribution chart.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border/50 bg-background p-3">
      <h4 className="text-xs font-medium mb-2">NMD maturity distribution (19 EBA buckets)</h4>
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="bucket"
              tick={{ fontSize: 7, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={{ stroke: 'hsl(var(--border))' }}
              tickLine={false}
              interval={0}
              angle={-45}
              textAnchor="end"
              height={40}
            />
            <YAxis
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              tick={{ fontSize: 8, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={{ stroke: 'hsl(var(--border))' }}
              tickLine={false}
              domain={[0, 'auto']}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as { bucket: string; value: number; isNonCore: boolean };
                return (
                  <div className="rounded-md border bg-popover px-2 py-1.5 text-xs shadow-md">
                    <div className="font-medium">{d.bucket}</div>
                    <div className="text-muted-foreground">
                      {d.isNonCore ? 'Non-core' : 'Core'}: {d.value.toFixed(2)}%
                    </div>
                  </div>
                );
              }}
            />
            <Bar dataKey="value" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={entry.isNonCore ? 'hsl(var(--muted-foreground))' : 'hsl(var(--primary))'}
                  opacity={entry.isNonCore ? 0.5 : 0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 mt-1 text-[10px]">
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-muted-foreground/50" />
          <span className="text-muted-foreground">Non-core (O/N)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-primary/80" />
          <span className="text-muted-foreground">Core (buckets 2-19)</span>
        </div>
      </div>
    </div>
  );
}
