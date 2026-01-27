import React, { useState } from 'react';
import { Settings2, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { Scenario } from '@/types/financial';

interface ScenariosCardProps {
  scenarios: Scenario[];
  onScenariosChange: (scenarios: Scenario[]) => void;
}

export function ScenariosCard({ scenarios, onScenariosChange }: ScenariosCardProps) {
  const [showEdit, setShowEdit] = useState(false);
  
  const handleToggle = (scenarioId: string) => {
    onScenariosChange(
      scenarios.map((s) =>
        s.id === scenarioId ? { ...s, enabled: !s.enabled } : s
      )
    );
  };

  const enabledCount = scenarios.filter((s) => s.enabled).length;
  const enabledScenarios = scenarios.filter((s) => s.enabled);

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <Settings2 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">IRRBB Scenarios</span>
          </div>
          <span className="text-[10px] font-medium text-muted-foreground">
            {enabledCount}/{scenarios.length} selected
          </span>
        </div>

        <div className="dashboard-card-content">
          <p className="text-[10px] text-muted-foreground mb-2">Standard regulatory scenarios</p>
          
          <div className="flex flex-wrap gap-1 mb-2">
            {enabledScenarios.map((scenario) => (
              <ScenarioPill key={scenario.id} scenario={scenario} />
            ))}
            {enabledCount === 0 && (
              <span className="text-xs text-muted-foreground italic">No scenarios selected</span>
            )}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEdit(true)}
            className="w-full h-6 text-xs mt-auto"
          >
            <Eye className="mr-1 h-3 w-3" />
            Edit scenarios
          </Button>
        </div>
      </div>

      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Settings2 className="h-4 w-4 text-primary" />
              IRRBB Scenarios
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Select regulatory interest rate shock scenarios to apply
            </p>
            
            <div className="grid gap-1.5 max-h-[50vh] overflow-auto">
              {scenarios.map((scenario) => (
                <label
                  key={scenario.id}
                  className={`flex items-center gap-2 p-2 rounded-md border cursor-pointer transition-colors ${
                    scenario.enabled 
                      ? 'border-primary/30 bg-primary/5' 
                      : 'border-border bg-background hover:bg-muted/50'
                  }`}
                >
                  <Checkbox
                    checked={scenario.enabled}
                    onCheckedChange={() => handleToggle(scenario.id)}
                    className="shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-foreground">
                      {scenario.name}
                    </span>
                  </div>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      scenario.shockBps > 0
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-success/10 text-success'
                    }`}
                  >
                    {scenario.shockBps > 0 ? '+' : ''}{scenario.shockBps}bp
                  </span>
                </label>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ScenarioPill({ scenario }: { scenario: Scenario }) {
  const isPositive = scenario.shockBps > 0;
  return (
    <div
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
        isPositive 
          ? 'bg-destructive/10 text-destructive' 
          : 'bg-success/10 text-success'
      }`}
    >
      <span>{scenario.name}</span>
      <span className="opacity-70">
        {isPositive ? '+' : ''}{scenario.shockBps}bp
      </span>
    </div>
  );
}
