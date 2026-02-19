/**
 * BalancePositionsCardConnected.tsx – "Smart" wrapper connecting
 * BalancePositionsCard (pure UI) to the backend API and session system.
 *
 * === ROLE IN THE SYSTEM ===
 * Bridge between backend balance APIs and the presentational card. Handles:
 * 1. SESSION MANAGEMENT: useSession() + withSessionRetry() for stale sessions.
 * 2. EXCEL UPLOAD: Intercepts file/drop events, uploads to backend, refreshes tree.
 * 3. SUMMARY → POSITIONS MAPPING: Converts BalanceSummaryResponse → Position[].
 *    This mapping is LOSSY (one Position per sheet, not per contract).
 * 4. PERSISTENCE MARKER: localStorage remembers uploads across page refreshes.
 *
 * === CURRENT LIMITATIONS ===
 * - LOSSY MAPPING: mapSummaryToPositions() creates one Position per sheet with
 *   sheet-level totals. Phase 1 backend engine reads canonical_rows directly.
 * - DEFAULT MATURITY: All positions get "2030-12-31" as placeholder maturity.
 * - EVENT INTERCEPTION: Uses onChangeCapture/onDropCapture to intercept events
 *   before child component handles them – pragmatic backend integration pattern.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { BalancePositionsCard } from "@/components/BalancePositionsCard";
import {
  getBalanceSummary,
  getUploadProgress,
  uploadBalanceExcel,
  uploadBalanceZip,
  type BalanceSummaryResponse,
} from "@/lib/api";
import { inferCategoryFromSheetName } from "@/lib/balanceUi";
import { generateSamplePositionsCSV, parsePositionsCSV } from "@/lib/csvParser";
import type { Position } from "@/types/financial";

interface BalancePositionsCardConnectedProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
  sessionId: string | null;
}

const DEFAULT_MATURITY_DATE = "2030-12-31";
const BALANCE_UPLOADED_SESSION_KEY = "almready_balance_uploaded_session_id";

function isExcelFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return lower.endsWith(".xlsx") || lower.endsWith(".xls");
}

function isZipFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".zip");
}

function isBalanceFile(file: File): boolean {
  return isExcelFile(file) || isZipFile(file);
}

function isNoBalanceUploadedError(error: unknown): boolean {
  const message = (error instanceof Error ? error.message : String(error)).toLowerCase();
  return message.includes("no balance uploaded");
}

function getUploadedSessionMarker(): string | null {
  return localStorage.getItem(BALANCE_UPLOADED_SESSION_KEY);
}

function setUploadedSessionMarker(sessionId: string): void {
  localStorage.setItem(BALANCE_UPLOADED_SESSION_KEY, sessionId);
}

function clearUploadedSessionMarker(): void {
  localStorage.removeItem(BALANCE_UPLOADED_SESSION_KEY);
}

function isCurrentSessionKnownUploaded(sessionId: string | null): boolean {
  if (!sessionId) return false;
  return getUploadedSessionMarker() === sessionId;
}

function mapSummaryToPositions(summary: BalanceSummaryResponse): Position[] {
  if (summary.sheets.length === 0) return [];

  return summary.sheets.map((sheet, index) => {
    const category = inferCategoryFromSheetName(sheet.sheet);

    return {
      id: `backend-sheet-${index}`,
      instrumentType: category === "liability" ? "Liability" : "Asset",
      description: sheet.sheet,
      notional: sheet.total_saldo_ini ?? sheet.total_book_value ?? 0,
      maturityDate: DEFAULT_MATURITY_DATE,
      couponRate: sheet.avg_tae ?? 0,
      repriceFrequency: "Annual",
      currency: "EUR",
    };
  });
}

export function BalancePositionsCardConnected({
  positions,
  onPositionsChange,
  sessionId,
}: BalancePositionsCardConnectedProps) {
  const [balanceSummary, setBalanceSummary] = useState<BalanceSummaryResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshSummary = useCallback(async () => {
    if (!sessionId) return;
    try {
      const summary = await getBalanceSummary(sessionId);
      setUploadedSessionMarker(summary.session_id);
      setBalanceSummary(summary);
      onPositionsChange(mapSummaryToPositions(summary));
    } catch (error) {
      if (isNoBalanceUploadedError(error)) {
        clearUploadedSessionMarker();
        setBalanceSummary(null);
        return;
      }
      console.error(
        "[BalancePositionsCardConnected] failed to refresh balance summary",
        error
      );
    }
  }, [onPositionsChange, sessionId]);

  useEffect(() => {
    if (positions.length > 0) return;
    if (!isCurrentSessionKnownUploaded(sessionId)) return;
    void refreshSummary();
  }, [sessionId, positions.length, refreshSummary]);

  const handleBalanceUpload = useCallback(
    async (file: File) => {
      if (!sessionId) return;

      // Cancel any leftover poll timer from a previous upload.
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }

      setIsUploading(true);
      setUploadProgress(0);

      // Once bytes are sent, start polling the backend for real progress.
      const startPolling = () => {
        if (pollTimerRef.current) return; // guard double-fire
        pollTimerRef.current = setInterval(async () => {
          try {
            const p = await getUploadProgress(sessionId);
            if (p.phase !== "idle") {
              setUploadProgress(p.pct);
            }
          } catch {
            // Ignore transient poll errors; upload XHR will report real failures.
          }
        }, 500);
      };

      try {
        const onProgress = (pct: number) => setUploadProgress(pct); // 0→80 (XHR bytes)
        if (isZipFile(file)) {
          await uploadBalanceZip(sessionId, file, onProgress, startPolling);
        } else {
          await uploadBalanceExcel(sessionId, file, onProgress, startPolling);
        }

        // Server responded → stop polling and complete.
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
        setUploadProgress(100);
        setUploadedSessionMarker(sessionId);
        await refreshSummary();
      } catch (error) {
        console.error(
          "[BalancePositionsCardConnected] failed to upload balance",
          error
        );
      } finally {
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
        setIsUploading(false);
        setUploadProgress(0);
      }
    },
    [refreshSummary, sessionId]
  );

  const handleChangeCapture = useCallback(
    (event: React.FormEvent<HTMLDivElement>) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "file") return;

      const file = target.files?.[0];
      if (!file || !isBalanceFile(file)) return;

      event.preventDefault();
      event.stopPropagation();
      target.value = "";
      void handleBalanceUpload(file);
    },
    [handleBalanceUpload]
  );

  const handleDropCapture = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      const file = event.dataTransfer.files?.[0];
      if (!file || !isBalanceFile(file)) return;

      event.preventDefault();
      void handleBalanceUpload(file);
    },
    [handleBalanceUpload]
  );

  const loadSampleIntoBalance = useCallback(() => {
    clearUploadedSessionMarker();
    setBalanceSummary(null);
    onPositionsChange(parsePositionsCSV(generateSamplePositionsCSV()));
  }, [onPositionsChange]);

  const handleClickCapture = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const sampleButton = target.closest("button");
    if (
      sampleButton &&
      sampleButton.textContent?.trim() === "Sample"
    ) {
      event.preventDefault();
      event.stopPropagation();
      loadSampleIntoBalance();
      return;
    }

    const resetButton = target.closest('button[title="Reset all"]');
    if (!resetButton) return;

    clearUploadedSessionMarker();
    setBalanceSummary(null);
  }, [loadSampleIntoBalance]);

  return (
    <div
      className="h-full min-h-0 [&>*]:h-full [&>*]:min-h-0 [&_.lucide-download]:hidden"
      onChangeCapture={handleChangeCapture}
      onDropCapture={handleDropCapture}
      onClickCapture={handleClickCapture}
    >
      <BalancePositionsCard
        positions={positions}
        onPositionsChange={onPositionsChange}
        sessionId={sessionId}
        summaryTree={balanceSummary?.summary_tree ?? null}
        isUploading={isUploading}
        uploadProgress={uploadProgress}
      />
    </div>
  );
}
