// ---------- TypeScript Interfaces ----------
export interface Case {
  case_id: string;
  case_name?: string;
  status?: string;
  uploaded_by?: string;
  lead_investigator?: string;
  total_entities?: number;
  severity?: string;
  fir_number?: string;
  date_filed?: string;
  crime_category?: string;
  primary_suspect?: string;
  victim?: string;
  evidences?: string[];
  overlapping_cases?: string[];
  [key: string]: unknown;
}


export interface Entity {
  id?: string;
  entity_id?: string;
  display_name?: string;
  name?: string;
  labels?: string[];
  case_ids?: string[];
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Insight {
  insight_id?: string;
  type?: string;
  severity?: string;
  description?: string;
  case_id?: string;
  entities_involved?: string[];
  [key: string]: unknown;
}

export interface GraphNode {
  id: string;
  name?: string;
  labels?: string[];
  properties?: Record<string, unknown>;
  degree?: number;
  is_key_entity?: boolean;
}

export interface GraphEdge {
  id?: string;
  source: string;
  target: string;
  type?: string;
  properties?: Record<string, unknown>;
}

export interface HealthStatus {
  status: string;
  database?: string;
  version?: string;
  edition?: string;
  gds_available?: boolean;
  gds_version?: string | null;
  latency_ms?: number;
}

export interface NavOption {
  id: string;
  label: string;
  icon: string;
}

export interface Toast {
  id: number;
  msg: string;
  type: string;
  out: boolean;
}

export type ViewId = 'home' | 'overview' | 'graph' | 'search' | 'path' | 'rankings' | 'insights' | 'blockchain' | 'timeline' | 'cases' | 'ingest' | 'board' | 'reports';

export type ThemeMode = 'dark' | 'light';

export interface OfficerSession {
  isDemo?: boolean;
  agency?: string;
  rank?: string;
  badgeNumber: string;
  officerName: string;
  department: string;
  clearanceLevel: string; // e.g. 'Level 1: Officer' | 'Level 2: Investigator' | 'Level 3: Lead Detective' | 'Level 4: Special Director'
  signedInAt: string;
}

export interface ModalState {
  type: string;
  data?: Record<string, unknown>;
}

export interface AiChatMessage {
  sender: 'user' | 'bot';
  content: string;
  model?: string;
  error?: boolean;
  chips?: string[];
  extracted_graph_type?: string;
}

export interface PathResult {
  error?: string;
  ambiguous?: boolean;
  message?: string;
  candidates?: Array<{
    person_id: string;
    name: string;
    dob?: string;
    case_ids?: string[];
  }>;
  nodes?: Array<{
    id: string;
    name?: string;
    labels?: string[];
  }>;
  edges?: Array<{
    type: string;
    source: string;
    target: string;
  }>;
  relationships?: Array<{
    id?: string;
    type: string;
    start_node?: string;
    end_node?: string;
    properties?: Record<string, unknown>;
  }>;
  path_length?: number;
  summary?: string;
}

export interface RankingResult {
  supported?: boolean;
  reason?: string | null;
  rankings: Array<{
    id: string;
    name?: string;
    labels?: string[];
    score: number;
    case_ids?: string[];
  }>;
  total_ranked: number;
  metric?: string;
}

export interface BlockchainBlock {
  block_index?: number;
  case_id?: string;
  document_type?: string;
  hash?: string;
  prev_hash?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---------- API Helper ----------
interface ApiErrorDetail {
  detail?: string | Array<{ loc?: string[]; msg: string }> | { code?: string; message?: string };
  message?: string;
}

interface SendOptions extends RequestInit {
  form?: boolean;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/$/, '');

export const API = {
  formatError(d: ApiErrorDetail | string | null, status: number): string {
    const safeDatabaseCodes = ['DATABASE_AUTH_FAILED', 'DATABASE_AUTH_RATE_LIMIT', 'DATABASE_PASSWORD_EXPIRED', 'DATABASE_WRITE_DENIED', 'DATABASE_NOT_FOUND', 'DATABASE_UNAVAILABLE'];
    if (status === 503 && d && typeof d === 'object' && d.detail && !Array.isArray(d.detail) && typeof d.detail === 'object' && safeDatabaseCodes.includes(d.detail.code || '') && d.detail.message) {
      return d.detail.message;
    }
    if (status >= 500) return 'This service is temporarily unavailable. Please retry.';
    if (!d) return `HTTP ${status}`;
    if (typeof d === 'string') return d;
    if (d.detail) {
      if (typeof d.detail === 'string') return d.detail;
      if (Array.isArray(d.detail)) {
        return d.detail.map((e) => (e.loc ? e.loc.filter((l) => l !== 'body').join('.') + ': ' : '') + e.msg).join('; ');
      }
      if (typeof d.detail === 'object') return d.detail.message || JSON.stringify(d.detail);
    }
    if (d.message) return d.message;
    return `HTTP ${status}`;
  },
  async get<T = unknown>(url: string): Promise<T> {
    return this.send<T>(url, { method: 'GET' });
  },
  async post<T = unknown>(url: string, body: unknown = {}): Promise<T> {
    return this.send<T>(url, { method: 'POST', body: typeof body === 'string' ? body : JSON.stringify(body) });
  },
  async put<T = unknown>(url: string, body: unknown = {}): Promise<T> {
    return this.send<T>(url, { method: 'PUT', body: typeof body === 'string' ? body : JSON.stringify(body) });
  },
  async send<T = unknown>(url: string, opts: SendOptions = {}): Promise<T> {
    const { form, ...requestOptions } = opts;
    const headers = new Headers(opts.headers);
    headers.set('Accept', 'application/json');
    if (!form && opts.body != null && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${url}`, { ...requestOptions, headers });
    } catch {
      throw new Error('Unable to reach the ATLAS backend. Check that the backend is running and the API address is correct.');
    }
    if (response.status === 204) return undefined as T;
    let data: T | null = null;
    try { data = await response.json(); } catch { /* Report non-JSON proxy/server responses below. */ }
    if (!response.ok) {
      if (data === null && [500, 502, 503, 504].includes(response.status)) {
        throw new Error('The ATLAS backend is unavailable. Start the backend or check its connection settings.');
      }
      if (response.status >= 500) console.error('ATLAS API request failed', { url, status: response.status, detail: data });
      throw new Error(this.formatError(data as ApiErrorDetail | null, response.status));
    }
    if (data === null) throw new Error('The API returned an unexpected response. Check the backend URL and proxy configuration.');
    return data;
  },
  async delete<T = unknown>(url: string, body: unknown = null): Promise<T> {
    return this.send<T>(url, { method: 'DELETE', ...(body !== null ? { body: JSON.stringify(body) } : {}) });
  }
};

// ---------- Utility Helpers ----------
export function esc(s: unknown): string {
  return String(s == null ? '' : s);
}

export const LABEL_COLOR: Record<string, string> = {
  Person: '#168568',
  Phone: '#303A36',
  BankAccount: '#168568',
  Vehicle: '#D97706',
  SocialHandle: '#303A36',
  IPAddress: '#303A36',
  Location: '#059669',
  CellTower: '#64748B',
  FIR: '#303A36',
  Crime: '#171C1B',
  PriorCase: '#303A36',
  Case: '#171C1B',
  Transaction: '#168568',
  SourceRecord: '#303A36',
  Organization: '#4338CA',
  Document: '#303A36',
  Device: '#475569',
  Exhibit: '#0F766E'
};

export function getNodeLevel(labels?: string[]): number {
  if (!labels || !labels.length) return 6;
  if (labels.includes('Case')) return 1;
  if (labels.includes('FIR') || labels.includes('PriorCase') || labels.includes('SourceRecord') || labels.includes('Exhibit')) return 2;
  if (labels.includes('Person') || labels.includes('Organization')) return 3;
  if (labels.some((l) => ['Phone', 'BankAccount', 'Vehicle', 'SocialHandle', 'Device'].includes(l))) return 4;
  if (labels.some((l) => ['CellTower', 'Location', 'Transaction'].includes(l))) return 5;
  return 6;
}

export function getDeterministicSeed(str?: string | null): number {
  let hash = 42;
  const s = String(str || 'atlas_seed');
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) - hash) + s.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash) || 42;
}

// ---------- Navigation Config ----------
export const NAV: NavOption[] = [
  { id: 'home', label: 'Home / Portal', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { id: 'overview', label: 'Overview', icon: 'M4 13 9 4l5 9H4Zm6 0 5-8 5 8h-10Z' },
  { id: 'graph', label: 'Graph Explorer', icon: 'M12 3a2 2 0 0 1 2 2c0 .4-.1.8-.3 1.1l3.4 5.4c.3-.1.6-.2.9-.2a2 2 0 1 1 0 4c-.3 0-.6-.1-.9-.2l-3.4 5.4c.2.3.3.7.3 1.1a2 2 0 1 1-3.6-1.1L8.9 15.5c-.3.1-.6.2-.9.2a2 2 0 1 1 0-4c.3 0 .6.1.8.2l3.4-5.4c-.2-.3-.3-.7-.3-1.1a2 2 0 0 1 2-2Z' },
  { id: 'search', label: 'Entity Search', icon: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35' },
  { id: 'path', label: 'Shortest Path', icon: 'M4 5h12m0 0-3-3m3 3-3 3M4 19h12m0 0-3-3m3 3-3 3M8 8v8' },
  { id: 'rankings', label: 'Network rankings', icon: 'M3 17l4-4 4 4 5-5 4 4' },
  { id: 'insights', label: 'Pattern Insights', icon: 'M12 3l1.9 5.6L19 10l-5.1 1.9L12 17.5l-1.9-5.6L5 10l5.1-1.4L12 3Z' },
  { id: 'blockchain', label: 'Case Integrity', icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' },
  { id: 'timeline', label: 'Activity Timeline', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'cases', label: 'Case Registry', icon: 'M3 7a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z' },
  { id: 'ingest', label: 'Upload', icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
  { id: 'board', label: 'Investigation Board', icon: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2' },
  { id: 'reports', label: 'Reports', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' }
];

export const TITLES: Record<string, [string, string]> = {
  home: ['ATLAS', 'Criminal Network Analysis System'],
  overview: ['Your investigations', 'Your cases, evidence, and investigation tools in one place'],
  graph: ['Graph Explorer', 'Interactive topological network visualization'],
  search: ['Entity Search', 'Fast multi-property search across people, phones, bank accounts, VINs'],
  path: ['Trace a connection', 'Find association paths between two entities; inspect the supporting records'],
  rankings: ['Centrality Rankings', 'Degree, PageRank, betweenness, and cross-case relevance'],
  insights: ['Pattern insights', 'Review system-generated leads and examine their case context'],
  blockchain: ['Case Integrity', 'Case-wise verification and cryptographic evidence integrity auditing'],
  timeline: ['Activity Timeline', 'Chronological log of multi-officer case access, verification, and forensic updates'],
  cases: ['Case Registry', 'Manage cases, entity breakdowns, case ingestion, and deletion'],
  ingest: ['Upload', 'Add case records to the existing extraction and graph pipeline'],
  board: ['Investigation Board', 'Officer manual canvas workspace — independent from evidence graph'],
  reports: ['Case Reports', 'Executive investigative dossier, findings, and export center']
};

// ---------- Officer Scope Case Helpers ----------
export function getOfficerUploadedCaseIds(badgeNumber?: string): string[] {
  try {
    const key = badgeNumber ? `atlas_officer_cases_${badgeNumber}` : 'atlas_officer_cases_global';
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

export function addOfficerUploadedCaseId(arg1: string, arg2?: string): void {
  try {
    if (!arg1 && !arg2) return;
    const badges: string[] = ['global'];
    const caseIds: string[] = [];

    if (arg2) {
      badges.push(arg1, arg2);
      caseIds.push(arg1, arg2);
    } else {
      caseIds.push(arg1);
    }

    badges.forEach(b => {
      const existing = getOfficerUploadedCaseIds(b);
      caseIds.forEach(cid => {
        if (!existing.includes(cid)) existing.push(cid);
      });
      localStorage.setItem(`atlas_officer_cases_${b}`, JSON.stringify(existing));
    });
  } catch (e) {
    console.warn('Failed to store officer case link', e);
  }
}

export function removeOfficerUploadedCaseId(badgeNumber: string, caseId: string): void {
  try {
    const existing = getOfficerUploadedCaseIds(badgeNumber);
    const filtered = existing.filter(id => id.toLowerCase() !== caseId.toLowerCase());
    localStorage.setItem(`atlas_officer_cases_${badgeNumber}`, JSON.stringify(filtered));
  } catch (e) {
    console.warn('Failed to remove officer case link', e);
  }
}

export function filterCasesForOfficer(cases: Case[], session: OfficerSession | null): Case[] {
  if (!session) return cases;
  // All authenticated officers have full visibility across department cases.
  return cases;
}



