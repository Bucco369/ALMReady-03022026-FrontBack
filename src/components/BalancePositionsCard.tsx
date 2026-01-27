import React, { useCallback, useState } from 'react';
import { Upload, FileSpreadsheet, Eye, RefreshCw, Download, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { Position } from '@/types/financial';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';

interface BalancePositionsCardProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
}

export function BalancePositionsCard({ positions, onPositionsChange }: BalancePositionsCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const handleFileUpload = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        const parsed = parsePositionsCSV(content);
        onPositionsChange(parsed);
        setFileName(file.name);
      };
      reader.readAsText(file);
    },
    [onPositionsChange]
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
    const content = generateSamplePositionsCSV();
    const blob = new Blob([content], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample_positions.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const handleReplace = useCallback(() => {
    onPositionsChange([]);
    setFileName(null);
  }, [onPositionsChange]);

  const assetCount = positions.filter(p => p.instrumentType === 'Asset').length;
  const liabilityCount = positions.filter(p => p.instrumentType === 'Liability').length;
  const totalNotional = positions.reduce((sum, p) => sum + Math.abs(p.notional), 0);

  const formatNotional = (num: number) => {
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toString();
  };

  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatPercent = (num: number) => (num * 100).toFixed(2) + '%';

  const isLoaded = positions.length > 0;

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <FileSpreadsheet className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Balance Positions</span>
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
                <MetricBox label="Positions" value={positions.length.toString()} />
                <MetricBox label="Notional" value={formatNotional(totalNotional)} />
                <MetricBox label="Assets" value={assetCount.toString()} variant="success" />
                <MetricBox label="Liabilities" value={liabilityCount.toString()} variant="muted" />
              </div>
              
              <div className="flex gap-1.5 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDetails(true)}
                  className="flex-1 h-6 text-xs"
                >
                  <Eye className="mr-1 h-3 w-3" />
                  View details
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReplace}
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
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              Balance Positions ({positions.length})
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-auto flex-1">
            <table className="data-table text-xs">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Description</th>
                  <th className="text-right">Notional</th>
                  <th>Maturity</th>
                  <th className="text-right">Rate</th>
                  <th>Reprice</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.id}>
                    <td>
                      <span
                        className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          position.instrumentType === 'Asset'
                            ? 'bg-success/10 text-success'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {position.instrumentType}
                      </span>
                    </td>
                    <td className="font-medium">{position.description}</td>
                    <td className="text-right font-mono">{formatCurrency(position.notional)}</td>
                    <td className="font-mono">{position.maturityDate}</td>
                    <td className="text-right font-mono">{formatPercent(position.couponRate)}</td>
                    <td className="text-muted-foreground">{position.repriceFrequency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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

function MetricBox({ label, value, variant = 'default' }: { label: string; value: string; variant?: 'default' | 'success' | 'muted' }) {
  const valueClass = variant === 'success' 
    ? 'text-success' 
    : variant === 'muted' 
      ? 'text-muted-foreground' 
      : 'text-foreground';
  
  return (
    <div className="rounded-md bg-muted/50 px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={`text-sm font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}
