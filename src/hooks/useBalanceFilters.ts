import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface BalanceFilters {
  currencies: string[];
  rateTypes: string[];
  segments: string[];
  strategicSegments: string[];
  maturityBuckets: string[];
  remunerations: string[];
  bookValues: string[];
}

const EMPTY_FILTERS: BalanceFilters = {
  currencies: [],
  rateTypes: [],
  segments: [],
  strategicSegments: [],
  maturityBuckets: [],
  remunerations: [],
  bookValues: [],
};

const DEBOUNCE_MS = 200;

export function useBalanceFilters() {
  const [filters, setFilters] = useState<BalanceFilters>(EMPTY_FILTERS);
  const [debouncedFilters, setDebouncedFilters] = useState<BalanceFilters>(EMPTY_FILTERS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedFilters(filters);
    }, DEBOUNCE_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [filters]);

  const toggleFilter = useCallback((category: keyof BalanceFilters, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter((v) => v !== value)
        : [...prev[category], value],
    }));
  }, []);

  const setFilterCategory = useCallback((category: keyof BalanceFilters, values: string[]) => {
    setFilters((prev) => ({ ...prev, [category]: values }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setDebouncedFilters(EMPTY_FILTERS);
  }, []);

  const activeFilterCount = useMemo(
    () =>
      filters.currencies.length +
      filters.rateTypes.length +
      filters.segments.length +
      filters.strategicSegments.length +
      filters.maturityBuckets.length +
      filters.remunerations.length +
      filters.bookValues.length,
    [filters]
  );

  return { filters, debouncedFilters, setFilters, setFilterCategory, toggleFilter, clearFilters, activeFilterCount };
}
