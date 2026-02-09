import React, { useState, useEffect, useMemo } from 'react';
import { Brain, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  useBehavioural,
  BehaviouralProfile,
  NMDParameters,
  LoanPrepaymentParameters,
  TermDepositParameters,
  NMD_BUCKET_DISTRIBUTION,
  MAX_TOTAL_MATURITY,
} from './BehaviouralContext';
import { NMDCashflowChart } from './NMDCashflowChart';

interface BehaviouralAssumptionsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BehaviouralAssumptionsModal({
  open,
  onOpenChange,
}: BehaviouralAssumptionsModalProps) {
  const {
    activeProfile,
    setActiveProfile,
    nmdParams,
    setNmdParams,
    loanPrepaymentParams,
    setLoanPrepaymentParams,
    termDepositParams,
    setTermDepositParams,
    applyAssumptions,
  } = useBehavioural();

  // Local state for editing (to allow cancel without saving)
  const [localProfile, setLocalProfile] = useState<BehaviouralProfile>(activeProfile);
  const [localNmdParams, setLocalNmdParams] = useState<NMDParameters>(nmdParams);
  const [localLoanParams, setLocalLoanParams] = useState<LoanPrepaymentParameters>(loanPrepaymentParams);
  const [localTermParams, setLocalTermParams] = useState<TermDepositParameters>(termDepositParams);
  const [detailsOpen, setDetailsOpen] = useState(false);

  // Sync local state when modal opens
  useEffect(() => {
    if (open) {
      setLocalProfile(activeProfile);
      setLocalNmdParams(nmdParams);
      setLocalLoanParams(loanPrepaymentParams);
      setLocalTermParams(termDepositParams);
    }
  }, [open, activeProfile, nmdParams, loanPrepaymentParams, termDepositParams]);

  // Calculate local total average maturity for NMD
  const localTotalMaturity = useMemo(() => {
    return (localNmdParams.coreProportion / 100) * localNmdParams.coreAverageMaturity;
  }, [localNmdParams.coreProportion, localNmdParams.coreAverageMaturity]);

  const localIsValidMaturity = localTotalMaturity <= MAX_TOTAL_MATURITY;

  // Calculate local CPR from SMM
  const localCpr = useMemo(() => {
    const smm = localLoanParams.smm / 100;
    const cprDecimal = 1 - Math.pow(1 - smm, 12);
    return cprDecimal * 100;
  }, [localLoanParams.smm]);

  // Calculate local annual TDRR
  const localAnnualTdrr = useMemo(() => {
    const monthly = localTermParams.tdrr / 100;
    const annualDecimal = 1 - Math.pow(1 - monthly, 12);
    return annualDecimal * 100;
  }, [localTermParams.tdrr]);

  // NMD handlers
  const handleCoreProportion = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setLocalNmdParams(prev => ({
        ...prev,
        coreProportion: Math.max(0, Math.min(100, num)),
      }));
    }
  };

  const handleCoreMaturity = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setLocalNmdParams(prev => ({
        ...prev,
        coreAverageMaturity: Math.max(2, Math.min(10, num)),
      }));
    }
  };

  const handlePassThrough = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setLocalNmdParams(prev => ({
        ...prev,
        passThrough: Math.max(0, Math.min(100, num)),
      }));
    }
  };

  // Loan Prepayment handlers
  const handleSmm = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setLocalLoanParams(prev => ({
        ...prev,
        smm: Math.max(0, Math.min(50, num)),
      }));
    }
  };

  // Term Deposit handlers
  const handleTdrr = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setLocalTermParams(prev => ({
        ...prev,
        tdrr: Math.max(0, Math.min(50, num)),
      }));
    }
  };

  const handleApply = () => {
    if (localProfile === 'nmd' && localNmdParams.enabled && !localIsValidMaturity) {
      return; // Prevent apply if NMD maturity invalid
    }
    setActiveProfile(localProfile);
    setNmdParams(localNmdParams);
    setLoanPrepaymentParams(localLoanParams);
    setTermDepositParams(localTermParams);
    applyAssumptions();
    onOpenChange(false);
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-primary" />
            Behavioural Assumptions
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            Affect repricing and timing of cash flows
          </p>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Profile Selector */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">Profile</Label>
            <Select
              value={localProfile}
              onValueChange={(value: BehaviouralProfile) => setLocalProfile(value)}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select behavioural profile" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none" className="text-xs">None (default)</SelectItem>
                <SelectItem value="nmd" className="text-xs">Non-Maturing Deposits (NMDs)</SelectItem>
                <SelectItem value="loan-prepayments" className="text-xs">Loan Prepayments</SelectItem>
                <SelectItem value="term-deposits" className="text-xs">Term Deposits</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* NMD Configuration Panel */}
          {localProfile === 'nmd' && (
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-4">
              {/* Activation Toggle */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="nmd-enabled"
                  checked={localNmdParams.enabled}
                  onCheckedChange={(checked) =>
                    setLocalNmdParams(prev => ({ ...prev, enabled: !!checked }))
                  }
                />
                <Label htmlFor="nmd-enabled" className="text-xs font-medium cursor-pointer">
                  Apply behavioural assumptions to NMDs
                </Label>
              </div>

              {localNmdParams.enabled && (
                <div className="space-y-4 pt-2 border-t border-border/50">
                  <p className="text-[10px] text-muted-foreground italic">
                    All parameters apply to the aggregate of all NMDs (no segmentation).
                  </p>

                  {/* Parameter 1: Core Proportion */}
                  <div className="space-y-1">
                    <Label className="text-xs font-medium">Core proportion (%)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={localNmdParams.coreProportion}
                      onChange={(e) => handleCoreProportion(e.target.value)}
                      className="h-8 text-xs w-24"
                    />
                  </div>

                  {/* Parameter 2: Core Average Maturity */}
                  <div className="space-y-1">
                    <Label className="text-xs font-medium">Core average maturity (years)</Label>
                    <div className="flex items-start gap-4">
                      <Input
                        type="number"
                        min={2}
                        max={10}
                        step={0.25}
                        value={localNmdParams.coreAverageMaturity}
                        onChange={(e) => handleCoreMaturity(e.target.value)}
                        className="h-8 text-xs w-24"
                      />
                      
                      {/* Calculated Total Maturity */}
                      <div className={`flex-1 rounded-md p-2 text-xs ${
                        localIsValidMaturity 
                          ? 'bg-muted/50 border border-border/50' 
                          : 'bg-destructive/10 border border-destructive/30'
                      }`}>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Total average maturity (core + non-core):</span>
                          <span className={`font-semibold ${!localIsValidMaturity ? 'text-destructive' : ''}`}>
                            {localTotalMaturity.toFixed(2)} years
                          </span>
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          Max allowed: {MAX_TOTAL_MATURITY.toFixed(2)} years
                        </div>
                        {!localIsValidMaturity && (
                          <div className="flex items-center gap-1 mt-1.5 text-destructive">
                            <AlertTriangle className="h-3 w-3" />
                            <span className="text-[10px] font-medium">Exceeds supervisory limit (5 years)</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Parameter 3: Pass-through */}
                  <div className="space-y-1">
                    <Label className="text-xs font-medium">Rate pass-through (%)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={localNmdParams.passThrough}
                      onChange={(e) => handlePassThrough(e.target.value)}
                      className="h-8 text-xs w-24"
                    />
                  </div>

                  {/* Additional Details - Collapsible */}
                  <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
                    <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors">
                      {detailsOpen ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                      Additional details
                    </CollapsibleTrigger>
                    <CollapsibleContent className="pt-3">
                      <NMDCashflowChart
                        coreProportion={localNmdParams.coreProportion}
                        coreAverageMaturity={localNmdParams.coreAverageMaturity}
                      />
                      <p className="text-[10px] text-muted-foreground mt-2 italic">
                        The shape of the behavioural maturity profile is fixed.
                        The selected core maturity scales the overall timing of cash flows.
                      </p>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              )}
            </div>
          )}

          {/* Loan Prepayments Configuration Panel */}
          {localProfile === 'loan-prepayments' && (
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-4">
              {/* Activation Toggle */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="loan-enabled"
                  checked={localLoanParams.enabled}
                  onCheckedChange={(checked) =>
                    setLocalLoanParams(prev => ({ ...prev, enabled: !!checked }))
                  }
                />
                <Label htmlFor="loan-enabled" className="text-xs font-medium cursor-pointer">
                  Apply behavioural assumptions to Loan Prepayments
                </Label>
              </div>

              {localLoanParams.enabled && (
                <div className="space-y-4 pt-2 border-t border-border/50">
                  <p className="text-[10px] text-muted-foreground italic">
                    Applies to the aggregate loan portfolio (no segmentation).
                  </p>

                  {/* Parameter: SMM */}
                  <div className="space-y-1">
                    <Label className="text-xs font-medium">SMM – Single Monthly Mortality (monthly) (%)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={50}
                      step={0.01}
                      value={localLoanParams.smm}
                      onChange={(e) => handleSmm(e.target.value)}
                      className="h-8 text-xs w-24"
                    />
                  </div>

                  {/* Calculated CPR */}
                  <div className="rounded-md p-2 text-xs bg-muted/50 border border-border/50">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Equivalent CPR (annual):</span>
                      <span className="font-semibold">{localCpr.toFixed(2)} %</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      Annualized using CPR = 1 − (1 − SMM)<sup>12</sup>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Term Deposits Configuration Panel */}
          {localProfile === 'term-deposits' && (
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-4">
              {/* Activation Toggle */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="term-enabled"
                  checked={localTermParams.enabled}
                  onCheckedChange={(checked) =>
                    setLocalTermParams(prev => ({ ...prev, enabled: !!checked }))
                  }
                />
                <Label htmlFor="term-enabled" className="text-xs font-medium cursor-pointer">
                  Apply behavioural assumptions to Term Deposits
                </Label>
              </div>

              {localTermParams.enabled && (
                <div className="space-y-4 pt-2 border-t border-border/50">
                  <p className="text-[10px] text-muted-foreground italic">
                    Applies to the aggregate term deposit portfolio.
                  </p>

                  {/* Parameter: TDRR */}
                  <div className="space-y-1">
                    <Label className="text-xs font-medium">TDRR – Term Deposit Redemption Rate (monthly) (%)</Label>
                    <Input
                      type="number"
                      min={0}
                      max={50}
                      step={0.01}
                      value={localTermParams.tdrr}
                      onChange={(e) => handleTdrr(e.target.value)}
                      className="h-8 text-xs w-24"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Monthly early redemption rate for term deposits.
                    </p>
                  </div>

                  {/* Calculated Annual TDRR */}
                  <div className="rounded-md p-2 text-xs bg-muted/50 border border-border/50">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Equivalent annual TDRR:</span>
                      <span className="font-semibold">{localAnnualTdrr.toFixed(2)} %</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      Annualized using: 1 − (1 − monthly rate)<sup>12</sup>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Empty state for None profile */}
          {localProfile === 'none' && (
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-xs">No behavioural assumptions selected.</p>
              <p className="text-[10px] mt-1">Select a profile to configure behavioural parameters.</p>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" size="sm" onClick={handleCancel} className="text-xs">
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleApply}
            disabled={localProfile === 'nmd' && localNmdParams.enabled && !localIsValidMaturity}
            className="text-xs"
          >
            Apply assumptions
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}