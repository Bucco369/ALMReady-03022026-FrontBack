import React, { useCallback, useState } from 'react';
import { Upload, FileSpreadsheet, X, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Position } from '@/types/financial';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';

interface BalanceUploaderProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
}

export function BalanceUploader({ positions, onPositionsChange }: BalanceUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

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

  const handleCellEdit = useCallback(
    (id: string, field: keyof Position, value: string | number) => {
      onPositionsChange(
        positions.map((p) =>
          p.id === id ? { ...p, [field]: value } : p
        )
      );
    },
    [positions, onPositionsChange]
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

  const handleClear = useCallback(() => {
    onPositionsChange([]);
    setFileName(null);
  }, [onPositionsChange]);

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'decimal',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatPercent = (num: number) => {
    return (num * 100).toFixed(2) + '%';
  };

  return (
    <div className="section-card animate-fade-in">
      <div className="section-header">
        <FileSpreadsheet className="h-5 w-5 text-primary" />
        Balance Positions
      </div>

      {positions.length === 0 ? (
        <div
          className={`upload-zone ${isDragging ? 'active' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          <Upload className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="mb-2 text-sm font-medium text-foreground">
            Drop your CSV file here, or click to browse
          </p>
          <p className="mb-4 text-xs text-muted-foreground">
            Supports: id, instrumentType, description, notional, maturityDate, couponRate, repriceFrequency, currency
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
      ) : (
        <>
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {fileName || 'Positions loaded'} • {positions.length} items
              </span>
            </div>
            <Button variant="ghost" size="sm" onClick={handleClear}>
              <X className="mr-1 h-4 w-4" />
              Clear
            </Button>
          </div>
          
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="data-table">
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
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          position.instrumentType === 'Asset'
                            ? 'bg-success/10 text-success'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {position.instrumentType}
                      </span>
                    </td>
                    <td>
                      <Input
                        value={position.description}
                        onChange={(e) =>
                          handleCellEdit(position.id, 'description', e.target.value)
                        }
                        className="h-8 border-0 bg-transparent p-0 text-sm focus-visible:ring-0"
                      />
                    </td>
                    <td className="text-right font-mono">
                      {formatNumber(position.notional)}
                    </td>
                    <td className="font-mono text-xs">
                      {position.maturityDate}
                    </td>
                    <td className="text-right font-mono">
                      {formatPercent(position.couponRate)}
                    </td>
                    <td className="text-xs text-muted-foreground">
                      {position.repriceFrequency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
