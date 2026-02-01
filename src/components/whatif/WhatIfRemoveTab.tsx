import React, { useState } from 'react';
import { Search, ChevronRight, ChevronDown, Minus, FileText, Folder, FolderOpen } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BALANCE_HIERARCHY, type BalanceNode } from '@/types/whatif';
import { useWhatIf } from './WhatIfContext';

// Mock contract search results
const MOCK_CONTRACTS = [
  { id: 'NUM_SEC_AC_001234', product: 'Fixed Rate Mortgage', balance: 450000, rate: 3.25 },
  { id: 'NUM_SEC_AC_001235', product: 'Commercial Loan', balance: 2500000, rate: 4.50 },
  { id: 'NUM_SEC_AC_001236', product: 'Government Bond', balance: 10000000, rate: 2.10 },
  { id: 'NUM_SEC_AC_002100', product: 'Term Deposit', balance: 1500000, rate: 3.75 },
  { id: 'NUM_SEC_AC_002101', product: 'Corporate Bond', balance: 5000000, rate: 4.25 },
];

export function WhatIfRemoveTab() {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const { addModification } = useWhatIf();

  const toggleNode = (nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  // Map node IDs to category and subcategory for balance tree placement
  const getCategoryFromNodeId = (nodeId: string): { category: 'asset' | 'liability'; subcategory: string } => {
    const assetSubcategories = ['mortgages', 'loans', 'securities', 'interbank', 'other-assets'];
    const liabilitySubcategories = ['deposits', 'term-deposits', 'wholesale-funding', 'debt-issued', 'other-liabilities'];
    
    if (nodeId === 'assets' || assetSubcategories.includes(nodeId)) {
      return { 
        category: 'asset', 
        subcategory: assetSubcategories.includes(nodeId) ? nodeId : 'loans'
      };
    }
    return { 
      category: 'liability', 
      subcategory: liabilitySubcategories.includes(nodeId) ? nodeId : 'term-deposits'
    };
  };

  const handleRemoveNode = (node: BalanceNode, path: string) => {
    const { category, subcategory } = getCategoryFromNodeId(node.id);
    addModification({
      type: 'remove',
      label: node.label,
      details: node.amount ? formatAmount(node.amount) : undefined,
      notional: node.amount || 0,
      category,
      subcategory,
      rate: 0.035, // Placeholder rate for removed positions
    });
  };

  const handleRemoveContract = (contract: typeof MOCK_CONTRACTS[0]) => {
    // Determine category based on product type (mock logic)
    const isAsset = ['Fixed Rate Mortgage', 'Commercial Loan', 'Government Bond', 'Corporate Bond'].includes(contract.product);
    const subcategoryMap: Record<string, string> = {
      'Fixed Rate Mortgage': 'mortgages',
      'Commercial Loan': 'loans',
      'Government Bond': 'securities',
      'Corporate Bond': 'securities',
      'Term Deposit': 'term-deposits',
    };
    
    addModification({
      type: 'remove',
      label: contract.id,
      details: `${contract.product} - ${formatAmount(contract.balance)}`,
      notional: contract.balance,
      category: isAsset ? 'asset' : 'liability',
      subcategory: subcategoryMap[contract.product] || (isAsset ? 'loans' : 'term-deposits'),
      rate: contract.rate / 100,
    });
  };

  const formatAmount = (num: number) => {
    if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `$${(num / 1e3).toFixed(0)}K`;
    return `$${num}`;
  };

  // Filter contracts based on search
  const filteredContracts = searchQuery.length >= 2
    ? MOCK_CONTRACTS.filter(c => 
        c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.product.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Contract Search */}
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
        
        {/* Search Results */}
        {filteredContracts.length > 0 && (
          <div className="rounded-md border border-border bg-card overflow-hidden">
            {filteredContracts.map(contract => (
              <div
                key={contract.id}
                className="flex items-center justify-between px-2.5 py-1.5 border-b border-border/50 last:border-0 hover:bg-accent/30"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                    <span className="text-xs font-mono text-foreground truncate">{contract.id}</span>
                  </div>
                  <div className="text-[10px] text-muted-foreground ml-4.5">
                    {contract.product} • {formatAmount(contract.balance)} • {contract.rate}%
                  </div>
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

      {/* Divider */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-border" />
        <span className="text-[9px] text-muted-foreground uppercase tracking-wide">Or select from balance</span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* Balance Tree */}
      <ScrollArea className="flex-1">
        <div className="space-y-0.5 pr-3">
          {BALANCE_HIERARCHY.map(node => (
            <TreeNode
              key={node.id}
              node={node}
              path={node.label}
              depth={0}
              expandedNodes={expandedNodes}
              onToggle={toggleNode}
              onRemove={handleRemoveNode}
              formatAmount={formatAmount}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

interface TreeNodeProps {
  node: BalanceNode;
  path: string;
  depth: number;
  expandedNodes: Set<string>;
  onToggle: (id: string) => void;
  onRemove: (node: BalanceNode, path: string) => void;
  formatAmount: (n: number) => string;
}

function TreeNode({ node, path, depth, expandedNodes, onToggle, onRemove, formatAmount }: TreeNodeProps) {
  const isExpanded = expandedNodes.has(node.id);
  const hasChildren = node.children && node.children.length > 0;
  
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
        {/* Expand/collapse */}
        {hasChildren ? (
          <button onClick={() => onToggle(node.id)} className="p-0.5 hover:bg-accent rounded">
            <ChevronIcon className="h-3 w-3 text-muted-foreground" />
          </button>
        ) : (
          <span className="w-4" />
        )}

        {/* Icon */}
        {hasChildren ? (
          <FolderIcon className="h-3 w-3 text-muted-foreground" />
        ) : (
          <FileText className="h-3 w-3 text-muted-foreground" />
        )}

        {/* Label */}
        <span className={`text-xs flex-1 ${isCategory ? `font-semibold ${labelColor}` : 'text-foreground'}`}>
          {node.label}
        </span>

        {/* Amount */}
        {node.amount && (
          <span className="text-[10px] font-mono text-muted-foreground">
            {formatAmount(node.amount)}
          </span>
        )}

        {/* Count */}
        {node.count && (
          <span className="text-[9px] text-muted-foreground/70 bg-muted px-1 rounded">
            {node.count}
          </span>
        )}

        {/* Remove button */}
        <Button
          variant="ghost"
          size="sm"
          className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive hover:bg-destructive/10 transition-opacity"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(node, path);
          }}
        >
          <Minus className="h-2.5 w-2.5" />
        </Button>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map(child => (
            <TreeNode
              key={child.id}
              node={child}
              path={`${path} > ${child.label}`}
              depth={depth + 1}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onRemove={onRemove}
              formatAmount={formatAmount}
            />
          ))}
        </div>
      )}
    </div>
  );
}
