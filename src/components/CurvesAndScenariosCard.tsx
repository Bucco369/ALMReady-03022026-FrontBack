import React, { useState } from 'react';
import { TrendingUp, Settings2, Eye, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Scenario } from '@/types/financial';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

// Placeholder curve definitions
const AVAILABLE_CURVES = [
  { id: 'risk-free', name: 'Risk-free curve', loaded: true },
  { id: 'euribor-3m', name: 'Euribor / OIS 3M', loaded: true },
  { id: 'euribor-6m', name: 'Euribor / OIS 6M', loaded: false },
  { id: 'swap-1y', name: 'Swap 1Y', loaded: false },
  { id: 'govt-bond', name: 'Govt Bond curve', loaded: false },
];

// Placeholder curve data for chart
const PLACEHOLDER_CURVE_DATA = [
  { tenor: '1M', 'Risk-free': 3.25, 'Euribor 3M': 3.45, 'Risk-free +200bp': 5.25, 'Risk-free -200bp': 1.25 },
  { tenor: '3M', 'Risk-free': 3.40, 'Euribor 3M': 3.60, 'Risk-free +200bp': 5.40, 'Risk-free -200bp': 1.40 },
  { tenor: '6M', 'Risk-free': 3.55, 'Euribor 3M': 3.75, 'Risk-free +200bp': 5.55, 'Risk-free -200bp': 1.55 },
  { tenor: '1Y', 'Risk-free': 3.70, 'Euribor 3M': 3.90, 'Risk-free +200bp': 5.70, 'Risk-free -200bp': 1.70 },
  { tenor: '2Y', 'Risk-free': 3.85, 'Euribor 3M': 4.05, 'Risk-free +200bp': 5.85, 'Risk-free -200bp': 1.85 },
  { tenor: '5Y', 'Risk-free': 4.00, 'Euribor 3M': 4.20, 'Risk-free +200bp': 6.00, 'Risk-free -200bp': 2.00 },
  { tenor: '10Y', 'Risk-free': 4.15, 'Euribor 3M': 4.35, 'Risk-free +200bp': 6.15, 'Risk-free -200bp': 2.15 },
  { tenor: '20Y', 'Risk-free': 4.25, 'Euribor 3M': 4.45, 'Risk-free +200bp': 6.25, 'Risk-free -200bp': 2.25 },
  { tenor: '30Y', 'Risk-free': 4.30, 'Euribor 3M': 4.50, 'Risk-free +200bp': 6.30, 'Risk-free -200bp': 2.30 },
];

interface CurvesAndScenariosCardProps {
  scenarios: Scenario[];
  onScenariosChange: (scenarios: Scenario[]) => void;
  selectedCurves: string[];
  onSelectedCurvesChange: (curves: string[]) => void;
}

export function CurvesAndScenariosCard({
  scenarios,
  onScenariosChange,
  selectedCurves,
  onSelectedCurvesChange,
}: CurvesAndScenariosCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [chartCurves, setChartCurves] = useState<string[]>(['Risk-free']);
  const [chartScenarios, setChartScenarios] = useState<string[]>(['base']);

  const handleCurveToggle = (curveId: string) => {
    if (selectedCurves.includes(curveId)) {
      onSelectedCurvesChange(selectedCurves.filter(c => c !== curveId));
    } else {
      onSelectedCurvesChange([...selectedCurves, curveId]);
    }
  };

  const handleScenarioToggle = (scenarioId: string) => {
    onScenariosChange(
      scenarios.map((s) =>
        s.id === scenarioId ? { ...s, enabled: !s.enabled } : s
      )
    );
  };

  const toggleChartCurve = (curveName: string) => {
    if (chartCurves.includes(curveName)) {
      if (chartCurves.length > 1) {
        setChartCurves(chartCurves.filter(c => c !== curveName));
      }
    } else {
      setChartCurves([...chartCurves, curveName]);
    }
  };

  const toggleChartScenario = (scenarioKey: string) => {
    if (chartScenarios.includes(scenarioKey)) {
      if (chartScenarios.length > 1) {
        setChartScenarios(chartScenarios.filter(s => s !== scenarioKey));
      }
    } else {
      setChartScenarios([...chartScenarios, scenarioKey]);
    }
  };

  const selectedCurvesCount = selectedCurves.length;
  const enabledScenariosCount = scenarios.filter(s => s.enabled).length;

  const curveColors: Record<string, string> = {
    'Risk-free': 'hsl(215, 50%, 45%)',
    'Euribor 3M': 'hsl(152, 45%, 42%)',
  };

  const scenarioColors: Record<string, string> = {
    'base': 'hsl(215, 50%, 45%)',
    '+200bp': 'hsl(0, 55%, 50%)',
    '-200bp': 'hsl(152, 45%, 42%)',
  };

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Curves & Scenarios</span>
          </div>
          <span className="text-[10px] font-medium text-muted-foreground">
            {selectedCurvesCount} curves • {enabledScenariosCount} scenarios
          </span>
        </div>

        <div className="dashboard-card-content">
          <div className="flex gap-3 flex-1 min-h-0">
            {/* Left: Curve Selection */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
                Curves
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-1 pr-2">
                  {AVAILABLE_CURVES.map((curve) => (
                    <label
                      key={curve.id}
                      className={`flex items-center gap-1.5 py-1 px-1.5 rounded cursor-pointer transition-colors text-xs ${
                        selectedCurves.includes(curve.id)
                          ? 'bg-primary/10'
                          : 'hover:bg-muted/50'
                      }`}
                    >
                      <Checkbox
                        checked={selectedCurves.includes(curve.id)}
                        onCheckedChange={() => handleCurveToggle(curve.id)}
                        className="h-3 w-3"
                      />
                      <span className={`truncate ${selectedCurves.includes(curve.id) ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                        {curve.name}
                      </span>
                      {curve.loaded ? (
                        <CheckCircle2 className="h-2.5 w-2.5 text-success shrink-0 ml-auto" />
                      ) : (
                        <XCircle className="h-2.5 w-2.5 text-muted-foreground/50 shrink-0 ml-auto" />
                      )}
                    </label>
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Vertical divider */}
            <div className="w-px bg-border" />

            {/* Right: Scenario Selection */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
                Scenarios
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-1 pr-2">
                  {scenarios.map((scenario) => (
                    <label
                      key={scenario.id}
                      className={`flex items-center gap-1.5 py-1 px-1.5 rounded cursor-pointer transition-colors text-xs ${
                        scenario.enabled
                          ? 'bg-primary/10'
                          : 'hover:bg-muted/50'
                      }`}
                    >
                      <Checkbox
                        checked={scenario.enabled}
                        onCheckedChange={() => handleScenarioToggle(scenario.id)}
                        className="h-3 w-3"
                      />
                      <span className={`truncate ${scenario.enabled ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                        {scenario.name}
                      </span>
                      <span
                        className={`shrink-0 ml-auto text-[9px] font-medium ${
                          scenario.shockBps > 0 ? 'text-destructive' : 'text-success'
                        }`}
                      >
                        {scenario.shockBps > 0 ? '+' : ''}{scenario.shockBps}bp
                      </span>
                    </label>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </div>

          <div className="pt-2 border-t border-border/30 mt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowDetails(true)}
              className="w-full h-6 text-xs"
            >
              <Eye className="mr-1 h-3 w-3" />
              View details
            </Button>
          </div>
        </div>
      </div>

      {/* Details Modal with Chart */}
      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Curve & Scenario Visualization
            </DialogTitle>
          </DialogHeader>
          
          <div className="flex-1 flex flex-col gap-4 overflow-hidden">
            {/* Chart */}
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={PLACEHOLDER_CURVE_DATA} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis 
                    dataKey="tenor" 
                    tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    stroke="hsl(var(--border))"
                  />
                  <YAxis 
                    tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    stroke="hsl(var(--border))"
                    tickFormatter={(v) => `${v}%`}
                    domain={[0, 8]}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '11px'
                    }}
                    formatter={(value: number) => [`${value.toFixed(2)}%`, '']}
                  />
                  <Legend wrapperStyle={{ fontSize: '10px' }} />
                  
                  {/* Base curves */}
                  {chartCurves.includes('Risk-free') && chartScenarios.includes('base') && (
                    <Line 
                      type="monotone" 
                      dataKey="Risk-free" 
                      stroke={curveColors['Risk-free']}
                      strokeWidth={2}
                      dot={false}
                    />
                  )}
                  {chartCurves.includes('Euribor 3M') && chartScenarios.includes('base') && (
                    <Line 
                      type="monotone" 
                      dataKey="Euribor 3M" 
                      stroke={curveColors['Euribor 3M']}
                      strokeWidth={2}
                      dot={false}
                    />
                  )}
                  
                  {/* Shocked curves */}
                  {chartCurves.includes('Risk-free') && chartScenarios.includes('+200bp') && (
                    <Line 
                      type="monotone" 
                      dataKey="Risk-free +200bp" 
                      stroke={scenarioColors['+200bp']}
                      strokeWidth={1.5}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                  )}
                  {chartCurves.includes('Risk-free') && chartScenarios.includes('-200bp') && (
                    <Line 
                      type="monotone" 
                      dataKey="Risk-free -200bp" 
                      stroke={scenarioColors['-200bp']}
                      strokeWidth={1.5}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Control Panel */}
            <div className="border-t border-border pt-3">
              <div className="grid grid-cols-2 gap-4">
                {/* Curve toggles */}
                <div>
                  <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-2">
                    Display Curves
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {['Risk-free', 'Euribor 3M'].map((curve) => (
                      <button
                        key={curve}
                        onClick={() => toggleChartCurve(curve)}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                          chartCurves.includes(curve)
                            ? 'bg-primary/15 text-primary border border-primary/30'
                            : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                        }`}
                      >
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: curveColors[curve] }}
                        />
                        {curve}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Scenario toggles */}
                <div>
                  <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-2">
                    Display Scenarios
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { key: 'base', label: 'Base' },
                      { key: '+200bp', label: '+200bp' },
                      { key: '-200bp', label: '-200bp' },
                    ].map((scenario) => (
                      <button
                        key={scenario.key}
                        onClick={() => toggleChartScenario(scenario.key)}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                          chartScenarios.includes(scenario.key)
                            ? 'bg-primary/15 text-primary border border-primary/30'
                            : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                        }`}
                      >
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: scenarioColors[scenario.key] }}
                        />
                        {scenario.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Info text */}
            <p className="text-[10px] text-muted-foreground text-center">
              This chart is illustrative only. Curve transformations will be computed programmatically by the pricing engine.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
