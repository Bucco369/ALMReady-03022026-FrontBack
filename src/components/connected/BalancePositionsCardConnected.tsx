import React, { useCallback, useEffect, useState } from "react";
import { BalancePositionsCard } from "@/components/BalancePositionsCard";
import {
  getBalanceSummary,
  uploadBalanceExcel,
  type BalanceSummaryResponse,
} from "@/lib/api";
import { inferCategoryFromSheetName } from "@/lib/balanceUi";
import { generateSamplePositionsCSV, parsePositionsCSV } from "@/lib/csvParser";
import { clearSessionId, getOrCreateSessionId } from "@/lib/session";
import { useSession } from "@/hooks/useSession";
import type { Position } from "@/types/financial";

interface BalancePositionsCardConnectedProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
}

const DEFAULT_MATURITY_DATE = "2030-12-31";
const BALANCE_UPLOADED_SESSION_KEY = "almready_balance_uploaded_session_id";

function isExcelFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return lower.endsWith(".xlsx") || lower.endsWith(".xls");
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isStaleSessionError(error: unknown): boolean {
  const message = getErrorMessage(error).toLowerCase();
  return (
    message.includes("session not found") ||
    message.includes("unknown session") ||
    message.includes("invalid session")
  );
}

function isNoBalanceUploadedError(error: unknown): boolean {
  const message = getErrorMessage(error).toLowerCase();
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

function clearSessionState(): void {
  clearSessionId();
  clearUploadedSessionMarker();
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
      currency: "USD",
    };
  });
}

export function BalancePositionsCardConnected({
  positions,
  onPositionsChange,
}: BalancePositionsCardConnectedProps) {
  const { sessionId, loading } = useSession();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [balanceSummary, setBalanceSummary] = useState<BalanceSummaryResponse | null>(null);

  useEffect(() => {
    if (sessionId) setActiveSessionId(sessionId);
  }, [sessionId]);

  const ensureSessionId = useCallback(async (): Promise<string> => {
    if (activeSessionId) return activeSessionId;
    const nextSessionId = await getOrCreateSessionId();
    setActiveSessionId(nextSessionId);
    return nextSessionId;
  }, [activeSessionId]);

  const withSessionRetry = useCallback(
    async <T,>(request: (resolvedSessionId: string) => Promise<T>): Promise<T> => {
      let resolvedSessionId = await ensureSessionId();

      try {
        return await request(resolvedSessionId);
      } catch (error) {
        if (!isStaleSessionError(error)) throw error;

        clearSessionState();
        resolvedSessionId = await getOrCreateSessionId();
        setActiveSessionId(resolvedSessionId);
        return request(resolvedSessionId);
      }
    },
    [ensureSessionId]
  );

  const refreshSummary = useCallback(async () => {
    try {
      const summary = await withSessionRetry((resolvedSessionId) =>
        getBalanceSummary(resolvedSessionId)
      );
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
  }, [onPositionsChange, withSessionRetry]);

  useEffect(() => {
    if (loading || positions.length > 0) return;
    if (!isCurrentSessionKnownUploaded(activeSessionId)) return;
    void refreshSummary();
  }, [activeSessionId, loading, positions.length, refreshSummary]);

  const handleExcelUpload = useCallback(
    async (file: File) => {
      try {
        await withSessionRetry(async (resolvedSessionId) => {
          await uploadBalanceExcel(resolvedSessionId, file);
          setUploadedSessionMarker(resolvedSessionId);
        });
        await refreshSummary();
      } catch (error) {
        console.error(
          "[BalancePositionsCardConnected] failed to upload Excel balance",
          error
        );
      }
    },
    [refreshSummary, withSessionRetry]
  );

  const handleChangeCapture = useCallback(
    (event: React.FormEvent<HTMLDivElement>) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "file") return;

      const file = target.files?.[0];
      if (!file || !isExcelFile(file)) return;

      event.preventDefault();
      event.stopPropagation();
      target.value = "";
      void handleExcelUpload(file);
    },
    [handleExcelUpload]
  );

  const handleDropCapture = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      const file = event.dataTransfer.files?.[0];
      if (!file || !isExcelFile(file)) return;

      event.preventDefault();
      void handleExcelUpload(file);
    },
    [handleExcelUpload]
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
        sessionId={activeSessionId}
        summaryTree={balanceSummary?.summary_tree ?? null}
      />
    </div>
  );
}
