import type { Position, YieldCurve, YieldCurvePoint } from '@/types/financial';

/**
 * Parse CSV content into an array of string arrays
 */
function parseCSVContent(content: string): string[][] {
  const lines = content.trim().split('\n');
  return lines.map((line) =>
    line.split(',').map((cell) => cell.trim().replace(/^["']|["']$/g, ''))
  );
}

/**
 * Parse positions from CSV file
 * Expected format: id,instrumentType,description,notional,maturityDate,couponRate,repriceFrequency,currency
 */
export function parsePositionsCSV(content: string): Position[] {
  const rows = parseCSVContent(content);
  
  // Skip header row
  const dataRows = rows.slice(1);
  
  return dataRows
    .filter((row) => row.length >= 8 && row[0])
    .map((row, index) => ({
      id: row[0] || String(index + 1),
      instrumentType: (row[1] === 'Liability' ? 'Liability' : 'Asset') as 'Asset' | 'Liability',
      description: row[2] || 'Unknown',
      notional: parseFloat(row[3]) || 0,
      maturityDate: row[4] || new Date().toISOString().split('T')[0],
      couponRate: parseFloat(row[5]) || 0,
      repriceFrequency: (row[6] as Position['repriceFrequency']) || 'Fixed',
      currency: row[7] || 'USD',
    }));
}

/**
 * Parse yield curve from CSV file
 * Expected format: tenor,rate
 */
export function parseYieldCurveCSV(content: string, curveName: string = 'Uploaded Curve'): YieldCurve {
  const rows = parseCSVContent(content);
  
  // Skip header row
  const dataRows = rows.slice(1);
  
  const points: YieldCurvePoint[] = dataRows
    .filter((row) => row.length >= 2 && row[0])
    .map((row) => {
      const tenor = row[0];
      const rate = parseFloat(row[1]) || 0;
      
      // Parse tenor to years
      let tenorYears = 1;
      if (tenor.endsWith('M')) {
        tenorYears = parseInt(tenor) / 12;
      } else if (tenor.endsWith('Y')) {
        tenorYears = parseInt(tenor);
      } else {
        tenorYears = parseFloat(tenor) || 1;
      }
      
      return {
        tenor,
        tenorYears,
        rate: rate > 1 ? rate / 100 : rate, // Convert from percentage if needed
      };
    });
  
  return {
    id: `curve-${Date.now()}`,
    name: curveName,
    currency: 'USD',
    asOfDate: new Date().toISOString().split('T')[0],
    points,
  };
}

/**
 * Generate sample CSV content for positions
 */
export function generateSamplePositionsCSV(): string {
  return `id,instrumentType,description,notional,maturityDate,couponRate,repriceFrequency,currency
1,Asset,Fixed Rate Mortgage Portfolio,50000000,2029-12-31,0.045,Fixed,USD
2,Asset,Floating Rate Commercial Loans,30000000,2027-06-30,0.055,Quarterly,USD
3,Liability,Term Deposits,40000000,2025-12-31,0.035,Fixed,USD
4,Liability,Savings Accounts,25000000,2025-06-30,0.02,Monthly,USD`;
}

/**
 * Generate sample CSV content for yield curve
 */
export function generateSampleYieldCurveCSV(): string {
  return `tenor,rate
1M,0.0525
3M,0.054
6M,0.0545
1Y,0.0495
2Y,0.0445
3Y,0.0425
5Y,0.0415
7Y,0.042
10Y,0.0435
20Y,0.047
30Y,0.0475`;
}
