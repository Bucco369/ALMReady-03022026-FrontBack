/**
 * WhatIfAddTab.tsx – LEGACY template-based form for adding synthetic positions.
 *
 * ── STATUS ───────────────────────────────────────────────────────────────
 *
 *   SUPERSEDED by BuySellCompartment.tsx (AddCatalog component) inside
 *   the WhatIfWorkbench modal. This file is retained for reference.
 *
 *   The current flow uses:
 *     CascadingDropdowns → StructuralConfigRow → TemplateFieldsForm
 *     (all from shared/ProductConfigForm.tsx)
 *
 * ── ORIGINAL ROLE ────────────────────────────────────────────────────────
 *
 *   Two-step flow inside WhatIfBuilder's "Add Position" tab:
 *   1. Template selection: PRODUCT_TEMPLATES grouped by category.
 *   2. Form entry: Dynamic fields → WhatIfModification of type='add'.
 *
 *   Key differences vs current AddCatalog:
 *   • Flat template list (no cascading dropdowns)
 *   • No amortization selection
 *   • No progressive field reveal
 *   • No edit mode / Calculate Impact
 *   • Duplicates subcategoryMap inline (now in shared/constants.ts)
 */
import React, { useState } from 'react';
import { Plus, Building2, Landmark, TrendingUp, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PRODUCT_TEMPLATES, type ProductTemplate } from '@/types/whatif';
import { useWhatIf } from './WhatIfContext';

function parsePositiveNumber(input?: string): number | null {
  if (!input) return null;
  const parsed = parseFloat(input);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return parsed;
}

function computeResidualMaturityYears(formValues: Record<string, string>): number {
  const fromAvgLife = parsePositiveNumber(formValues.avgLife);
  if (fromAvgLife !== null) return fromAvgLife;

  const maturityDateRaw = formValues.maturityDate;
  if (!maturityDateRaw) return 0;

  const maturityDate = new Date(maturityDateRaw);
  if (Number.isNaN(maturityDate.getTime())) return 0;

  const startDateRaw = formValues.startDate;
  const startDate = startDateRaw ? new Date(startDateRaw) : new Date();
  if (Number.isNaN(startDate.getTime())) return 0;

  const years = (maturityDate.getTime() - startDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
  if (!Number.isFinite(years)) return 0;
  return Math.max(0, years);
}

export function WhatIfAddTab() {
  const [selectedTemplate, setSelectedTemplate] = useState<ProductTemplate | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const { addModification } = useWhatIf();

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'asset': return <TrendingUp className="h-3.5 w-3.5 text-success" />;
      case 'liability': return <Landmark className="h-3.5 w-3.5 text-destructive" />;
      case 'derivative': return <Building2 className="h-3.5 w-3.5 text-primary" />;
      default: return null;
    }
  };

  const handleSelectTemplate = (template: ProductTemplate) => {
    setSelectedTemplate(template);
    setFormValues({});
  };

  const handleFieldChange = (fieldId: string, value: string) => {
    setFormValues(prev => ({ ...prev, [fieldId]: value }));
  };

  const handleAddToModifications = () => {
    if (!selectedTemplate) return;
    
    const notional = formValues.notional || '—';
    const currency = formValues.currency || 'EUR';
    const rawRate = formValues.coupon || formValues.depositRate || formValues.fixedRate || formValues.wac;
    const parsedRate = rawRate !== undefined ? parseFloat(rawRate) : NaN;
    const rate = Number.isFinite(parsedRate) ? parsedRate / 100 : undefined;
    const maturity = computeResidualMaturityYears(formValues);
    
    // Map template to subcategory for balance tree placement
    const subcategoryMap: Record<string, string> = {
      'fixed-loan': 'loans',
      'floating-loan': 'loans',
      'mixed-loan': 'loans',
      'bond-portfolio': 'securities',
      'bond-frn': 'securities',
      'nmd': 'deposits',
      'term-deposit': 'term-deposits',
      'wholesale-fixed': 'wholesale-funding',
      'wholesale-floating': 'wholesale-funding',
      'covered-bond': 'wholesale-funding',
      'covered-bond-floating': 'wholesale-funding',
      'subordinated': 'wholesale-funding',
      'subordinated-floating': 'wholesale-funding',
      'subordinated-fix2float': 'wholesale-funding',
      'irs-hedge': 'loans', // derivatives appear under appropriate category
      'securitised': 'mortgages',
    };
    
    addModification({
      type: 'add',
      label: selectedTemplate.name,
      details: `${notional} ${currency}`,
      notional: parseFloat(notional.replace(/,/g, '')) || 0,
      currency,
      category: selectedTemplate.category,
      subcategory: subcategoryMap[selectedTemplate.id] || 'loans',
      rate,
      maturity,
      positionDelta: 1,
      // Motor-specific fields for backend What-If calculation
      productTemplateId: selectedTemplate.id,
      startDate: formValues.startDate || undefined,
      maturityDate: formValues.maturityDate || undefined,
      paymentFreq: formValues.paymentFreq || undefined,
      repricingFreq: formValues.repricingFreq || undefined,
      refIndex: formValues.refIndex || undefined,
      spread: formValues.spread ? parseFloat(formValues.spread) : undefined,
    });

    // Reset form
    setFormValues({});
  };

  const handleBack = () => {
    setSelectedTemplate(null);
    setFormValues({});
  };

  if (selectedTemplate) {
    return (
      <div className="flex flex-col h-full">
        {/* Header with back button */}
        <div className="flex items-center gap-2 pb-3 border-b border-border mb-3">
          <Button variant="ghost" size="sm" onClick={handleBack} className="h-6 px-2 text-xs">
            ← Back
          </Button>
          <div className="flex items-center gap-1.5">
            {getCategoryIcon(selectedTemplate.category)}
            <span className="text-xs font-medium">{selectedTemplate.name}</span>
          </div>
        </div>

        {/* Form */}
        <ScrollArea className="flex-1">
          <div className="space-y-3 pr-3">
            {selectedTemplate.fields.map((field) => (
              <div key={field.id} className="space-y-1">
                <Label className="text-[11px] text-muted-foreground flex items-center gap-1">
                  {field.label}
                  {field.required && <span className="text-destructive">*</span>}
                  {field.disabled && <span className="text-muted-foreground/50">(N/A)</span>}
                </Label>
                
                {field.type === 'select' ? (
                  <Select
                    value={formValues[field.id] || ''}
                    onValueChange={(val) => handleFieldChange(field.id, val)}
                    disabled={field.disabled}
                  >
                    <SelectTrigger className="h-7 text-xs">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      {field.options?.map(opt => (
                        <SelectItem key={opt} value={opt} className="text-xs">{opt}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    type={field.type === 'date' ? 'date' : field.type === 'number' ? 'number' : 'text'}
                    placeholder={field.placeholder}
                    value={formValues[field.id] || ''}
                    onChange={(e) => handleFieldChange(field.id, e.target.value)}
                    className="h-7 text-xs"
                    disabled={field.disabled}
                  />
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Add button */}
        <div className="pt-3 border-t border-border mt-3">
          <Button
            size="sm"
            className="w-full h-7 text-xs"
            onClick={handleAddToModifications}
          >
            <Plus className="h-3 w-3 mr-1" />
            Add to modifications
          </Button>
        </div>
      </div>
    );
  }

  // Template selection view
  const assetTemplates = PRODUCT_TEMPLATES.filter(t => t.category === 'asset');
  const liabilityTemplates = PRODUCT_TEMPLATES.filter(t => t.category === 'liability');
  const derivativeTemplates = PRODUCT_TEMPLATES.filter(t => t.category === 'derivative');

  return (
    <ScrollArea className="flex-1">
      <div className="space-y-4 pr-3">
        {/* Assets */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingUp className="h-3 w-3 text-success" />
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Asset Products</span>
          </div>
          <div className="space-y-1">
            {assetTemplates.map(template => (
              <TemplateButton key={template.id} template={template} onClick={() => handleSelectTemplate(template)} />
            ))}
          </div>
        </div>

        {/* Liabilities */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Landmark className="h-3 w-3 text-destructive" />
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Liability Products</span>
          </div>
          <div className="space-y-1">
            {liabilityTemplates.map(template => (
              <TemplateButton key={template.id} template={template} onClick={() => handleSelectTemplate(template)} />
            ))}
          </div>
        </div>

        {/* Derivatives */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Building2 className="h-3 w-3 text-primary" />
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Derivatives</span>
          </div>
          <div className="space-y-1">
            {derivativeTemplates.map(template => (
              <TemplateButton key={template.id} template={template} onClick={() => handleSelectTemplate(template)} />
            ))}
          </div>
        </div>
      </div>
    </ScrollArea>
  );
}

function TemplateButton({ template, onClick }: { template: ProductTemplate; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md border border-border bg-card hover:bg-accent/50 hover:border-primary/30 transition-colors text-left group"
    >
      <span className="text-xs text-foreground">{template.name}</span>
      <ChevronRight className="h-3 w-3 text-muted-foreground group-hover:text-primary transition-colors" />
    </button>
  );
}
