import React from 'react';
import { Calculator } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface CalculateButtonProps {
  onClick: () => void;
  disabled: boolean;
  isCalculating: boolean;
}

export function CalculateButton({ onClick, disabled, isCalculating }: CalculateButtonProps) {
  return (
    <Button
      size="lg"
      className="w-full gap-2 bg-primary text-primary-foreground shadow-lg transition-all hover:bg-primary/90 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-50"
      onClick={onClick}
      disabled={disabled || isCalculating}
    >
      {isCalculating ? (
        <>
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
          Calculating...
        </>
      ) : (
        <>
          <Calculator className="h-5 w-5" />
          Calculate EVE & NII
        </>
      )}
    </Button>
  );
}
