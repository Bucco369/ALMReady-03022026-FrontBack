import { useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type { FacetOption } from '@/lib/api';

interface FilterDropdownProps {
  label: string;
  options: FacetOption[];
  selected: string[];
  onToggle: (value: string) => void;
  onSetAll?: (values: string[]) => void;
  searchable?: boolean;
}

export function FilterDropdown({ label, options, selected, onToggle, onSetAll, searchable }: FilterDropdownProps) {
  const [search, setSearch] = useState('');
  const showSearch = searchable ?? options.length > 6;

  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.trim().toLowerCase();
    return options.filter((o) => o.value.toLowerCase().includes(q));
  }, [options, search]);

  const allSelected = options.length > 0 && selected.length === options.length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-6 text-xs px-2',
            selected.length > 0 && 'border-primary text-primary'
          )}
        >
          {label}
          {selected.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 h-4 min-w-4 text-[9px] px-1">
              {selected.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-52 p-2" align="start">
        {showSearch && (
          <Input
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-6 text-xs mb-2"
          />
        )}
        {options.length > 1 && onSetAll && (
          <div className="flex items-center gap-1.5 mb-1.5 px-1">
            <button
              onClick={() => onSetAll(options.map((o) => o.value))}
              className={cn('text-[10px] hover:underline', allSelected ? 'text-muted-foreground' : 'text-primary')}
              disabled={allSelected}
            >
              All
            </button>
            <span className="text-muted-foreground text-[10px]">/</span>
            <button
              onClick={() => onSetAll([])}
              className={cn('text-[10px] hover:underline', selected.length === 0 ? 'text-muted-foreground' : 'text-primary')}
              disabled={selected.length === 0}
            >
              None
            </button>
          </div>
        )}
        <div className="space-y-0.5 max-h-56 overflow-y-auto">
          {filtered.length === 0 && (
            <div className="text-xs text-muted-foreground px-1 py-1">No values</div>
          )}
          {filtered.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 py-1 px-1 rounded hover:bg-muted/50 cursor-pointer text-sm"
            >
              <Checkbox
                checked={selected.includes(option.value)}
                onCheckedChange={() => onToggle(option.value)}
              />
              <span className="truncate">{option.value}</span>
              <span className="text-muted-foreground ml-auto text-[10px] tabular-nums">{option.count}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
