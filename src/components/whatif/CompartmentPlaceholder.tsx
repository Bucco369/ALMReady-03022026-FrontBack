/**
 * CompartmentPlaceholder.tsx – "Coming soon" placeholder for future
 * What-If compartments (Find Limit, Behavioural, Pricing).
 */
import React from 'react';

interface CompartmentPlaceholderProps {
  title: string;
  icon: React.ElementType;
  description: string;
}

export function CompartmentPlaceholder({
  title,
  icon: Icon,
  description,
}: CompartmentPlaceholderProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      <div className="rounded-2xl bg-muted/40 p-6 mb-4">
        <Icon className="h-10 w-10 text-muted-foreground/40" />
      </div>
      <h3 className="text-sm font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-xs text-muted-foreground max-w-sm">{description}</p>
      <div className="mt-4 px-3 py-1.5 rounded-full bg-muted/50 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
        Coming Soon
      </div>
    </div>
  );
}
