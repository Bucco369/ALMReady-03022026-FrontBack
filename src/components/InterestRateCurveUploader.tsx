import React, { useCallback, useState } from 'react';
import { Upload, TrendingUp, X, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { YieldCurve } from '@/types/financial';
import { parseYieldCurveCSV, generateSampleYieldCurveCSV } from '@/lib/csvParser';

interface InterestRateCurveUploaderProps {
  curves: YieldCurve[];
  selectedBaseCurve: string | null;
  selectedDiscountCurve: string | null;
  onCurvesChange: (curves: YieldCurve[]) => void;
  onBaseCurveSelect: (curveId: string) => void;
  onDiscountCurveSelect: (curveId: string) => void;
}

export function InterestRateCurveUploader({
  curves,
  selectedBaseCurve,
  selectedDiscountCurve,
  onCurvesChange,
  onBaseCurveSelect,
  onDiscountCurveSelect,
}: InterestRateCurveUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleFileUpload = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        const curveName = file.name.replace('.csv', '');
        const parsed = parseYieldCurveCSV(content, curveName);
        const newCurves = [...curves, parsed];
        onCurvesChange(newCurves);
        
        // Auto-select if first curve
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

  const handleRemoveCurve = useCallback(
    (curveId: string) => {
      onCurvesChange(curves.filter((c) => c.id !== curveId));
    },
    [curves, onCurvesChange]
  );

  const formatPercent = (num: number) => {
    return (num * 100).toFixed(2) + '%';
  };

  const selectedCurve = curves.find((c) => c.id === selectedBaseCurve);

  return (
    <div className="section-card animate-fade-in">
      <div className="section-header">
        <TrendingUp className="h-5 w-5 text-primary" />
        Interest Rate Curves
      </div>

      <div
        className={`upload-zone mb-4 ${isDragging ? 'active' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="mb-1 text-sm font-medium text-foreground">
          Upload yield curve CSV
        </p>
        <p className="mb-3 text-xs text-muted-foreground">
          Format: tenor, rate (e.g., 1Y, 0.05)
        </p>
        <div className="flex gap-2">
          <label>
            <Input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleInputChange}
            />
            <Button variant="outline" size="sm" asChild>
              <span>Browse Files</span>
            </Button>
          </label>
          <Button variant="ghost" size="sm" onClick={handleDownloadSample}>
            <Download className="mr-1 h-4 w-4" />
            Sample CSV
          </Button>
        </div>
      </div>

      {curves.length > 0 && (
        <>
          <div className="mb-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground">
                Base Curve
              </label>
              <Select value={selectedBaseCurve || ''} onValueChange={onBaseCurveSelect}>
                <SelectTrigger className="bg-card">
                  <SelectValue placeholder="Select base curve" />
                </SelectTrigger>
                <SelectContent className="bg-card">
                  {curves.map((curve) => (
                    <SelectItem key={curve.id} value={curve.id}>
                      {curve.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground">
                Discount Curve
              </label>
              <Select value={selectedDiscountCurve || ''} onValueChange={onDiscountCurveSelect}>
                <SelectTrigger className="bg-card">
                  <SelectValue placeholder="Select discount curve" />
                </SelectTrigger>
                <SelectContent className="bg-card">
                  {curves.map((curve) => (
                    <SelectItem key={curve.id} value={curve.id}>
                      {curve.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {curves.map((curve) => (
              <div
                key={curve.id}
                className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs ${
                  curve.id === selectedBaseCurve
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-muted text-muted-foreground'
                }`}
              >
                {curve.name}
                <button
                  onClick={() => handleRemoveCurve(curve.id)}
                  className="ml-1 rounded-full p-0.5 hover:bg-destructive/20"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={handleClear} className="text-xs">
              Clear All
            </Button>
          </div>

          {selectedCurve && (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="data-table">
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
                      <td className="text-right font-mono">
                        {formatPercent(point.rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
