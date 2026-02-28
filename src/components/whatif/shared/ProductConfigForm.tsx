/**
 * ProductConfigForm.tsx – Shared product configuration form engine.
 *
 * ── ROLE IN THE SYSTEM ──────────────────────────────────────────────────
 *
 *   The single source of truth for product selection UI. Used by:
 *
 *   • AddCatalog (BuySellCompartment) — full form, all fields editable
 *   • FindLimitCompartment            — same form, but "solve-for" field
 *                                       is excluded (shown as "Solved by
 *                                       Find Limit" placeholder)
 *
 *   Any change here automatically propagates to both consumers.
 *
 * ── PROGRESSIVE REVEAL ──────────────────────────────────────────────────
 *
 *   Fields appear one-by-one as the user fills required values:
 *
 *   Row 1 (CascadingDropdowns):
 *     Side → Category → Amortization → Rate Type
 *     • Category is hidden when only 1 family exists (e.g. Derivatives)
 *     • Amortization hidden for families with noAmortization flag
 *     • Derivatives promote Currency into Row 1 (saves vertical space)
 *
 *   Row 2 (StructuralConfigRow):
 *     Currency → Day Count → Grace Period → Grace Years
 *     • Hidden entirely for Derivatives (Currency in Row 1, no DayCount)
 *     • Grace only shown for loans family
 *
 *   Row 3 (TemplateFieldsForm):
 *     Dynamic 3-column grid of template-specific fields
 *     • Fields with showWhen conditions appear/hide based on parent value
 *     • Required unfilled fields block downstream fields (progressive)
 *     • fieldGroups enable side-by-side panels (used by IRS swap legs)
 *     • excludeFieldIds marks "solved" fields for FindLimit mode
 *
 * ── FIELD GROUPS (IRS / DERIVATIVES) ────────────────────────────────────
 *
 *   Templates can define fieldGroups for multi-panel layouts:
 *   ┌─────────────────┬─────────────────┐
 *   │    Leg A (Pay)   │   Leg B (Receive)│
 *   │  ─────────────   │  ─────────────   │
 *   │  Notional        │  Notional        │
 *   │  Rate            │  RefIndex        │
 *   │  Frequency       │  Spread          │
 *   └─────────────────┴─────────────────┘
 *   Each group has independent progressive reveal chains.
 *   Pay leg is always sorted to the left.
 *
 * ── EXPORTS ─────────────────────────────────────────────────────────────
 *
 *   useProductFormState():
 *     Hook returning { state, callbacks, derived, prefill, reset }.
 *     state:     raw selections (side, family, amortization, variant, formValues)
 *     callbacks: cascade handlers that reset downstream on change
 *     derived:   computed values (selectedTemplate, fieldVisibility, etc.)
 *     prefill:   bulk-set all state at once (used for edit mode round-trips)
 *     reset:     clear everything back to initial state
 *
 *   CascadingDropdowns:    Row 1 — Side → Category → Amortization → Rate Type
 *   StructuralConfigRow:   Row 2 — Currency → DayCount → Grace
 *   TemplateFieldsForm:    Row 3 — Dynamic template fields (3-col or grouped)
 *   ComingSoonPlaceholder: Disabled-variant badge for unreleased products
 */
import React, { useCallback, useMemo, useState } from 'react';
import { Clock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  PRODUCT_TEMPLATES,
  PRODUCT_FAMILIES,
  AMORTIZATION_OPTIONS,
  type ProductTemplate,
  type ProductField,
  type ProductFamily,
  type ProductVariant,
  type AmortizationOption,
  type FieldGroup,
} from '@/types/whatif';
import {
  CURRENCY_OPTIONS,
  DAY_COUNT_OPTIONS,
  ROW2_FIELD_IDS,
} from './constants';

// ── Types ────────────────────────────────────────────────────────────────

export interface ProductFormState {
  selectedSide: string;
  selectedFamilyId: string;
  selectedAmortization: string;
  selectedVariantId: string;
  formValues: Record<string, string>;
}

export interface ProductFormCallbacks {
  onSideChange: (value: string) => void;
  onFamilyChange: (value: string) => void;
  onAmortizationChange: (value: string) => void;
  onVariantChange: (value: string) => void;
  onFieldChange: (fieldId: string, value: string) => void;
}

export interface ProductFormDerived {
  availableFamilies: ProductFamily[];
  selectedFamily: ProductFamily | null;
  hasAmortizationStep: boolean;
  availableAmortizations: AmortizationOption[];
  selectedVariant: ProductVariant | null;
  selectedTemplate: ProductTemplate | null;
  templateFormFields: ProductField[];
  fieldVisibility: Record<string, boolean>;
  allRequiredFormFieldsFilled: boolean;
  childFieldMap: Record<string, ProductField[]>;
  gridFields: ProductField[];
}

export interface ProductFormConfig {
  /** Fields to exclude from the template form (e.g., the "solve for" field). */
  excludeFieldIds?: Set<string>;
}

// ── Hook: useProductFormState ────────────────────────────────────────────

export function useProductFormState() {
  const [selectedSide, setSelectedSide] = useState('');
  const [selectedFamilyId, setSelectedFamilyId] = useState('');
  const [selectedAmortization, setSelectedAmortization] = useState('');
  const [selectedVariantId, setSelectedVariantId] = useState('');
  const [formValues, setFormValues] = useState<Record<string, string>>({});

  // ── Derived ──────────────────────────────────────────────────────────

  const availableFamilies = selectedSide
    ? PRODUCT_FAMILIES.filter((f) => f.side === selectedSide)
    : [];

  const selectedFamily = availableFamilies.find((f) => f.id === selectedFamilyId) ?? null;

  const hasAmortizationStep = (selectedFamily?.amortizationTypes?.length ?? 0) > 0;

  const availableAmortizations = hasAmortizationStep
    ? AMORTIZATION_OPTIONS.filter((a) =>
        selectedFamily!.amortizationTypes!.includes(a.id),
      )
    : [];

  const selectedVariant =
    selectedFamily?.variants.find((v) => v.id === selectedVariantId) ?? null;

  const selectedTemplate = selectedVariant?.templateId
    ? (PRODUCT_TEMPLATES.find((t) => t.id === selectedVariant.templateId) ?? null)
    : null;

  const templateFormFields = useMemo(() => {
    if (!selectedTemplate) return [];
    return selectedTemplate.fields.filter((f) => !ROW2_FIELD_IDS.has(f.id));
  }, [selectedTemplate]);

  const fieldVisibility = useMemo(() => {
    const vis: Record<string, boolean> = {};
    let canShowNext = true;

    // Parallel reveal: each group gets its own independent chain
    const hasFieldGroups = (selectedTemplate?.fieldGroups?.length ?? 0) > 0;
    const groupCanShow: Record<string, boolean> = {};
    let groupsStarted = false;

    for (const field of templateFormFields) {
      if (field.showWhen && formValues[field.showWhen.field] !== field.showWhen.value) {
        vis[field.id] = false;
        continue;
      }

      if (hasFieldGroups && field.group) {
        // First field in this group inherits the ungrouped chain state
        if (!(field.group in groupCanShow)) {
          groupCanShow[field.group] = canShowNext;
          groupsStarted = true;
        }
        if (groupCanShow[field.group]) {
          vis[field.id] = true;
          if (field.required && !formValues[field.id]) {
            groupCanShow[field.group] = false;
          }
        } else {
          vis[field.id] = false;
        }
      } else {
        // Post-group ungrouped: require ALL groups complete
        if (groupsStarted && hasFieldGroups) {
          canShowNext = Object.values(groupCanShow).every((v) => v);
        }
        if (canShowNext) {
          vis[field.id] = true;
          if (field.required && !formValues[field.id]) {
            canShowNext = false;
          }
        } else {
          vis[field.id] = false;
        }
      }
    }

    return vis;
  }, [templateFormFields, formValues, selectedTemplate]);

  const allRequiredFormFieldsFilled = useMemo(() => {
    return templateFormFields
      .filter((f) => {
        if (f.disabled || f.derivedFrom || !f.required) return false;
        if (f.showWhen && formValues[f.showWhen.field] !== f.showWhen.value) return false;
        return true;
      })
      .every((f) => !!formValues[f.id]);
  }, [templateFormFields, formValues]);

  const childFieldMap = useMemo(() => {
    const map: Record<string, ProductField[]> = {};
    for (const field of templateFormFields) {
      if (field.showWhen) {
        if (!map[field.showWhen.field]) map[field.showWhen.field] = [];
        map[field.showWhen.field].push(field);
      }
    }
    return map;
  }, [templateFormFields]);

  const gridFields = useMemo(() => {
    return templateFormFields.filter((f) => !f.showWhen);
  }, [templateFormFields]);

  // ── Cascade handlers ─────────────────────────────────────────────────

  const onSideChange = useCallback((value: string) => {
    setSelectedSide(value);
    setSelectedAmortization('');
    setSelectedVariantId('');
    setFormValues({});
    // Auto-select when there's only one family for this side
    const families = PRODUCT_FAMILIES.filter((f) => f.side === value);
    setSelectedFamilyId(families.length === 1 ? families[0].id : '');
  }, []);

  const onFamilyChange = useCallback((value: string) => {
    setSelectedFamilyId(value);
    setSelectedAmortization('');
    setSelectedVariantId('');
    setFormValues({});
  }, []);

  const onAmortizationChange = useCallback((value: string) => {
    setSelectedAmortization(value);
    setSelectedVariantId('');
    setFormValues({});
  }, []);

  const onVariantChange = useCallback((value: string) => {
    setSelectedVariantId(value);
    setFormValues({});
  }, []);

  const onFieldChange = useCallback((fieldId: string, value: string) => {
    setFormValues((prev) => {
      const next = { ...prev, [fieldId]: value };
      // Auto-compute derived fields that depend on this field
      for (const tmpl of PRODUCT_TEMPLATES) {
        for (const f of tmpl.fields) {
          if (f.derivedFrom && f.derivedFrom.field === fieldId) {
            next[f.id] = f.derivedFrom.map[value] || '';
          }
        }
      }
      return next;
    });
  }, []);

  // ── Bulk state operations ────────────────────────────────────────────

  const prefill = useCallback((s: ProductFormState) => {
    setSelectedSide(s.selectedSide);
    setSelectedFamilyId(s.selectedFamilyId);
    setSelectedAmortization(s.selectedAmortization);
    setSelectedVariantId(s.selectedVariantId);
    setFormValues(s.formValues);
  }, []);

  const reset = useCallback(() => {
    setSelectedSide('');
    setSelectedFamilyId('');
    setSelectedAmortization('');
    setSelectedVariantId('');
    setFormValues({});
  }, []);

  return {
    state: {
      selectedSide,
      selectedFamilyId,
      selectedAmortization,
      selectedVariantId,
      formValues,
    } as ProductFormState,
    callbacks: {
      onSideChange,
      onFamilyChange,
      onAmortizationChange,
      onVariantChange,
      onFieldChange,
    } as ProductFormCallbacks,
    derived: {
      availableFamilies,
      selectedFamily,
      hasAmortizationStep,
      availableAmortizations,
      selectedVariant,
      selectedTemplate,
      templateFormFields,
      fieldVisibility,
      allRequiredFormFieldsFilled,
      childFieldMap,
      gridFields,
    } as ProductFormDerived,
    prefill,
    reset,
    setFormValues,
  };
}

// ═════════════════════════════════════════════════════════════════════════
// CascadingDropdowns – Side → Category → Amortization → Rate Type
// ═════════════════════════════════════════════════════════════════════════

interface CascadingDropdownsProps {
  state: ProductFormState;
  callbacks: ProductFormCallbacks;
  derived: ProductFormDerived;
}

export function CascadingDropdowns({
  state,
  callbacks,
  derived,
}: CascadingDropdownsProps) {
  const { selectedSide, selectedVariantId, formValues } = state;
  const { onSideChange, onFamilyChange, onAmortizationChange, onVariantChange, onFieldChange } = callbacks;
  const {
    availableFamilies,
    selectedFamily,
    hasAmortizationStep,
    availableAmortizations,
    selectedVariant,
  } = derived;

  // Skip Category when only one family (e.g. Derivatives)
  const showCategoryDropdown = availableFamilies.length !== 1;
  // Skip Amortization entirely for families that don't have it (e.g. Derivatives)
  const showAmortizationDropdown = !selectedFamily?.noAmortization;
  // Derivatives: promote Currency into this row (saves a whole row)
  const showCurrencyInRow1 = selectedFamily?.side === 'derivative' && !!selectedVariant && !selectedVariant.comingSoon;
  // Count hidden columns to pad with spacers (keeps 4-col grid stable)
  const hiddenColumns = (showCategoryDropdown ? 0 : 1) + (showAmortizationDropdown ? 0 : 1) - (showCurrencyInRow1 ? 1 : 0);

  return (
    <div className="grid grid-cols-4 gap-2">
      {/* Side */}
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground">Side</Label>
        <Select value={selectedSide} onValueChange={onSideChange}>
          <SelectTrigger className="h-7 text-[11px]">
            <SelectValue placeholder="Side..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="asset" className="text-xs">Asset</SelectItem>
            <SelectItem value="liability" className="text-xs">Liability</SelectItem>
            <SelectItem value="derivative" className="text-xs">Derivative</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Category — hidden when only one family exists for the side */}
      {showCategoryDropdown && (
        <div className="space-y-1">
          {selectedSide ? (
            <>
              <Label className="text-[10px] text-muted-foreground">Category</Label>
              <Select value={state.selectedFamilyId} onValueChange={onFamilyChange}>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue placeholder="Category..." />
                </SelectTrigger>
                <SelectContent>
                  {availableFamilies.map((f) => (
                    <SelectItem key={f.id} value={f.id} className="text-xs">
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          ) : <div className="h-[calc(14px+28px+4px)]" />}
        </div>
      )}

      {/* Amortization — hidden for families where it doesn't apply (e.g. Derivatives) */}
      {showAmortizationDropdown && (
        <div className="space-y-1">
          {selectedFamily && hasAmortizationStep ? (
            <>
              <Label className="text-[10px] text-muted-foreground">Amortization</Label>
              <Select value={state.selectedAmortization} onValueChange={onAmortizationChange}>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue placeholder="Amortization..." />
                </SelectTrigger>
                <SelectContent>
                  {availableAmortizations.map((a) => (
                    <SelectItem key={a.id} value={a.id} className="text-xs">
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          ) : selectedFamily ? (
            <>
              <Label className="text-[10px] text-muted-foreground">Amortization</Label>
              <Select value="bullet" disabled>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="bullet" className="text-xs">Bullet</SelectItem>
                </SelectContent>
              </Select>
            </>
          ) : <div className="h-[calc(14px+28px+4px)]" />}
        </div>
      )}

      {/* Rate Type */}
      <div className="space-y-1">
        {selectedFamily && (!hasAmortizationStep || state.selectedAmortization) ? (
          <>
            <Label className="text-[10px] text-muted-foreground">Rate Type</Label>
            <Select value={selectedVariantId} onValueChange={onVariantChange}>
              <SelectTrigger className="h-7 text-[11px]">
                <SelectValue placeholder="Rate..." />
              </SelectTrigger>
              <SelectContent>
                {selectedFamily.variants.map((v) => (
                  <SelectItem
                    key={v.id}
                    value={v.id}
                    className="text-xs"
                    disabled={v.comingSoon}
                  >
                    {v.name}
                    {v.comingSoon ? ' (coming soon)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        ) : <div className="h-[calc(14px+28px+4px)]" />}
      </div>

      {/* Currency — promoted into row 1 for derivatives */}
      {showCurrencyInRow1 && (
        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground">Currency</Label>
          <Select
            value={formValues.currency || ''}
            onValueChange={(val) => onFieldChange('currency', val)}
          >
            <SelectTrigger className="h-7 text-[11px]">
              <SelectValue placeholder="Currency..." />
            </SelectTrigger>
            <SelectContent>
              {CURRENCY_OPTIONS.map((c) => (
                <SelectItem key={c} value={c} className="text-xs">{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Spacers for hidden columns — keeps 4-col grid stable */}
      {Array.from({ length: Math.max(0, hiddenColumns) }).map((_, i) => (
        <div key={`spacer-${i}`} className="h-[calc(14px+28px+4px)]" />
      ))}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════
// StructuralConfigRow – Currency → DayCount → Grace Period → Grace Years
// ═════════════════════════════════════════════════════════════════════════

interface StructuralConfigRowProps {
  state: ProductFormState;
  callbacks: ProductFormCallbacks;
  derived: ProductFormDerived;
}

export function StructuralConfigRow({
  state,
  callbacks,
  derived,
}: StructuralConfigRowProps) {
  const { selectedFamilyId, formValues } = state;
  const { onFieldChange } = callbacks;
  const { selectedVariant, selectedFamily } = derived;

  if (!selectedVariant || selectedVariant.comingSoon) return null;

  // Derivatives: Currency is in CascadingDropdowns row 1, Day Count is per-leg
  const isDerivative = selectedFamily?.side === 'derivative';
  if (isDerivative) return null;

  return (
    <div className="grid grid-cols-4 gap-2">
      {/* Currency */}
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground">Currency</Label>
        <Select
          value={formValues.currency || ''}
          onValueChange={(val) => onFieldChange('currency', val)}
        >
          <SelectTrigger className="h-7 text-[11px]">
            <SelectValue placeholder="Currency..." />
          </SelectTrigger>
          <SelectContent>
            {CURRENCY_OPTIONS.map((c) => (
              <SelectItem key={c} value={c} className="text-xs">{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Day Count — skipped for derivatives (they have per-leg day counts) */}
      {!isDerivative && (
        <div className="space-y-1">
          {formValues.currency ? (
            <>
              <Label className="text-[10px] text-muted-foreground">Day Count</Label>
              <Select
                value={formValues.daycount || ''}
                onValueChange={(val) => onFieldChange('daycount', val)}
              >
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue placeholder="Day count..." />
                </SelectTrigger>
                <SelectContent>
                  {DAY_COUNT_OPTIONS.map((d) => (
                    <SelectItem key={d.value} value={d.value} className="text-xs">
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          ) : <div className="h-[calc(14px+28px+4px)]" />}
        </div>
      )}

      {/* Grace Period (loans only) */}
      <div className="space-y-1">
        {!isDerivative && formValues.daycount && selectedFamilyId === 'loans' ? (
          <>
            <Label className="text-[10px] text-muted-foreground">Grace Period</Label>
            <Select
              value={formValues.gracePeriod || ''}
              onValueChange={(val) => {
                onFieldChange('gracePeriod', val);
                if (val === 'no') onFieldChange('graceYears', '');
              }}
            >
              <SelectTrigger className="h-7 text-[11px]">
                <SelectValue placeholder="Grace..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="no" className="text-xs">No</SelectItem>
                <SelectItem value="yes" className="text-xs">Yes</SelectItem>
              </SelectContent>
            </Select>
          </>
        ) : <div className="h-[calc(14px+28px+4px)]" />}
      </div>

      {/* Grace Years */}
      <div className="space-y-1">
        {formValues.gracePeriod === 'yes' && selectedFamilyId === 'loans' ? (
          <>
            <Label className="text-[10px] text-muted-foreground">Grace (years)</Label>
            <Input
              type="number"
              min="0"
              step="0.5"
              placeholder="e.g. 2"
              value={formValues.graceYears || ''}
              onChange={(e) => onFieldChange('graceYears', e.target.value)}
              className="h-7 text-[11px]"
            />
          </>
        ) : <div className="h-[calc(14px+28px+4px)]" />}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════
// ComingSoonPlaceholder
// ═════════════════════════════════════════════════════════════════════════

export function ComingSoonPlaceholder({ name }: { name: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2.5 rounded-md border border-border/40 bg-muted/20">
      <Clock className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-xs text-muted-foreground">
        {name} — coming soon
      </span>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════
// TemplateFieldsForm – Progressive 3-column template form
// ═════════════════════════════════════════════════════════════════════════

interface TemplateFieldsFormProps {
  state: ProductFormState;
  callbacks: ProductFormCallbacks;
  derived: ProductFormDerived;
  config?: ProductFormConfig;
}

/** Renders a single field cell (label + input/select/derived). */
function FieldCell({
  field,
  formValues,
  onFieldChange,
  isVisible,
  isExcluded,
  children: childFields,
  childVisibility,
  excludeFieldIds,
}: {
  field: ProductField;
  formValues: Record<string, string>;
  onFieldChange: (id: string, val: string) => void;
  isVisible: boolean;
  isExcluded: boolean;
  children?: ProductField[];
  childVisibility?: Record<string, boolean>;
  excludeFieldIds?: Set<string>;
}) {
  if (!isVisible) return <div className="h-[calc(14px+28px+4px)]" />;

  const hasChildren = childFields && childFields.length > 0;
  const hasVisibleChildren = hasChildren && childFields.some((c) => childVisibility?.[c.id]);

  return (
    <div className="space-y-1">
      {/* Label row — when children are visible, show parent + child labels side-by-side */}
      {hasVisibleChildren ? (
        <div className="flex gap-1.5">
          <div className="w-1/2">
            <Label className="text-[10px] text-muted-foreground flex items-center gap-1">
              {field.label}
              {field.required && !isExcluded && <span className="text-destructive">*</span>}
            </Label>
          </div>
          {childFields.map((child) =>
            childVisibility?.[child.id] ? (
              <div key={`lbl-${child.id}`} className="w-1/2">
                <Label className="text-[10px] text-muted-foreground/70">{child.label}</Label>
              </div>
            ) : null
          )}
        </div>
      ) : (
        <Label className="text-[10px] text-muted-foreground flex items-center gap-1">
          {field.label}
          {field.required && !isExcluded && <span className="text-destructive">*</span>}
          {field.disabled && <span className="text-muted-foreground/50">(N/A)</span>}
        </Label>
      )}
      {/* Content */}
      {isExcluded ? (
        <Input
          disabled
          value=""
          placeholder="Solved by Find Limit"
          className="h-7 text-[11px] border-primary/30 bg-primary/5 placeholder:text-primary/60 placeholder:italic"
        />
      ) : field.derivedFrom ? (
        <Input disabled value={formValues[field.id] || ''} placeholder="—" className="h-7 text-[11px]" />
      ) : hasChildren ? (
        <div className="flex gap-1.5">
          <div className={hasVisibleChildren ? 'w-1/2' : 'w-full'}>
            <FieldInput field={field} formValues={formValues} onFieldChange={onFieldChange} />
          </div>
          {childFields.map((child) => {
            const childExcluded = excludeFieldIds?.has(child.id);
            return childVisibility?.[child.id] ? (
              <div key={child.id} className="w-1/2">
                {childExcluded ? (
                  <Input disabled value="" placeholder="Solved" className="h-7 text-[11px] border-primary/30 bg-primary/5 placeholder:text-primary/60 placeholder:italic" />
                ) : (
                  <Input
                    type={child.type === 'date' ? 'date' : child.type === 'number' ? 'number' : 'text'}
                    placeholder={child.placeholder}
                    value={formValues[child.id] || ''}
                    onChange={(e) => onFieldChange(child.id, e.target.value)}
                    className="h-7 text-[11px]"
                  />
                )}
              </div>
            ) : null;
          })}
        </div>
      ) : (
        <FieldInput field={field} formValues={formValues} onFieldChange={onFieldChange} />
      )}
    </div>
  );
}

/** Renders a bare select or input control (no label). */
function FieldInput({
  field,
  formValues,
  onFieldChange,
}: {
  field: ProductField;
  formValues: Record<string, string>;
  onFieldChange: (id: string, val: string) => void;
}) {
  if (field.type === 'select') {
    return (
      <Select
        value={formValues[field.id] || ''}
        onValueChange={(val) => onFieldChange(field.id, val)}
        disabled={field.disabled}
      >
        <SelectTrigger className="h-7 text-[11px]">
          <SelectValue placeholder="Select..." />
        </SelectTrigger>
        <SelectContent>
          {field.options?.map((opt) => (
            <SelectItem key={opt} value={opt} className="text-xs">{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input
      type={field.type === 'date' ? 'date' : field.type === 'number' ? 'number' : 'text'}
      placeholder={field.placeholder}
      value={formValues[field.id] || ''}
      onChange={(e) => onFieldChange(field.id, e.target.value)}
      className="h-7 text-[11px]"
      disabled={field.disabled}
    />
  );
}

export function TemplateFieldsForm({
  state,
  callbacks,
  derived,
  config,
}: TemplateFieldsFormProps) {
  const { formValues } = state;
  const { onFieldChange } = callbacks;
  const { fieldVisibility, gridFields, childFieldMap, templateFormFields, selectedTemplate } = derived;
  const excludeFieldIds = config?.excludeFieldIds;

  // When fields are excluded (Find Limit mode), recompute progressive reveal
  // so excluded fields don't block the chain.
  const hasFieldGroups = (selectedTemplate?.fieldGroups?.length ?? 0) > 0;

  const adjustedFieldVisibility = useMemo(() => {
    if (!excludeFieldIds || excludeFieldIds.size === 0) return fieldVisibility;

    const vis: Record<string, boolean> = {};
    let canShowNext = true;
    const groupCanShow: Record<string, boolean> = {};
    let groupsStarted = false;

    for (const field of templateFormFields) {
      if (field.showWhen && formValues[field.showWhen.field] !== field.showWhen.value) {
        vis[field.id] = false;
        continue;
      }

      if (hasFieldGroups && field.group) {
        if (!(field.group in groupCanShow)) {
          groupCanShow[field.group] = canShowNext;
          groupsStarted = true;
        }
        if (groupCanShow[field.group]) {
          vis[field.id] = true;
          if (excludeFieldIds.has(field.id)) continue;
          if (field.required && !formValues[field.id]) groupCanShow[field.group] = false;
        } else {
          vis[field.id] = false;
        }
      } else {
        if (groupsStarted && hasFieldGroups) {
          canShowNext = Object.values(groupCanShow).every((v) => v);
        }
        if (canShowNext) {
          vis[field.id] = true;
          if (excludeFieldIds.has(field.id)) continue;
          if (field.required && !formValues[field.id]) canShowNext = false;
        } else {
          vis[field.id] = false;
        }
      }
    }
    return vis;
  }, [excludeFieldIds, fieldVisibility, templateFormFields, formValues, hasFieldGroups]);

  // ── Grouped layout (e.g. IRS swap legs) ────────────────────────────────
  const fieldGroups = selectedTemplate?.fieldGroups;
  const hasGroups = fieldGroups && fieldGroups.length > 0;

  // Split gridFields into ungrouped-top, groups, ungrouped-bottom
  const { topFields, groupedFieldMap, bottomFields } = useMemo(() => {
    if (!hasGroups) return { topFields: gridFields, groupedFieldMap: {} as Record<string, ProductField[]>, bottomFields: [] as ProductField[] };

    const top: ProductField[] = [];
    const groups: Record<string, ProductField[]> = {};
    const bottom: ProductField[] = [];
    let seenAnyGroup = false;

    for (const f of gridFields) {
      if (f.group) {
        seenAnyGroup = true;
        if (!groups[f.group]) groups[f.group] = [];
        groups[f.group].push(f);
      } else if (!seenAnyGroup) {
        top.push(f);
      } else {
        bottom.push(f);
      }
    }
    return { topFields: top, groupedFieldMap: groups, bottomFields: bottom };
  }, [hasGroups, gridFields]);

  // Split topFields: last N fields (N = group count) become pre-group headers
  // aligned with the 2-col panel grid; the rest stay in the 3-col grid.
  const groupCount = fieldGroups?.length ?? 0;
  const preGroupFields = hasGroups && topFields.length >= groupCount
    ? topFields.slice(-groupCount)
    : [];
  const mainTopFields = hasGroups && preGroupFields.length > 0
    ? topFields.slice(0, -groupCount)
    : topFields;

  // Order groups so the "Pay" group is always on the left
  const orderedFieldGroups = useMemo(() => {
    if (!fieldGroups) return [];
    return [...fieldGroups].sort((a, b) => {
      const aSub = a.subtitle?.map[formValues[a.subtitle.field]] || '';
      const bSub = b.subtitle?.map[formValues[b.subtitle.field]] || '';
      if (aSub === 'Pay') return -1;
      if (bSub === 'Pay') return 1;
      return 0;
    });
  }, [fieldGroups, formValues]);

  // ── Grouped rendering path ─────────────────────────────────────────────
  if (hasGroups) {
    return (
      <div className="space-y-2">
        {/* Top ungrouped fields — 3-col grid */}
        {mainTopFields.length > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {mainTopFields.map((field) => (
              <FieldCell
                key={field.id}
                field={field}
                formValues={formValues}
                onFieldChange={onFieldChange}
                isVisible={adjustedFieldVisibility[field.id]}
                isExcluded={!!excludeFieldIds?.has(field.id)}
                children={childFieldMap[field.id]}
                childVisibility={adjustedFieldVisibility}
                excludeFieldIds={excludeFieldIds}
              />
            ))}
            {Array.from({ length: (3 - (mainTopFields.length % 3)) % 3 }).map((_, i) => (
              <div key={`tpad-${i}`} />
            ))}
          </div>
        )}

        {/* Pre-group header fields — 2-col grid aligned with panels */}
        {preGroupFields.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {preGroupFields.map((field) => (
              <FieldCell
                key={field.id}
                field={field}
                formValues={formValues}
                onFieldChange={onFieldChange}
                isVisible={adjustedFieldVisibility[field.id]}
                isExcluded={!!excludeFieldIds?.has(field.id)}
                children={childFieldMap[field.id]}
                childVisibility={adjustedFieldVisibility}
                excludeFieldIds={excludeFieldIds}
              />
            ))}
          </div>
        )}

        {/* Side-by-side group panels — Pay leg always left */}
        <div className="grid grid-cols-2 gap-2">
          {orderedFieldGroups.map((group) => {
            const fields = groupedFieldMap[group.id] || [];
            const subtitleValue = group.subtitle
              ? group.subtitle.map[formValues[group.subtitle.field]] || ''
              : '';
            // Panel visible only when at least one field in the group is visible
            const anyVisible = fields.some((f) => adjustedFieldVisibility[f.id]);
            if (!anyVisible) return <div key={group.id} />;

            return (
              <div
                key={group.id}
                className="rounded-md border border-border/50 bg-muted/10 px-2.5 py-2 space-y-1.5"
              >
                <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                  {group.label}
                  {subtitleValue && (
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-primary uppercase tracking-wide">
                      {subtitleValue}
                    </span>
                  )}
                </div>
                <div className="space-y-1.5">
                  {fields.map((field) => (
                    <FieldCell
                      key={field.id}
                      field={field}
                      formValues={formValues}
                      onFieldChange={onFieldChange}
                      isVisible={adjustedFieldVisibility[field.id]}
                      isExcluded={!!excludeFieldIds?.has(field.id)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom ungrouped fields — 3-col grid */}
        {bottomFields.length > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {bottomFields.map((field) => (
              <FieldCell
                key={field.id}
                field={field}
                formValues={formValues}
                onFieldChange={onFieldChange}
                isVisible={adjustedFieldVisibility[field.id]}
                isExcluded={!!excludeFieldIds?.has(field.id)}
              />
            ))}
            {Array.from({ length: (3 - (bottomFields.length % 3)) % 3 }).map((_, i) => (
              <div key={`bpad-${i}`} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Flat grid rendering (non-grouped templates) ────────────────────────
  return (
    <div className="grid grid-cols-3 gap-2">
      {gridFields.map((field) => (
        <FieldCell
          key={field.id}
          field={field}
          formValues={formValues}
          onFieldChange={onFieldChange}
          isVisible={adjustedFieldVisibility[field.id]}
          isExcluded={!!excludeFieldIds?.has(field.id)}
          children={childFieldMap[field.id]}
          childVisibility={adjustedFieldVisibility}
          excludeFieldIds={excludeFieldIds}
        />
      ))}
      {Array.from({ length: (3 - (gridFields.length % 3)) % 3 }).map((_, i) => (
        <div key={`pad-${i}`} className="h-[calc(14px+28px+4px)]" />
      ))}
    </div>
  );
}
