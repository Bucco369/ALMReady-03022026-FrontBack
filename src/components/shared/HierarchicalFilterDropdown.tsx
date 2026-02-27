import { useState, useMemo } from 'react';
import { ChevronRight } from 'lucide-react';
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

interface HierarchicalFilterDropdownProps {
  label: string;
  parentFacets: FacetOption[];
  segmentTree: Record<string, FacetOption[]>;
  selectedParents: string[];
  selectedChildren: string[];
  onToggleParent: (value: string) => void;
  onToggleChild: (value: string) => void;
  onClearAll?: () => void;
}

export function HierarchicalFilterDropdown({
  label,
  parentFacets,
  segmentTree,
  selectedParents,
  selectedChildren,
  onToggleParent,
  onToggleChild,
  onClearAll,
}: HierarchicalFilterDropdownProps) {
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const totalSelected = selectedParents.length + selectedChildren.length;

  const filteredParents = useMemo(() => {
    if (!search.trim()) return parentFacets;
    const q = search.trim().toLowerCase();
    return parentFacets.filter((p) => {
      if (p.value.toLowerCase().includes(q)) return true;
      const children = segmentTree[p.value] ?? [];
      return children.some((c) => c.value.toLowerCase().includes(q));
    });
  }, [parentFacets, search, segmentTree]);

  const toggleExpand = (parent: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(parent)) next.delete(parent);
      else next.add(parent);
      return next;
    });
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-6 text-xs px-2',
            totalSelected > 0 && 'border-primary text-primary'
          )}
        >
          {label}
          {totalSelected > 0 && (
            <Badge variant="secondary" className="ml-1.5 h-4 min-w-4 text-[9px] px-1">
              {totalSelected}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="start">
        {parentFacets.length > 6 && (
          <Input
            placeholder="Search segments..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-6 text-xs mb-2"
          />
        )}
        {totalSelected > 0 && onClearAll && (
          <div className="flex items-center mb-1.5 px-1">
            <button
              onClick={onClearAll}
              className="text-[10px] text-primary hover:underline"
            >
              Clear all
            </button>
          </div>
        )}
        <div className="space-y-0.5 max-h-64 overflow-y-auto">
          {filteredParents.length === 0 && (
            <div className="text-xs text-muted-foreground px-1 py-1">No segments</div>
          )}
          {filteredParents.map((parent) => {
            const children = segmentTree[parent.value] ?? [];
            const hasChildren = children.length > 0;
            const isExpanded = expanded.has(parent.value);
            const q = search.trim().toLowerCase();
            const filteredChildren = q
              ? children.filter((c) => c.value.toLowerCase().includes(q))
              : children;

            return (
              <div key={parent.value}>
                <div className="flex items-center gap-1 py-1 px-1 rounded hover:bg-muted/50">
                  {hasChildren ? (
                    <button
                      onClick={() => toggleExpand(parent.value)}
                      className="p-0.5 text-muted-foreground hover:text-foreground"
                    >
                      <ChevronRight
                        className={cn('h-3 w-3 transition-transform', isExpanded && 'rotate-90')}
                      />
                    </button>
                  ) : (
                    <div className="w-4" />
                  )}
                  <label className="flex items-center gap-2 cursor-pointer flex-1 text-sm">
                    <Checkbox
                      checked={selectedParents.includes(parent.value)}
                      onCheckedChange={() => onToggleParent(parent.value)}
                    />
                    <span className="truncate font-medium">{parent.value}</span>
                    <span className="text-muted-foreground ml-auto text-[10px] tabular-nums">
                      {parent.count}
                    </span>
                  </label>
                </div>
                {isExpanded && filteredChildren.length > 0 && (
                  <div className="ml-6 space-y-0.5">
                    {filteredChildren.map((child) => (
                      <label
                        key={child.value}
                        className="flex items-center gap-2 py-0.5 px-1 rounded hover:bg-muted/50 cursor-pointer text-xs"
                      >
                        <Checkbox
                          checked={selectedChildren.includes(child.value)}
                          onCheckedChange={() => onToggleChild(child.value)}
                        />
                        <span className="truncate">{child.value}</span>
                        <span className="text-muted-foreground ml-auto text-[10px]">{child.count}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
