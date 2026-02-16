const EXACT_LABELS: Record<string, string> = {
  EUR_ESTR_OIS: "Risk-free",
  EUR_EURIBOR_1M: "EURIBOR 1M",
  EUR_EURIBOR_3M: "EURIBOR 3M",
  EUR_EURIBOR_6M: "EURIBOR 6M",
  EUR_EURIBOR_12M: "EURIBOR 12M",
  EUR_IRS_EURIBOR_3M: "Swap (EURIBOR 3M)",
  EUR_IRS_EURIBOR_6M: "Swap (EURIBOR 6M)",
  EUR_EONIA_LEGACY: "EONIA (legacy)",
  EUR_ESTR: "€STR",
  IRPH: "Hipotecaria (IRPH)",
  EUR_IRPH: "Hipotecaria (IRPH)",
};

function toTitleCaseWords(value: string): string {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function normalizeTenor(tenorToken: string): string {
  return tenorToken.replace(/\s+/g, "").toUpperCase();
}

export function getCurveDisplayLabel(curveId: string): string {
  const normalized = curveId.trim().toUpperCase();
  if (EXACT_LABELS[normalized]) {
    return EXACT_LABELS[normalized];
  }

  const withoutPrefix = normalized.replace(/^[A-Z]{3}[_-]/, "");

  if (/\bIRPH\b/.test(withoutPrefix)) {
    return "Hipotecaria (IRPH)";
  }

  if (/\b(?:IRS|SWAP)[_-]?EURIBOR[_-]?([0-9]+[WMY]|ON)\b/.test(withoutPrefix)) {
    const match = withoutPrefix.match(/\b(?:IRS|SWAP)[_-]?EURIBOR[_-]?([0-9]+[WMY]|ON)\b/);
    if (match?.[1]) {
      return `Swap (EURIBOR ${normalizeTenor(match[1])})`;
    }
  }

  if (/\bEURIBOR[_-]?([0-9]+[WMY]|ON)\b/.test(withoutPrefix)) {
    const match = withoutPrefix.match(/\bEURIBOR[_-]?([0-9]+[WMY]|ON)\b/);
    if (match?.[1]) {
      return `EURIBOR ${normalizeTenor(match[1])}`;
    }
  }

  if (/\bGOVT\b/.test(withoutPrefix)) {
    return "Govt Bond";
  }

  if (/\bESTR[_-]?OIS\b/.test(withoutPrefix)) {
    return "Risk-free";
  }

  if (/\bEONIA\b/.test(withoutPrefix) && /\bLEGACY\b/.test(withoutPrefix)) {
    return "EONIA (legacy)";
  }

  if (/\bESTR\b/.test(withoutPrefix)) {
    return "€STR";
  }

  if (/\bHIPOTEC/.test(withoutPrefix)) {
    return "Hipotecaria";
  }

  const cleaned = withoutPrefix
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return cleaned ? toTitleCaseWords(cleaned) : curveId;
}

export function getCurveTooltipLabel(curveId: string): string {
  const normalized = curveId.trim().toUpperCase();
  if (normalized === "EUR_ESTR_OIS") {
    return "Risk-free (€STR OIS)";
  }
  return getCurveDisplayLabel(curveId);
}
