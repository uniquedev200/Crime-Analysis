import type { Case, Insight } from './api';
export type LoadStatus = 'loading' | 'ready' | 'error';
export function isActiveCase(record: Case): boolean {
  return ['OPEN', 'UNDER_INVESTIGATION', 'ACTIVE', 'IN_PROGRESS'].includes(String(record.status || '').toUpperCase());
}
export function caseCategory(record: Case): string {
  return String(record.crime_category || record.case_type || record.category_of_crime || 'Not recorded');
}
export function caseUpdated(record: Case): string {
  return String(record.updated_at || record.last_updated || record.created_at || record.created_date || record.date_filed || '');
}
export function displayDate(value: unknown): string {
  if (!value) return 'Not recorded';
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
export function sourceReferences(record: Record<string, unknown>): string[] {
  const props = (record.properties && typeof record.properties === 'object' ? record.properties : record) as Record<string, unknown>;
  const metadata = (record.metadata && typeof record.metadata === 'object' ? record.metadata : {}) as Record<string, unknown>;
  const references: string[] = [];
  for (const obj of [props, metadata]) for (const key of ['source_record_id', 'source_record_ids', 'source_ids']) {
    const value = obj[key];
    if (Array.isArray(value)) references.push(...value.filter(v => typeof v === 'string') as string[]);
    else if (typeof value === 'string' && value) {
      try { const parsed = JSON.parse(value); if (Array.isArray(parsed)) { references.push(...parsed.filter(v => typeof v === 'string')); continue; } } catch { /* Plain identifier. */ }
      references.push(value);
    }
  }
  return [...new Set(references)];
}
export function scopedConnections(insights: Insight[], visibleCaseIds: string[]): Insight[] {
  const allowed = new Set(visibleCaseIds);
  return insights.filter(i => (i.case_ids || []).length > 1 && i.case_ids!.every(id => allowed.has(id)));
}
export function caseMetric(value: number, status: LoadStatus, hasLoaded: boolean): number | string {
  return hasLoaded ? value : status === 'loading' ? '…' : '—';
}
