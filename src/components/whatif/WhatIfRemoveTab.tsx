/**
 * WhatIfRemoveTab.tsx – Browse and remove positions from the balance.
 *
 * ── ROLE IN THE SYSTEM ─────────────────────────────────────────────────
 *
 *   Used by BOTH WhatIfBuilder (legacy) and BuySellCompartment (current).
 *   BuySellCompartment embeds the same removal logic: the "Remove" sub-tab
 *   shows the balance tree and supports "remove all" or contract drill-down.
 *
 *   Two removal modes:
 *   1. SEARCH: Contract ID search (debounced API → /balance/contracts).
 *   2. BROWSE: Balance tree subcategory → "Remove All" or Eye icon →
 *      BalanceDetailsModalRemove (filter + cherry-pick contracts).
 *
 * ── DATA FLOW ───────────────────────────────────────────────────────────
 *
 *   Balance tree (BalanceUiTree) → RemoveTreeNode[] → TreeNode component.
 *   Each node shows: label, amount (Mln), position count, hover actions.
 *
 *   Remove actions:
 *   • Subcategory "Remove All" (Minus icon):
 *     Creates WhatIfModification { type: 'remove', removeMode: 'all' }.
 *     Locks the subcategory (Lock icon, further removals disabled).
 *     Fetches per-contract maturityProfile for accurate chart allocation.
 *
 *   • Eye icon → BalanceDetailsModalRemove:
 *     Opens modal for filtered/cherry-picked contract removal.
 *     Creates per-contract modifications { removeMode: 'contracts' }.
 *
 *   • Search result removal:
 *     Individual contract removal via handleRemoveContract().
 *     Disabled if subcategory already has "remove all" active.
 *
 * ── MATURITY PROFILE ────────────────────────────────────────────────────
 *
 *   Both "remove all" and filtered removals fetch maturityProfile[] from
 *   the backend (per-contract amount + maturityYears). This allows the
 *   EVE chart to distribute the removal across correct time buckets
 *   rather than using a single average maturity.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Search, ChevronRight, ChevronDown, Minus, FileText, Folder, FolderOpen, Eye, Lock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getBalanceContracts, type BalanceContract } from '@/lib/api';
import type { BalanceUiTree } from '@/lib/balanceUi';
import { useWhatIf } from './WhatIfContext';
import { BalanceDetailsModalRemove } from './BalanceDetailsModalRemove';

interface WhatIfRemoveTabProps {
  sessionId: string | null;
  balanceTree: BalanceUiTree | null;
}

interface RemoveTreeNode {
  id: string;
  label: string;
  type: 'category' | 'subcategory';
  category: 'asset' | 'liability';
  amount: number;
  count: number;
  avgRate?: number | null;
  avgMaturity?: number | null;
  children?: RemoveTreeNode[];
}

function normalizeCategory(category: string): 'asset' | 'liability' {
  return category.toLowerCase().startsWith('liab') ? 'liability' : 'asset';
}

function formatAmount(num: number) {
  const millions = num / 1e6;
  return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
}

function contractDetailLine(contract: BalanceContract): string {
  const bucket = contract.maturity_bucket ?? 'n/a';
  const group = contract.group ?? contract.subcategoria_ui ?? contract.subcategory;
  const amount = contract.amount ?? 0;
  const path =
    contract.categoria_ui && contract.subcategoria_ui
      ? `${contract.categoria_ui} / ${contract.subcategoria_ui}`
      : contract.subcategoria_ui ?? contract.subcategory;
  return `${path} • ${group} • ${bucket} • ${formatAmount(amount)}`;
}

export function WhatIfRemoveTab({ sessionId, balanceTree }: WhatIfRemoveTabProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const [searchResults, setSearchResults] = useState<BalanceContract[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedCategoryForDetails, setSelectedCategoryForDetails] = useState<string | null>(null);
  const [removeAllLoading, setRemoveAllLoading] = useState<string | null>(null);
  const { addModification, modifications } = useWhatIf();

  const removeAllSubcategories = useMemo(() => {
    return new Set(
      modifications
        .filter((mod) => mod.type === 'remove' && mod.removeMode === 'all' && mod.subcategory)
        .map((mod) => mod.subcategory as string)
    );
  }, [modifications]);

  const treeNodes = useMemo<RemoveTreeNode[]>(() => {
    if (!balanceTree) return [];

    const assetsNode: RemoveTreeNode = {
      id: 'assets',
      label: 'Assets',
      type: 'category',
      category: 'asset',
      amount: balanceTree.assets.amount,
      count: balanceTree.assets.positions,
      avgRate: balanceTree.assets.avgRate,
      avgMaturity: balanceTree.assets.avgMaturity,
      children: balanceTree.assets.subcategories.map((sub) => ({
        id: sub.id,
        label: sub.name,
        type: 'subcategory',
        category: 'asset',
        amount: sub.amount,
        count: sub.positions,
        avgRate: sub.avgRate,
        avgMaturity: sub.avgMaturity,
      })),
    };

    const liabilitiesNode: RemoveTreeNode = {
      id: 'liabilities',
      label: 'Liabilities',
      type: 'category',
      category: 'liability',
      amount: balanceTree.liabilities.amount,
      count: balanceTree.liabilities.positions,
      avgRate: balanceTree.liabilities.avgRate,
      avgMaturity: balanceTree.liabilities.avgMaturity,
      children: balanceTree.liabilities.subcategories.map((sub) => ({
        id: sub.id,
        label: sub.name,
        type: 'subcategory',
        category: 'liability',
        amount: sub.amount,
        count: sub.positions,
        avgRate: sub.avgRate,
        avgMaturity: sub.avgMaturity,
      })),
    };

    return [assetsNode, liabilitiesNode];
  }, [balanceTree]);

  useEffect(() => {
    let active = true;
    const q = searchQuery.trim();

    if (!sessionId || q.length < 2) {
      setSearchResults([]);
      setSearchLoading(false);
      setSearchError(null);
      return () => {
        active = false;
      };
    }

    setSearchLoading(true);
    setSearchError(null);

    const timer = window.setTimeout(async () => {
      try {
        const response = await getBalanceContracts(sessionId, {
          query: q,
          page: 1,
          page_size: 100,
        });
        if (!active) return;
        setSearchResults(response.contracts);
      } catch (error) {
        if (!active) return;
        setSearchResults([]);
        setSearchError(getErrorMessage(error));
      } finally {
        if (active) setSearchLoading(false);
      }
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [searchQuery, sessionId]);

  const availableSearchResults = useMemo(() => {
    return searchResults.filter((contract) => !removeAllSubcategories.has(contract.subcategory));
  }, [removeAllSubcategories, searchResults]);

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const handleRemoveNode = async (node: RemoveTreeNode) => {
    if (node.type !== 'subcategory') return;
    if (removeAllSubcategories.has(node.id)) return;

    // Fetch per-contract maturity distribution for accurate chart allocation
    let maturityProfile: Array<{ amount: number; maturityYears: number; rate?: number }> | undefined;
    if (sessionId) {
      setRemoveAllLoading(node.id);
      try {
        const resp = await getBalanceContracts(sessionId, {
          subcategory_id: node.id,
          page: 1,
          page_size: 50_000,
        });
        maturityProfile = resp.contracts.map((c) => ({
          amount: c.amount ?? 0,
          maturityYears: c.maturity_years ?? 0,
          rate: c.rate ?? undefined,
        }));
      } catch {
        // Fall back to single avg maturity if fetch fails
      } finally {
        setRemoveAllLoading(null);
      }
    }

    addModification({
      type: 'remove',
      removeMode: 'all',
      label: node.label,
      details: `${formatAmount(node.amount)} (all)`,
      notional: node.amount,
      category: node.category,
      subcategory: node.id,
      rate: node.avgRate ?? undefined,
      maturity: node.avgMaturity ?? 0,
      positionDelta: node.count,
      maturityProfile,
    });
  };

  const handleViewDetails = (node: RemoveTreeNode) => {
    if (node.type !== 'subcategory') return;
    setSelectedCategoryForDetails(node.id);
    setShowDetailsModal(true);
  };

  const handleRemoveContract = (contract: BalanceContract) => {
    if (removeAllSubcategories.has(contract.subcategory)) return;

    addModification({
      type: 'remove',
      removeMode: 'contracts',
      contractIds: [contract.contract_id],
      label: contract.contract_id,
      details: contractDetailLine(contract),
      notional: contract.amount ?? 0,
      category: normalizeCategory(contract.category),
      subcategory: contract.subcategory,
      rate: contract.rate ?? undefined,
      maturity: contract.maturity_years ?? 0,
      positionDelta: 1,
    });
  };

  const hasBalanceTree =
    treeNodes.some((node) => (node.children?.length ?? 0) > 0) ||
    treeNodes.some((node) => node.count > 0);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search by Contract ID (NUM_SEC_AC...)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-7 pl-7 text-xs"
          />
        </div>

        {searchQuery.trim().length >= 2 && (
          <div className="rounded-md border border-border bg-card overflow-hidden">
            {searchLoading && (
              <div className="px-2.5 py-2 text-[11px] text-muted-foreground">Searching contracts...</div>
            )}

            {!searchLoading && searchError && (
              <div className="px-2.5 py-2 text-[11px] text-destructive whitespace-pre-wrap">{searchError}</div>
            )}

            {!searchLoading && !searchError && availableSearchResults.length === 0 && (
              <div className="px-2.5 py-2 text-[11px] text-muted-foreground">No contracts found.</div>
            )}

            {!searchLoading &&
              !searchError &&
              availableSearchResults.map((contract) => (
                <div
                  key={`${contract.contract_id}-${contract.sheet ?? 'sheet'}`}
                  className="flex items-center justify-between px-2.5 py-1.5 border-b border-border/50 last:border-0 hover:bg-accent/30"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="text-xs font-mono text-foreground truncate">{contract.contract_id}</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground ml-4.5">{contractDetailLine(contract)}</div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 px-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => handleRemoveContract(contract)}
                  >
                    <Minus className="h-3 w-3" />
                  </Button>
                </div>
              ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-border" />
        <span className="text-[9px] text-muted-foreground uppercase tracking-wide">Or select from balance</span>
        <div className="flex-1 h-px bg-border" />
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-0.5 pr-3">
          {hasBalanceTree ? (
            treeNodes.map((node) => (
              <TreeNode
                key={node.id}
                node={node}
                depth={0}
                expandedNodes={expandedNodes}
                removeAllSubcategories={removeAllSubcategories}
                removeAllLoading={removeAllLoading}
                onToggle={toggleNode}
                onRemove={handleRemoveNode}
                onViewDetails={handleViewDetails}
              />
            ))
          ) : (
            <p className="text-[11px] text-muted-foreground italic">Upload a balance to enable remove selection.</p>
          )}
        </div>
      </ScrollArea>

      {selectedCategoryForDetails && (
        <BalanceDetailsModalRemove
          open={showDetailsModal}
          onOpenChange={setShowDetailsModal}
          selectedCategory={selectedCategoryForDetails}
          searchQuery={searchQuery}
          sessionId={sessionId}
          subcategoryLocked={removeAllSubcategories.has(selectedCategoryForDetails)}
        />
      )}
    </div>
  );
}

interface TreeNodeProps {
  node: RemoveTreeNode;
  depth: number;
  expandedNodes: Set<string>;
  removeAllSubcategories: Set<string>;
  removeAllLoading: string | null;
  onToggle: (id: string) => void;
  onRemove: (node: RemoveTreeNode) => void;
  onViewDetails: (node: RemoveTreeNode) => void;
}

function TreeNode({
  node,
  depth,
  expandedNodes,
  removeAllSubcategories,
  removeAllLoading,
  onToggle,
  onRemove,
  onViewDetails,
}: TreeNodeProps) {
  const isExpanded = expandedNodes.has(node.id);
  const hasChildren = Boolean(node.children && node.children.length > 0);
  const isLeaf = !hasChildren;
  const isLocked = isLeaf && removeAllSubcategories.has(node.id);
  const isLoading = isLeaf && removeAllLoading === node.id;

  const isCategory = node.type === 'category';
  const labelColor = node.id === 'assets' ? 'text-success' : node.id === 'liabilities' ? 'text-destructive' : 'text-foreground';

  const FolderIcon = isExpanded ? FolderOpen : Folder;
  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1 px-1.5 rounded-sm hover:bg-accent/50 group cursor-pointer ${
          depth === 0 ? 'bg-muted/30' : ''
        }`}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
      >
        {hasChildren ? (
          <button onClick={() => onToggle(node.id)} className="p-0.5 hover:bg-accent rounded">
            <ChevronIcon className="h-3 w-3 text-muted-foreground" />
          </button>
        ) : (
          <span className="w-4" />
        )}

        {hasChildren ? (
          <FolderIcon className="h-3 w-3 text-muted-foreground" />
        ) : (
          <FileText className="h-3 w-3 text-muted-foreground" />
        )}

        <span className={`text-xs flex-1 ${isCategory ? `font-semibold ${labelColor}` : 'text-foreground'}`}>
          {node.label}
        </span>

        {node.amount !== 0 && (
          <span className="text-[10px] font-mono text-muted-foreground">{formatAmount(node.amount)}</span>
        )}

        {node.count > 0 && (
          <span className="text-[9px] text-muted-foreground/70 bg-muted px-1 rounded">{node.count}</span>
        )}

        {isLocked && (
          <Lock className="h-2.5 w-2.5 text-muted-foreground/70" />
        )}

        {isLeaf && (
          <Button
            variant="ghost"
            size="sm"
            disabled={isLocked}
            className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-opacity disabled:opacity-30"
            onClick={(e) => {
              e.stopPropagation();
              onViewDetails(node);
            }}
            title="View contracts for removal"
          >
            <Eye className="h-2.5 w-2.5" />
          </Button>
        )}

        {isLeaf && (
          <Button
            variant="ghost"
            size="sm"
            disabled={isLocked || isLoading}
            className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive hover:bg-destructive/10 transition-opacity disabled:opacity-30"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(node);
            }}
          >
            {isLoading
              ? <div className="h-2.5 w-2.5 animate-spin rounded-full border border-destructive border-t-transparent" />
              : <Minus className="h-2.5 w-2.5" />}
          </Button>
        )}
      </div>

      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              expandedNodes={expandedNodes}
              removeAllSubcategories={removeAllSubcategories}
              removeAllLoading={removeAllLoading}
              onToggle={onToggle}
              onRemove={onRemove}
              onViewDetails={onViewDetails}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
