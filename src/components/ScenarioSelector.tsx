import React from 'react';
import { Settings2 } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import type { Scenario } from '@/types/financial';

interface ScenarioSelectorProps {
  scenarios: Scenario[];
  onScenariosChange: (scenarios: Scenario[]) => void;
}

export function ScenarioSelector({ scenarios, onScenariosChange }: ScenarioSelectorProps) {
  const handleToggle = (scenarioId: string) => {
    onScenariosChange(
      scenarios.map((s) =>
        s.id === scenarioId ? { ...s, enabled: !s.enabled } : s
      )
    );
  };

  const enabledCount = scenarios.filter((s) => s.enabled).length;

  return (
    <div className="section-card animate-fade-in">
      <div className="section-header">
        <Settings2 className="h-5 w-5 text-primary" />
        IRRBB Scenarios
        <span className="ml-auto text-sm font-normal text-muted-foreground">
          {enabledCount} of {scenarios.length} selected
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {scenarios.map((scenario) => (
          <label
            key={scenario.id}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
              scenario.enabled
                ? 'border-primary bg-accent'
                : 'border-border bg-card hover:border-primary/50'
            }`}
          >
            <Checkbox
              checked={scenario.enabled}
              onCheckedChange={() => handleToggle(scenario.id)}
              className="mt-0.5"
            />
            <div className="flex-1">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-medium text-foreground">{scenario.name}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                    scenario.shockBps > 0
                      ? 'bg-destructive/10 text-destructive'
                      : 'bg-success/10 text-success'
                  }`}
                >
                  {scenario.shockBps > 0 ? '+' : ''}
                  {scenario.shockBps} bps
                </span>
              </div>
              <p className="text-xs text-muted-foreground">{scenario.description}</p>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}
