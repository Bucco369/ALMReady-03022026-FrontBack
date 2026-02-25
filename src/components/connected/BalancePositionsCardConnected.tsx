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
 * 4. HYDRATION: Backend-provided hasBalance flag triggers auto-load on mount.
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
  deleteBalance,
  getBalanceSummary,
  getUploadProgress,
  uploadBalanceExcel,
  uploadBalanceZip,
  type BalanceSummaryResponse,
} from "@/lib/api";

import { useSmoothProgress } from "@/hooks/useSmoothProgress";
import { toast } from "sonner";
import { inferCategoryFromSheetName } from "@/lib/balanceUi";
import { generateSamplePositionsCSV, parsePositionsCSV } from "@/lib/csvParser";
import type { Position } from "@/types/financial";

interface BalancePositionsCardConnectedProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
  sessionId: string | null;
  hasBalance: boolean;
  onDataReset?: () => void;
}

const DEFAULT_MATURITY_DATE = "2030-12-31";

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
  hasBalance,
  onDataReset,
}: BalancePositionsCardConnectedProps) {
  const [balanceSummary, setBalanceSummary] = useState<BalanceSummaryResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState("");
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const smoothProgress = useSmoothProgress(uploadProgress, isUploading);

  const refreshSummary = useCallback(async () => {
    if (!sessionId) return;
    try {
      const summary = await getBalanceSummary(sessionId);
      setBalanceSummary(summary);
      onPositionsChange(mapSummaryToPositions(summary));
    } catch (error) {
      if (isNoBalanceUploadedError(error)) {
        setBalanceSummary(null);
        return;
      }
      console.error(
        "[BalancePositionsCardConnected] failed to refresh balance summary",
        error
      );
      toast.error("Failed to load balance data", {
        description: "Could not refresh balance data from server.",
      });
    }
  }, [onPositionsChange, sessionId]);

  const refreshSummaryRef = useRef(refreshSummary);
  useEffect(() => {
    refreshSummaryRef.current = refreshSummary;
  }, [refreshSummary]);

  useEffect(() => {
    if (positions.length > 0) return;
    if (!hasBalance) return;
    void refreshSummaryRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, hasBalance, positions.length]);

  const handleBalanceUpload = useCallback(
    async (file: File) => {
      if (!sessionId) return;

      // Cancel any leftover poll loop from a previous upload.
      pollTimerRef.current = null;

      setIsUploading(true);
      setUploadProgress(0);
      setUploadPhase("Uploading file…");

      // Once bytes are sent, start polling the backend for real progress.
      // Uses a sequential loop (wait for response before next poll) to avoid
      // flooding Chrome's connection pool when the server is busy parsing.
      const startPolling = () => {
        if (pollTimerRef.current) return; // guard double-fire
        // Use a sentinel value so the ref is truthy (guards double-fire).
        pollTimerRef.current = setTimeout(() => {}, 0);

        (async () => {
          while (pollTimerRef.current !== null) {
            try {
              const controller = new AbortController();
              const timeout = setTimeout(() => controller.abort(), 4000);
              const p = await getUploadProgress(sessionId);
              clearTimeout(timeout);
              if (p.phase !== "idle") {
                setUploadProgress(prev => Math.max(prev, p.pct));
                if (p.phase_label) setUploadPhase(p.phase_label);
              }
            } catch {
              // Ignore transient poll errors; upload XHR will report real failures.
            }
            // Wait before next poll — sequential, never piles up.
            await new Promise(r => setTimeout(r, 1500));
          }
        })();
      };

      try {
        // XHR byte transfer maps to 0→5% (fast network transfer);
        // monotonicity guard ensures we never regress when polling starts.
        const onProgress = (pct: number) =>
          setUploadProgress(prev => Math.max(prev, pct));

        if (isZipFile(file)) {
          await uploadBalanceZip(sessionId, file, onProgress, startPolling);
        } else {
          await uploadBalanceExcel(sessionId, file, onProgress, startPolling);
        }

        // Server responded → stop polling, load data, then mark complete.
        pollTimerRef.current = null;
        setUploadProgress(98);
        setUploadPhase("Loading results…");
        await refreshSummary();
        setUploadProgress(100);
        setUploadPhase("");
      } catch (error) {
        console.error(
          "[BalancePositionsCardConnected] failed to upload balance",
          error
        );
        const msg = error instanceof Error ? error.message : String(error);
        toast.error("Balance upload failed", {
          description: msg.includes("Network error")
            ? "Server may be restarting. Please try again in a moment."
            : msg.length > 120 ? msg.slice(0, 120) + "…" : msg,
        });
      } finally {
        pollTimerRef.current = null;
        setIsUploading(false);
        setUploadProgress(0);
        setUploadPhase("");
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

    setBalanceSummary(null);
    onDataReset?.();
    if (sessionId) {
      deleteBalance(sessionId).catch((err) =>
        console.error("[BalancePositionsCardConnected] deleteBalance failed", err)
      );
    }
  }, [loadSampleIntoBalance, onDataReset, sessionId]);

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
        uploadProgress={smoothProgress}
        uploadPhase={uploadPhase}
      />
    </div>
  );
}
