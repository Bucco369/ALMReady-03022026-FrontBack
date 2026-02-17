/**
 * calendarLabels.ts – Converts tenor strings (e.g. "3M", "5Y") into calendar dates.
 *
 * === ROLE IN THE SYSTEM ===
 * When the user sets an Analysis Date, charts show calendar dates beneath tenor
 * labels (e.g. "Jul 2026" under "6M"). Used by EVEChart, NIIChart, and
 * CurvesAndScenariosCard. Supports D/W/M/Y units and ON (overnight = +1 day).
 */
import { addDays, addMonths, addWeeks, addYears, format } from "date-fns";

const TENOR_TOKEN_RE = /^\s*(\d+)\s*([DWMY])\s*$/i;

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

  const value = Number.parseInt(match[1], 10);
  const unit = match[2].toUpperCase();

  if (!Number.isFinite(value) || value < 0) return null;

  if (unit === "D") return addDays(analysisDate, value);
  if (unit === "W") return addWeeks(analysisDate, value);
  if (unit === "M") return addMonths(analysisDate, value);
  if (unit === "Y") return addYears(analysisDate, value);
  return null;
}

export function getTenorCalendarDateLabel(
  analysisDate: Date | null | undefined,
  tenor: string,
  pattern: string = "yyyy-MM-dd"
): string | null {
  if (!analysisDate) return null;
  const target = getDateFromTenor(analysisDate, tenor);
  if (!target) return null;
  return format(target, pattern);
}
