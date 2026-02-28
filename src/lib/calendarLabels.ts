/**
 * calendarLabels.ts – Converts tenor strings (e.g. "3M", "5Y") into calendar dates.
 *
 * === ROLE IN THE SYSTEM ===
 * When the user sets an Analysis Date, charts show calendar dates beneath tenor
 * labels (e.g. "Jul 2026" under "6M"). Used by EVEChart, NIIChart, and
 * CurvesAndScenariosCard. Supports D/W/M/Y units and ON (overnight = +1 day).
 */
import { addDays, addMonths, addWeeks, addYears, format } from "date-fns";

const TENOR_TOKEN_RE = /^\s*(\d+(?:\.\d+)?)\s*([DWMY])\s*$/i;

export function getCalendarLabelFromMonths(analysisDate: Date, monthsToAdd: number): string {
  return format(addMonths(analysisDate, monthsToAdd), "MMM yyyy");
}

export function getDateFromTenor(analysisDate: Date, tenor: string): Date | null {
  const token = tenor.trim().toUpperCase();
  if (!token) return null;

  if (token === "ON") {
    return addDays(analysisDate, 1);
  }

  const match = TENOR_TOKEN_RE.exec(token);
  if (!match) return null;

  const value = Number.parseFloat(match[1]);
  const unit = match[2].toUpperCase();

  if (!Number.isFinite(value) || value < 0) return null;

  const isWhole = Math.abs(value - Math.round(value)) < 1e-9;

  if (unit === "D") return addDays(analysisDate, Math.round(value));
  if (unit === "W") return isWhole ? addWeeks(analysisDate, value) : addDays(analysisDate, Math.round(value * 7));
  if (unit === "M") return isWhole ? addMonths(analysisDate, value) : addDays(analysisDate, Math.round(value * 30.44));
  if (unit === "Y") return isWhole ? addYears(analysisDate, value) : addDays(analysisDate, Math.round(value * 365.25));
  return null;
}

export function getTenorCalendarDateLabel(
  analysisDate: Date | null | undefined,
  tenor: string,
  pattern: string = "MMM yyyy"
): string | null {
  if (!analysisDate) return null;
  const target = getDateFromTenor(analysisDate, tenor);
  if (!target) return null;
  // Title case: "Feb 2039" → first letter uppercase, rest lowercase
  const raw = format(target, pattern);
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}
