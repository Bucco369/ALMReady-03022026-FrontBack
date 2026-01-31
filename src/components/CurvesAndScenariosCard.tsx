import React, { useState, useMemo } from 'react';
import { TrendingUp, Eye, CheckCircle2, XCircle, CheckSquare, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
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

// Placeholder curve definitions - these match what's shown in the quadrant
const AVAILABLE_CURVES = [
  { id: 'risk-free', name: 'Risk-free curve', shortName: 'Risk-free', loaded: true },
  { id: 'euribor-3m', name: 'Euribor / OIS 3M', shortName: 'Euribor 3M', loaded: true },
  { id: 'euribor-6m', name: 'Euribor / OIS 6M', shortName: 'Euribor 6M', loaded: false },
  { id: 'swap-1y', name: 'Swap 1Y', shortName: 'Swap 1Y', loaded: false },
  { id: 'govt-bond', name: 'Govt Bond curve', shortName: 'Govt Bond', loaded: false },
];

// Color palette for curves
const CURVE_COLORS: Record<string, string> = {
  'risk-free': 'hsl(215, 50%, 45%)',
  'euribor-3m': 'hsl(152, 45%, 42%)',
  'euribor-6m': 'hsl(280, 45%, 50%)',
  'swap-1y': 'hsl(38, 70%, 50%)',
  'govt-bond': 'hsl(340, 50%, 50%)',
};

// Color palette for scenarios (including custom)
const SCENARIO_COLORS: Record<string, string> = {
  'base': 'hsl(215, 50%, 45%)',
  'parallel-up': 'hsl(0, 55%, 50%)',
  'parallel-down': 'hsl(152, 45%, 42%)',
  'steepener': 'hsl(280, 45%, 50%)',
  'flattener': 'hsl(38, 70%, 50%)',
  'short-up': 'hsl(340, 50%, 50%)',
  'short-down': 'hsl(180, 45%, 42%)',
  'custom': 'hsl(25, 80%, 50%)',
};

// Generate placeholder curve data for all curves and scenarios
const generatePlaceholderData = () => {
  const tenors = ['1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y', '20Y', '30Y'];
  const baseRates: Record<string, number[]> = {
    'risk-free': [3.25, 3.40, 3.55, 3.70, 3.85, 4.00, 4.15, 4.25, 4.30],
    'euribor-3m': [3.45, 3.60, 3.75, 3.90, 4.05, 4.20, 4.35, 4.45, 4.50],
    'euribor-6m': [3.50, 3.65, 3.80, 3.95, 4.10, 4.25, 4.40, 4.50, 4.55],
    'swap-1y': [3.55, 3.70, 3.85, 4.00, 4.15, 4.30, 4.45, 4.55, 4.60],
    'govt-bond': [3.15, 3.30, 3.45, 3.60, 3.75, 3.90, 4.05, 4.15, 4.20],
  };

  return tenors.map((tenor, idx) => {
    const point: Record<string, number | string> = { tenor };
    
    // Base curves
    AVAILABLE_CURVES.forEach(curve => {
      point[`${curve.id}_base`] = baseRates[curve.id][idx];
    });
    
    // Scenario shocks (simplified illustrative transformations)
    AVAILABLE_CURVES.forEach(curve => {
      const base = baseRates[curve.id][idx];
      // Parallel Up +200bp
      point[`${curve.id}_parallel-up`] = base + 2.0;
      // Parallel Down -200bp
      point[`${curve.id}_parallel-down`] = Math.max(0, base - 2.0);
      // Steepener: short down, long up (scaled by tenor index)
      point[`${curve.id}_steepener`] = base + (idx - 4) * 0.3;
      // Flattener: short up, long down
      point[`${curve.id}_flattener`] = base - (idx - 4) * 0.25;
      // Short Up: bigger impact on short tenors
      point[`${curve.id}_short-up`] = base + Math.max(0, (6 - idx) * 0.4);
      // Short Down: bigger impact on short tenors
      point[`${curve.id}_short-down`] = Math.max(0, base - Math.max(0, (6 - idx) * 0.4));
    });
    
    return point;
  });
};

const PLACEHOLDER_CURVE_DATA = generatePlaceholderData();

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
  const [chartCurves, setChartCurves] = useState<string[]>(['risk-free']);
  const [chartScenarios, setChartScenarios] = useState<string[]>(['base']);
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customBps, setCustomBps] = useState<string>('');

  // All scenario keys including base
  const allScenarioKeys = useMemo(() => {
    return ['base', ...scenarios.map(s => s.id)];
  }, [scenarios]);

  // All curve IDs
  const allCurveIds = useMemo(() => {
    return AVAILABLE_CURVES.map(c => c.id);
  }, []);

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

  const toggleChartCurve = (curveId: string) => {
    if (chartCurves.includes(curveId)) {
      if (chartCurves.length > 1) {
        setChartCurves(chartCurves.filter(c => c !== curveId));
      }
    } else {
      setChartCurves([...chartCurves, curveId]);
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

  const selectAllChartCurves = () => {
    if (chartCurves.length === allCurveIds.length) {
      setChartCurves(['risk-free']); // Keep at least one
    } else {
      setChartCurves([...allCurveIds]);
    }
  };

  const selectAllChartScenarios = () => {
    if (chartScenarios.length === allScenarioKeys.length) {
      setChartScenarios(['base']); // Keep at least one
    } else {
      setChartScenarios([...allScenarioKeys]);
    }
  };

  const selectedCurvesCount = selectedCurves.length;
  const enabledScenariosCount = scenarios.filter(s => s.enabled).length;
  const customScenarios = scenarios.filter(s => s.id.startsWith('custom-'));

  const getCurveName = (curveId: string) => {
    return AVAILABLE_CURVES.find(c => c.id === curveId)?.shortName || curveId;
  };

  const getScenarioLabel = (scenarioKey: string) => {
    if (scenarioKey === 'base') return 'Base';
    const scenario = scenarios.find(s => s.id === scenarioKey);
    return scenario ? scenario.name : scenarioKey;
  };

  const getScenarioShock = (scenarioKey: string) => {
    if (scenarioKey === 'base') return null;
    const scenario = scenarios.find(s => s.id === scenarioKey);
    return scenario ? scenario.shockBps : null;
  };

  const handleAddCustomScenario = () => {
    const bps = parseInt(customBps, 10);
    if (isNaN(bps)) return;
    
    const sign = bps >= 0 ? '+' : '';
    const newScenario: Scenario = {
      id: `custom-${Date.now()}`,
      name: `Custom ${sign}${bps}bp`,
      shockBps: bps,
      enabled: true,
    };
    
    onScenariosChange([...scenarios, newScenario]);
    setCustomBps('');
    setShowCustomInput(false);
  };

  const handleRemoveCustomScenario = (scenarioId: string) => {
    onScenariosChange(scenarios.filter(s => s.id !== scenarioId));
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
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Scenarios
                </span>
                <Popover open={showCustomInput} onOpenChange={setShowCustomInput}>
                  <PopoverTrigger asChild>
                    <button className="text-[9px] text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5">
                      <Plus className="h-2.5 w-2.5" />
                      Custom
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="w-48 p-2" align="end">
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-foreground">Add Custom Scenario</div>
                      <div className="text-[10px] text-muted-foreground">Parallel shock (basis points)</div>
                      <div className="flex gap-1.5">
                        <Input
                          type="number"
                          placeholder="e.g. +150 or -100"
                          value={customBps}
                          onChange={(e) => setCustomBps(e.target.value)}
                          className="h-7 text-xs"
                        />
                        <Button
                          size="sm"
                          onClick={handleAddCustomScenario}
                          disabled={!customBps || isNaN(parseInt(customBps, 10))}
                          className="h-7 px-2 text-xs"
                        >
                          Add
                        </Button>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-1 pr-2">
                  {scenarios.map((scenario) => {
                    const isCustom = scenario.id.startsWith('custom-');
                    return (
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
                          className={`shrink-0 text-[9px] font-medium ${
                            scenario.shockBps > 0 ? 'text-destructive' : 'text-success'
                          }`}
                        >
                          {scenario.shockBps > 0 ? '+' : ''}{scenario.shockBps}bp
                        </span>
                        {isCustom && (
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              handleRemoveCustomScenario(scenario.id);
                            }}
                            className="shrink-0 ml-auto text-muted-foreground hover:text-destructive transition-colors"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </label>
                    );
                  })}
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
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
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
                    tickFormatter={(v) => `${v.toFixed(1)}%`}
                    domain={[-1, 8]}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '11px'
                    }}
                    formatter={(value: number, name: string) => {
                      const parts = name.split('_');
                      const curveName = getCurveName(parts[0]);
                      const scenarioName = getScenarioLabel(parts[1]);
                      return [`${value.toFixed(2)}%`, `${curveName} (${scenarioName})`];
                    }}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '9px' }}
                    formatter={(value: string) => {
                      const parts = value.split('_');
                      const curveName = getCurveName(parts[0]);
                      const scenarioName = getScenarioLabel(parts[1]);
                      return `${curveName} - ${scenarioName}`;
                    }}
                  />
                  
                  {/* Render lines for all selected curve + scenario combinations */}
                  {chartCurves.map(curveId => 
                    chartScenarios.map(scenarioKey => {
                      const dataKey = `${curveId}_${scenarioKey}`;
                      const isBase = scenarioKey === 'base';
                      const color = isBase ? CURVE_COLORS[curveId] : SCENARIO_COLORS[scenarioKey];
                      
                      return (
                        <Line
                          key={dataKey}
                          type="monotone"
                          dataKey={dataKey}
                          stroke={color}
                          strokeWidth={isBase ? 2 : 1.5}
                          strokeDasharray={isBase ? undefined : '5 5'}
                          dot={false}
                          name={dataKey}
                        />
                      );
                    })
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Control Panel */}
            <ScrollArea className="flex-1 min-h-0">
              <div className="border-t border-border pt-3">
                <div className="grid grid-cols-2 gap-4">
                  {/* Curve toggles */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                        Display Curves
                      </span>
                      <button
                        onClick={selectAllChartCurves}
                        className="inline-flex items-center gap-1 text-[9px] text-primary hover:text-primary/80 transition-colors"
                      >
                        <CheckSquare className="h-3 w-3" />
                        {chartCurves.length === allCurveIds.length ? 'Deselect all' : 'Select all'}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {AVAILABLE_CURVES.map((curve) => (
                        <button
                          key={curve.id}
                          onClick={() => toggleChartCurve(curve.id)}
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                            chartCurves.includes(curve.id)
                              ? 'bg-primary/15 text-primary border border-primary/30'
                              : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                          }`}
                        >
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: CURVE_COLORS[curve.id] }}
                          />
                          {curve.shortName}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Scenario toggles */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                        Display Scenarios
                      </span>
                      <button
                        onClick={selectAllChartScenarios}
                        className="inline-flex items-center gap-1 text-[9px] text-primary hover:text-primary/80 transition-colors"
                      >
                        <CheckSquare className="h-3 w-3" />
                        {chartScenarios.length === allScenarioKeys.length ? 'Deselect all' : 'Select all'}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {/* Base scenario */}
                      <button
                        onClick={() => toggleChartScenario('base')}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                          chartScenarios.includes('base')
                            ? 'bg-primary/15 text-primary border border-primary/30'
                            : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                        }`}
                      >
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: SCENARIO_COLORS['base'] }}
                        />
                        Base
                      </button>
                      
                      {/* All regulatory scenarios */}
                      {scenarios.map((scenario) => {
                        const shockBps = getScenarioShock(scenario.id);
                        return (
                          <button
                            key={scenario.id}
                            onClick={() => toggleChartScenario(scenario.id)}
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                              chartScenarios.includes(scenario.id)
                                ? 'bg-primary/15 text-primary border border-primary/30'
                                : 'bg-muted/50 text-muted-foreground border border-transparent hover:bg-muted'
                            }`}
                          >
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: SCENARIO_COLORS[scenario.id] || 'hsl(var(--muted-foreground))' }}
                            />
                            {scenario.name}
                            {shockBps !== null && (
                              <span className={`text-[8px] ${shockBps > 0 ? 'text-destructive' : 'text-success'}`}>
                                ({shockBps > 0 ? '+' : ''}{shockBps}bp)
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </ScrollArea>

            {/* Info text */}
            <p className="text-[10px] text-muted-foreground text-center shrink-0">
              This chart is illustrative only. Curve transformations will be computed programmatically by the pricing engine.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}