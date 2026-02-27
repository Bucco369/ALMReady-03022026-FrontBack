/** Shared formatting utilities for balance details modals. */

export function formatAmount(num: number) {
  const millions = num / 1e6;
  return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '\u20AC';
}

export function formatPercent(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '\u2014';
  return (num * 100).toFixed(2) + '%';
}

export function formatMaturity(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '\u2014';
  return `${num.toFixed(1)}Y`;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export function toTitleCase(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase())
    .join(' ');
}

export function compactValues(values: string[], max = 2): string {
  if (values.length <= max) return values.join(' ');
  return `${values.slice(0, max).join(' ')} +${values.length - max}`;
}
