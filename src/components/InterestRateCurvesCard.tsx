import React, { useCallback, useState } from 'react';
import { Upload, TrendingUp, Eye, RefreshCw, Download, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { YieldCurve } from '@/types/financial';
import { parseYieldCurveCSV, generateSampleYieldCurveCSV } from '@/lib/csvParser';

interface InterestRateCurvesCardProps {
  curves: YieldCurve[];
  selectedBaseCurve: string | null;
  selectedDiscountCurve: string | null;
  onCurvesChange: (curves: YieldCurve[]) => void;
  onBaseCurveSelect: (curveId: string) => void;
  onDiscountCurveSelect: (curveId: string) => void;
}

export function InterestRateCurvesCard({
  curves,
  selectedBaseCurve,
  selectedDiscountCurve,
  onCurvesChange,
  onBaseCurveSelect,
  onDiscountCurveSelect,
}: InterestRateCurvesCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const handleFileUpload = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        const curveName = file.name.replace('.csv', '');
        const parsed = parseYieldCurveCSV(content, curveName);
        const newCurves = [...curves, parsed];
        onCurvesChange(newCurves);

        if (curves.length === 0) {
          onBaseCurveSelect(parsed.id);
          onDiscountCurveSelect(parsed.id);
        }
      };
      reader.readAsText(file);
    },
    [curves, onCurvesChange, onBaseCurveSelect, onDiscountCurveSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.csv')) {
        handleFileUpload(file);
      }
    },
    [handleFileUpload]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFileUpload(file);
      }
    },
    [handleFileUpload]
  );

  const handleDownloadSample = useCallback(() => {
    const content = generateSampleYieldCurveCSV();
    const blob = new Blob([content], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample_yield_curve.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const handleClear = useCallback(() => {
    onCurvesChange([]);
  }, [onCurvesChange]);

  const selectedCurve = curves.find((c) => c.id === selectedBaseCurve);
  const tenorCount = selectedCurve?.points.length ?? 0;
  const isLoaded = curves.length > 0;
  const hasBaseCurve = selectedBaseCurve !== null;
  const hasDiscountCurve = selectedDiscountCurve !== null;

  const formatPercent = (num: number) => (num * 100).toFixed(2) + '%';

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Interest Rate Curves</span>
          </div>
          <StatusIndicator loaded={isLoaded} />
        </div>

        <div className="dashboard-card-content">
          {!isLoaded ? (
            <div
              className={`compact-upload-zone ${isDragging ? 'active' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <Upload className="h-5 w-5 text-muted-foreground mb-1" />
              <p className="text-xs text-muted-foreground mb-2">Drop CSV or click to upload</p>
              <div className="flex gap-1.5">
                <label>
                  <Input
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={handleInputChange}
                  />
                  <Button variant="outline" size="sm" asChild className="h-6 text-xs px-2">
                    <span>Browse</span>
                  </Button>
                </label>
                <Button variant="ghost" size="sm" onClick={handleDownloadSample} className="h-6 text-xs px-2">
                  <Download className="mr-1 h-3 w-3" />
                  Sample
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <MetricBox label="Curves" value={curves.length.toString()} />
                <MetricBox label="Tenors" value={tenorCount.toString()} />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <CurveStatus label="Base" selected={hasBaseCurve} name={selectedCurve?.name} />
                </div>
                <div className="flex items-center gap-2">
                  <CurveStatus label="Discount" selected={hasDiscountCurve} name={curves.find(c => c.id === selectedDiscountCurve)?.name} />
                </div>
              </div>
              
              <div className="flex gap-1.5 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDetails(true)}
                  className="flex-1 h-6 text-xs"
                >
                  <Eye className="mr-1 h-3 w-3" />
                  View curves
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClear}
                  className="h-6 text-xs px-2"
                >
                  <RefreshCw className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Interest Rate Curves
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Base Curve
                </label>
                <Select value={selectedBaseCurve || ''} onValueChange={onBaseCurveSelect}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select" />
                  </SelectTrigger>
                  <SelectContent>
                    {curves.map((curve) => (
                      <SelectItem key={curve.id} value={curve.id} className="text-xs">
                        {curve.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Discount Curve
                </label>
                <Select value={selectedDiscountCurve || ''} onValueChange={onDiscountCurveSelect}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select" />
                  </SelectTrigger>
                  <SelectContent>
                    {curves.map((curve) => (
                      <SelectItem key={curve.id} value={curve.id} className="text-xs">
                        {curve.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {selectedCurve && (
              <div className="overflow-auto max-h-[40vh]">
                <table className="data-table text-xs">
                  <thead>
                    <tr>
                      <th>Tenor</th>
                      <th className="text-right">Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedCurve.points.map((point, index) => (
                      <tr key={index}>
                        <td className="font-mono">{point.tenor}</td>
                        <td className="text-right font-mono">{formatPercent(point.rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusIndicator({ loaded }: { loaded: boolean }) {
  return loaded ? (
    <div className="flex items-center gap-1 text-success">
      <CheckCircle2 className="h-3 w-3" />
      <span className="text-[10px] font-medium">Loaded</span>
    </div>
  ) : (
    <div className="flex items-center gap-1 text-muted-foreground">
      <XCircle className="h-3 w-3" />
      <span className="text-[10px] font-medium">Not loaded</span>
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted/50 px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-foreground">{value}</div>
    </div>
  );
}

function CurveStatus({ label, selected, name }: { label: string; selected: boolean; name?: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {selected ? (
        <CheckCircle2 className="h-3 w-3 text-success shrink-0" />
      ) : (
        <XCircle className="h-3 w-3 text-muted-foreground shrink-0" />
      )}
      <span className="text-muted-foreground">{label}:</span>
      <span className={selected ? 'text-foreground font-medium truncate' : 'text-muted-foreground'}>
        {name || 'Not selected'}
      </span>
    </div>
  );
}
