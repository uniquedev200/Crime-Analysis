import React, { useState, useEffect, useRef, FormEvent, DragEvent, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { CASE_CATEGORIES } from '../services/caseOptions';
import { Case, OfficerSession, addOfficerUploadedCaseId } from '../services/api';
import './evidence-ingestion.css';


export interface DataIngestionModuleProps {
  officerSession: OfficerSession | null;
  fetchCases: () => Promise<Case[]>;
  changeView: (view: string) => void;
  addToast: (msg: string, type?: string) => void;
}

interface EvidenceItem {
  evidence_id: string;
  case_id: string;
  sha256: string;
  filename: string;
  uploader: string;
  uploaded_at: string;
  format: string;
  size: number;
  relative_path: string;
  classification_override: string | null;
  job?: {
    job_id: string;
    status: string;
    stage: string;
    progress: number;
    created_at: string;
    finished_at?: string;
    error?: string;
    warnings: string[];
    classification?: string;
    mention_count: number;
    claim_count: number;
  };
}

type SectionCategory =
  | 'case_details'
  | 'people'
  | 'phones_devices'
  | 'vehicles'
  | 'locations'
  | 'dates_times'
  | 'financial'
  | 'organizations'
  | 'other';

interface GroupedEntity {
  id: string;
  category: SectionCategory;
  label: string;
  value: string;
  normalizedValue: string;
  role: string | null;
  mentionCount: number;
  pages: number[];
  provenances: Array<{ page?: number; sheet?: string; row?: number; snippet?: string }>;
  mentionIds: string[];
}

const SECTION_CONFIG: Array<{ id: SectionCategory; title: string }> = [
  { id: 'case_details', title: 'Case Details' },
  { id: 'people', title: 'People' },
  { id: 'phones_devices', title: 'Phone & Device Details' },
  { id: 'vehicles', title: 'Vehicles' },
  { id: 'locations', title: 'Locations' },
  { id: 'dates_times', title: 'Dates & Times' },
  { id: 'financial', title: 'Financial Details' },
  { id: 'organizations', title: 'Organizations' },
  { id: 'other', title: 'Other Identifiers' }
];

function getCategoryForMention(type: string): { category: SectionCategory; label: string } {
  switch (type) {
    case 'DocumentType':
      return { category: 'case_details', label: 'Document Type' };
    case 'CaseReference':
      return { category: 'case_details', label: 'Case Reference' };
    case 'FIRNumber':
      return { category: 'case_details', label: 'FIR Number' };
    case 'PoliceStation':
      return { category: 'case_details', label: 'Police Station / Dept' };
    case 'IncidentDate':
      return { category: 'case_details', label: 'Incident / Seizure Date' };
    case 'GeneralDiary':
      return { category: 'case_details', label: 'General Diary Ref' };
    case 'LegalReference':
      return { category: 'case_details', label: 'Legal Act / Sec' };

    case 'Person':
      return { category: 'people', label: 'Person' };

    case 'Phone':
      return { category: 'phones_devices', label: 'Phone Number' };
    case 'IMEI':
      return { category: 'phones_devices', label: 'IMEI' };
    case 'IMSI':
      return { category: 'phones_devices', label: 'IMSI' };
    case 'Device':
      return { category: 'phones_devices', label: 'Device / Handset' };

    case 'Vehicle':
      return { category: 'vehicles', label: 'Registration No' };
    case 'Chassis':
      return { category: 'vehicles', label: 'Chassis No' };
    case 'Engine':
      return { category: 'vehicles', label: 'Engine No' };
    case 'VehicleMakeModel':
      return { category: 'vehicles', label: 'Make / Model' };

    case 'Location':
      return { category: 'locations', label: 'Location' };

    case 'Date':
      return { category: 'dates_times', label: 'Date' };
    case 'Time':
      return { category: 'dates_times', label: 'Time' };
    case 'Duration':
      return { category: 'dates_times', label: 'Call Duration' };

    case 'Account':
      return { category: 'financial', label: 'Bank Account' };
    case 'TransactionReference':
      return { category: 'financial', label: 'Transaction Ref' };
    case 'Amount':
      return { category: 'financial', label: 'Amount' };

    case 'Organization':
      return { category: 'organizations', label: 'Organization' };

    case 'Exhibit':
      return { category: 'other', label: 'Exhibit' };
    case 'Seal':
      return { category: 'other', label: 'Evidence Seal' };
    case 'ReportReference':
      return { category: 'other', label: 'Report / Memo Ref' };
    case 'Artifact':
      return { category: 'other', label: 'Forensic Artifact' };
    case 'EvidenceReference':
      return { category: 'other', label: 'Evidence Ref' };
    case 'EventStatement':
      return { category: 'other', label: 'Recorded Observation' };
    default:
      return { category: 'other', label: type };
  }
}

function formatRole(role: string): string {
  const clean = role.trim();
  if (!clean || clean.toLowerCase() === 'none' || clean.toLowerCase() === 'not recorded') {
    return 'Role not verified';
  }
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

function renderProcessingStatus(job?: EvidenceItem['job'], isReviewed?: boolean) {
  const status = isReviewed ? 'Reviewed' : (job?.status || 'Queued');
  const progress = job?.progress ?? 0;
  const errorMsg = job?.error;

  if (status === 'Queued' || status === 'Retry Pending') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge queued">Queued</span>
      </div>
    );
  }

  if (status === 'Processing') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge processing">
          Processing · {progress}%
        </span>
        <div className="mini-progress-bar">
          <div className="mini-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>
    );
  }

  if (status === 'Reviewed') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge completed" style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#16a34a', borderColor: 'rgba(34, 197, 94, 0.3)' }}>
          ✓ Reviewed
        </span>
      </div>
    );
  }

  if (status === 'Completed') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge completed">✓ Completed</span>
      </div>
    );
  }

  if (status === 'Awaiting Review') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge review">Review Required</span>
      </div>
    );
  }


  if (status === 'Failed') {
    return (
      <div className="status-indicator-container">
        <span className="status-badge failed">Failed</span>
        {errorMsg && (
          <span className="status-error-hint" title={errorMsg}>
            {errorMsg}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="status-indicator-container">
      <span className="status-badge queued">{status}</span>
    </div>
  );
}

// Neat Excel Spreadsheet Viewer Component
interface ExcelSpreadsheetViewerProps {
  sources: any[];
  filename: string;
}

function ExcelSpreadsheetViewer({ sources, filename }: ExcelSpreadsheetViewerProps) {
  const [sheetFilter, setSheetFilter] = useState<string>('all');
  const [tableSearch, setTableSearch] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const rowsPerPage = 50;

  // Extract distinct sheet names
  const sheets = useMemo(() => {
    const s = new Set<string>();
    sources.forEach(src => {
      if (src.payload?.sheet) s.add(src.payload.sheet);
    });
    return Array.from(s);
  }, [sources]);

  // Headers: extract from first row payload headers or cell contents
  const rawHeaders: string[] = useMemo(() => {
    for (const src of sources) {
      if (src.payload?.headers && src.payload.headers.length > 0) {
        return src.payload.headers;
      }
    }
    return [];
  }, [sources]);

  // Check if row 1 of sources duplicates the headers
  const dataRows = useMemo(() => {
    if (sources.length === 0) return [];
    const first = sources[0]?.payload;
    if (
      first?.raw_cells &&
      rawHeaders.length > 0 &&
      first.raw_cells.length === rawHeaders.length &&
      first.raw_cells.every((c: string, idx: number) => c === rawHeaders[idx])
    ) {
      return sources.slice(1);
    }
    return sources;
  }, [sources, rawHeaders]);

  // Filter rows by sheet and search query
  const filteredRows = useMemo(() => {
    let list = dataRows;
    if (sheetFilter !== 'all') {
      list = list.filter(r => (r.payload?.sheet || 'Sheet1') === sheetFilter);
    }
    const q = tableSearch.trim().toLowerCase();
    if (q) {
      list = list.filter(r => {
        const cells = r.payload?.raw_cells || [];
        return cells.some((c: any) => String(c).toLowerCase().includes(q));
      });
    }
    return list;
  }, [dataRows, sheetFilter, tableSearch]);

  const totalPages = Math.ceil(filteredRows.length / rowsPerPage) || 1;
  const currentPage = Math.min(page, totalPages);
  const displayedRows = filteredRows.slice((currentPage - 1) * rowsPerPage, currentPage * rowsPerPage);

  return (
    <div className="excel-viewer-container">
      {/* Excel Toolbar */}
      <div className="excel-toolbar">
        <div className="excel-toolbar-left">
          <span className="excel-badge">XLSX</span>
          <span className="excel-file-title" title={filename}>{filename}</span>
          {sheets.length > 1 ? (
            <div className="excel-sheet-tabs">
              <button
                type="button"
                className={`excel-sheet-tab ${sheetFilter === 'all' ? 'active' : ''}`}
                onClick={() => { setSheetFilter('all'); setPage(1); }}
              >
                All Sheets
              </button>
              {sheets.map(sh => (
                <button
                  key={sh}
                  type="button"
                  className={`excel-sheet-tab ${sheetFilter === sh ? 'active' : ''}`}
                  onClick={() => { setSheetFilter(sh); setPage(1); }}
                >
                  {sh}
                </button>
              ))}
            </div>
          ) : sheets[0] ? (
            <span className="excel-sheet-label">Sheet: <strong>{sheets[0]}</strong></span>
          ) : null}
          <span className="excel-row-count">
            {filteredRows.length} rows · {rawHeaders.length} columns
          </span>
        </div>
        <div className="excel-toolbar-right">
          <input
            type="text"
            className="excel-search-input"
            placeholder="Search spreadsheet cells…"
            value={tableSearch}
            onChange={e => { setTableSearch(e.target.value); setPage(1); }}
          />
        </div>
      </div>

      {/* Spreadsheet Grid */}
      <div className="excel-grid-wrapper">
        <table className="excel-grid-table">
          <thead>
            {/* Column Letters Row (A, B, C...) like Excel */}
            <tr className="excel-header-letters">
              <th className="excel-corner-cell">#</th>
              {rawHeaders.map((_, idx) => {
                let letter = '';
                let n = idx;
                while (n >= 0) {
                  letter = String.fromCharCode((n % 26) + 65) + letter;
                  n = Math.floor(n / 26) - 1;
                }
                return (
                  <th key={idx} className="excel-col-letter">
                    {letter}
                  </th>
                );
              })}
            </tr>
            {/* Column Names Row */}
            <tr className="excel-header-names">
              <th className="excel-row-idx-header">Row</th>
              {rawHeaders.map((h, idx) => (
                <th key={idx} className="excel-col-name" title={h}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayedRows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(1, rawHeaders.length + 1)} className="excel-empty-td">
                  No matching tabular records found.
                </td>
              </tr>
            ) : (
              displayedRows.map((r, rIdx) => {
                const cells: string[] = r.payload?.raw_cells || [];
                const rowNum = r.payload?.row || (rIdx + 1);
                return (
                  <tr key={r.source_id || rIdx} className="excel-data-row">
                    <td className="excel-row-num">{rowNum}</td>
                    {rawHeaders.map((_, cIdx) => {
                      const cellVal = cells[cIdx] !== undefined ? String(cells[cIdx]) : '';
                      return (
                        <td key={cIdx} className="excel-cell" title={cellVal}>
                          {cellVal || <span className="excel-cell-empty">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {filteredRows.length > rowsPerPage && (
        <div className="excel-pagination-bar">
          <span className="excel-page-info">
            Showing {(currentPage - 1) * rowsPerPage + 1}–{Math.min(currentPage * rowsPerPage, filteredRows.length)} of {filteredRows.length} rows
          </span>
          <div className="excel-page-buttons">
            <button
              type="button"
              className="neu-btn"
              disabled={currentPage <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              style={{ height: 24, padding: '2px 8px', fontSize: 11 }}
            >
              Previous
            </button>
            <span style={{ fontSize: 11, padding: '0 6px' }}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              className="neu-btn"
              disabled={currentPage >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              style={{ height: 24, padding: '2px 8px', fontSize: 11 }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function DataIngestionModule({
  officerSession,
  fetchCases,
  changeView,
  addToast
}: DataIngestionModuleProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState<'upload' | 'dashboard'>('upload');

  // Case Selection & Upload State
  const [caseId, setCaseId] = useState('');
  const [category, setCategory] = useState('General Investigation');
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [selectionWarning, setSelectionWarning] = useState('');
  const [ingestionProgress, setIngestionProgress] = useState<{
    processed: number;
    total: number;
    currentFileName: string;
    stage: string;
    percent: number;
  } | null>(null);

  // Dashboard & Listing State
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [evidenceCases, setEvidenceCases] = useState<Array<{ case_id: string; category?: string; evidence_count?: number }>>([]);
  const [selectedCaseFilter, setSelectedCaseFilter] = useState<string>('ALL');
  const [loadingEvidence, setLoadingEvidence] = useState(false);

  // Dual-Panel Inspection & Review Modal State
  const [inspectItem, setInspectItem] = useState<EvidenceItem | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [mentions, setMentions] = useState<any[]>([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [classificationInput, setClassificationInput] = useState('');

  // Compact Right-Panel States
  const [searchFilter, setSearchFilter] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<Record<string, boolean>>({});
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [sectionPages, setSectionPages] = useState<Record<string, number>>({});
  const [reviewedIds, setReviewedIds] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('atlas_reviewed_evidence') || '[]'));
    } catch {
      return new Set();
    }
  });


  // Fetch Evidence Cases
  const loadEvidenceCases = useCallback(async () => {
    try {
      const res = await fetch('/api/evidence/cases');
      if (res.ok) {
        const data = await res.json();
        const items = data.items || [];
        setEvidenceCases(items);
        setSelectedCaseFilter(prev => {
          if (prev !== 'ALL' && !items.some((c: any) => c.case_id === prev)) {
            return 'ALL';
          }
          return prev;
        });
        items.forEach((c: { case_id?: string }) => {
          if (c.case_id) {
            if (officerSession?.badgeNumber) addOfficerUploadedCaseId(c.case_id, officerSession.badgeNumber);
            addOfficerUploadedCaseId(c.case_id);
          }
        });
      }
    } catch (e) {
      console.warn('Failed to fetch evidence cases', e);
    }
  }, [officerSession]);

  // Fetch Evidence List
  const loadEvidence = useCallback(async (filterCase?: string) => {
    setLoadingEvidence(true);
    try {
      const c = filterCase !== undefined ? filterCase : selectedCaseFilter;
      const url = c && c !== 'ALL' ? `/api/evidence?case_id=${encodeURIComponent(c)}&limit=200` : '/api/evidence?limit=200';
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setEvidenceList(data.items || []);
      }
    } catch (e) {
      console.warn('Failed to load evidence', e);
    } finally {
      setLoadingEvidence(false);
    }
  }, [selectedCaseFilter]);

  useEffect(() => {
    loadEvidenceCases();
    loadEvidence();
  }, [loadEvidenceCases, loadEvidence]);

  // Polling for active jobs
  useEffect(() => {
    const hasActive = evidenceList.some(
      e => e.job && ['Queued', 'Processing', 'Retry Pending'].includes(e.job.status)
    );
    if (!hasActive) return;
    const interval = setInterval(() => {
      loadEvidence();
    }, 2000);
    return () => clearInterval(interval);
  }, [evidenceList, loadEvidence]);

  // File selection
  const handleSelectFiles = (files: File[]) => {
    setUploadError('');
    setSelectionWarning('');
    const supportedExtensions = /\.(pdf|txt|csv|xls|xlsx|docx|json|png|jpg|jpeg|tiff|bmp)$/i;
    const valid = files.filter(f => supportedExtensions.test(f.name));
    const rejected = files.filter(f => !supportedExtensions.test(f.name));

    if (rejected.length > 0) {
      setSelectionWarning(`Unsupported files skipped: ${rejected.map(f => f.name).join(', ')}. Supported: PDF, Scanned PDF, Images, DOCX, TXT, CSV, XLSX, JSON.`);
    }

    setStagedFiles(prev => {
      const next = [...prev];
      for (const file of valid) {
        if (!next.some(p => p.name === file.name && p.size === file.size)) {
          next.push(file);
        }
      }
      return next;
    });
  };

  // Submit Upload with live per-file progress
  const handleUpload = async (e: FormEvent) => {
    e.preventDefault();
    if (!stagedFiles.length || uploading) return;
    if (!caseId.trim()) {
      setUploadError('Please select or specify a Case / FIR reference.');
      return;
    }
    const uploader = officerSession?.badgeNumber ? `${officerSession.officerName} (${officerSession.badgeNumber})` : 'Lead Investigator';
    const cid = caseId.trim();

    setUploading(true);
    setUploadError('');

    const total = stagedFiles.length;
    let completedCount = 0;
    const errors: string[] = [];

    for (let i = 0; i < total; i++) {
      const file = stagedFiles[i];
      setIngestionProgress({
        processed: i,
        total,
        currentFileName: file.name,
        stage: `Ingesting & extracting forensic entities (${i + 1}/${total})`,
        percent: Math.round((i / total) * 100)
      });

      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('case_id', cid);
        formData.append('category', category.trim() || 'General Investigation');
        formData.append('uploader', uploader);

        const res = await fetch('/api/evidence/upload', {
          method: 'POST',
          body: formData
        });

        if (!res.ok) {
          const errJson = await res.json().catch(() => ({}));
          throw new Error(errJson.detail || errJson.message || `Upload failed with HTTP ${res.status}`);
        }

        completedCount++;
        setIngestionProgress({
          processed: completedCount,
          total,
          currentFileName: file.name,
          stage: completedCount === total ? 'All files ingested & knowledge graph synchronized' : 'Extracted & graph linked',
          percent: Math.round((completedCount / total) * 100)
        });
      } catch (err) {
        errors.push(`${file.name}: ${(err as Error).message || 'Processing failed'}`);
      }
    }

    if (officerSession?.badgeNumber) {
      addOfficerUploadedCaseId(officerSession.badgeNumber, cid);
    }
    addOfficerUploadedCaseId(cid);

    if (errors.length > 0) {
      setUploadError(`Processed ${completedCount} of ${total} files with ${errors.length} issue(s):\n${errors.join('\n')}`);
      addToast(`Ingestion completed with ${errors.length} warning(s)`, 'warn');
    } else {
      addToast(`Preserved, processed and graph-linked all ${completedCount} evidence file(s) for ${cid}!`, 'ok');
      setStagedFiles([]);
    }

    await loadEvidenceCases();
    await loadEvidence(cid);
    setSelectedCaseFilter(cid);
    await fetchCases();

    // Leave the 100% complete state visible briefly before switching tabs
    setTimeout(() => {
      setUploading(false);
      setIngestionProgress(null);
      setActiveTab('dashboard');
    }, 1200);
  };

  // Open Dual-Panel Review Modal
  const openInspectModal = async (item: EvidenceItem) => {
    const updatedJob = item.job ? { ...item.job, status: 'Reviewed' } : item.job;
    const reviewedItem = { ...item, job: updatedJob };
    setInspectItem(reviewedItem);
    setClassificationInput(item.classification_override || item.job?.classification || 'Unknown');
    setLoadingResults(true);
    setExpandedKeys({});
    setEditingKey(null);
    setEditValue('');
    setSearchFilter('');
    setSectionPages({});

    // Mark as reviewed in local state immediately
    setReviewedIds(prev => new Set([...prev, item.evidence_id]));
    setEvidenceList(prev => prev.map(e => e.evidence_id === item.evidence_id ? {
      ...e,
      job: updatedJob
    } : e));

    // Persist to backend and localStorage
    try {
      fetch(`/api/evidence/${item.evidence_id}/reviewed`, { method: 'POST' }).catch(() => {});
      const stored = new Set(JSON.parse(localStorage.getItem('atlas_reviewed_evidence') || '[]'));
      stored.add(item.evidence_id);
      localStorage.setItem('atlas_reviewed_evidence', JSON.stringify(Array.from(stored)));
    } catch {
      // ignore
    }

    try {
      const [srcRes, mentRes] = await Promise.all([
        fetch(`/api/evidence/${item.evidence_id}/results/sources?limit=500`),
        fetch(`/api/evidence/${item.evidence_id}/results/mentions?limit=500`)
      ]);


      if (srcRes.ok) {
        const s = await srcRes.json();
        setSources(s.items || []);
      }
      if (mentRes.ok) {
        const m = await mentRes.json();
        setMentions(m.items || []);
      }
    } catch (err) {
      console.warn('Error loading inspection results', err);
    } finally {
      setLoadingResults(false);
    }
  };

  // Prevent background scroll when inspection modal is open
  useEffect(() => {
    if (inspectItem) {
      const origOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = origOverflow;
      };
    }
  }, [inspectItem]);

  // Retry / Reprocess Evidence
  const handleRetry = async (eid: string) => {
    try {
      const res = await fetch(`/api/evidence/${eid}/retry`, { method: 'POST' });
      if (res.ok) {
        addToast('Evidence processing re-queued', 'info');
        loadEvidence();
        if (inspectItem && inspectItem.evidence_id === eid) {
          openInspectModal(inspectItem);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        addToast(err.detail || 'Failed to retry', 'warn');
      }
    } catch (err) {
      addToast('Error retrying evidence', 'warn');
    }
  };

  // Delete Evidence File
  const handleDeleteEvidence = async (item: EvidenceItem | null) => {
    if (!item) return;
    const confirmMsg = `Permanently delete evidence file "${item.filename}" from ${item.case_id}?\n\nThis will remove the file, extracted entities, and pipeline claims from the database and disk.`;
    if (!window.confirm(confirmMsg)) return;

    const officerName = officerSession?.officerName || 'Investigator';
    const officerBadge = officerSession?.badgeNumber || 'IND-LE-8402';

    try {
      const queryParams = new URLSearchParams({
        officer_name: officerName,
        officer_badge: officerBadge
      });
      const res = await fetch(`/api/evidence/${encodeURIComponent(item.evidence_id)}?${queryParams.toString()}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to delete evidence file');
      }
      addToast(`Evidence file "${item.filename}" deleted successfully.`, 'ok');
      if (inspectItem?.evidence_id === item.evidence_id) {
        setInspectItem(null);
      }
      await loadEvidence();
      await loadEvidenceCases();
    } catch (err: any) {
      console.error('Delete evidence failed:', err);
      addToast(`Failed to delete evidence: ${err.message}`, 'err');
    }
  };

  // Correct Classification
  const handleSaveClassification = async () => {
    if (!inspectItem || !classificationInput) return;
    try {
      const res = await fetch(`/api/evidence/${inspectItem.evidence_id}/classification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: classificationInput,
          reviewer: officerSession?.badgeNumber ? `${officerSession.officerName} (${officerSession.badgeNumber})` : 'Investigator Reviewer'
        })
      });
      if (res.ok) {
        addToast(`Classification updated to ${classificationInput}. Reprocessing started.`, 'ok');
        loadEvidence();
        setInspectItem(null);
      } else {
        const err = await res.json().catch(() => ({}));
        addToast(err.detail || 'Failed to update classification', 'warn');
      }
    } catch (e) {
      addToast('Failed to update classification', 'warn');
    }
  };

  // Manual Correction Submission
  const handleSaveCorrection = async (item: GroupedEntity) => {
    if (!inspectItem || !editValue.trim()) return;
    try {
      const reviewer = officerSession?.badgeNumber ? `${officerSession.officerName} (${officerSession.badgeNumber})` : 'Investigator Reviewer';
      const res = await fetch(`/api/evidence/${inspectItem.evidence_id}/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_type: 'mentions',
          target_id: item.id,
          decision: 'corrected',
          correction: editValue.trim(),
          reviewer
        })
      });
      if (res.ok) {
        setCorrections(prev => ({ ...prev, [item.id]: editValue.trim() }));
        addToast(`Correction recorded for ${item.value}`, 'ok');
        setEditingKey(null);
        setEditValue('');
      } else {
        const err = await res.json().catch(() => ({}));
        addToast(err.detail || 'Correction submission failed', 'warn');
      }
    } catch (e) {
      addToast('Correction submission error', 'warn');
    }
  };

  // Deduplicate and group mentions into the 9 categories
  const groupedData = useMemo(() => {
    const map = new Map<string, GroupedEntity>();

    for (const m of mentions) {
      const p = m.payload || m;
      const { category: cat, label } = getCategoryForMention(p.type);
      const rawVal = (p.raw_value || '').trim();
      let normVal = (p.normalized_value || rawVal).trim();
      if (!rawVal) continue;

      // Canonicalize case references like 'CASE 001' or 'case_001' -> 'CASE_001'
      let canonicalKeyVal = normVal.toLowerCase().replace(/[\s-]+/g, '_');
      if (p.type === 'CaseReference') {
        const mCase = canonicalKeyVal.match(/^case_?(\d+)$/);
        if (mCase) {
          canonicalKeyVal = `case_${mCase[1]}`;
          normVal = `CASE_${mCase[1]}`;
        }
      }

      const key = `${cat}::${p.type}::${canonicalKeyVal}`;
      const prov = p.provenance || {};
      const pageNum = prov.page;

      if (map.has(key)) {
        const existing = map.get(key)!;
        existing.mentionCount++;
        existing.mentionIds.push(p.id);
        if (p.type === 'CaseReference' && rawVal.includes('_') && !existing.value.includes('_')) {
          existing.value = rawVal;
        }
        if (pageNum && !existing.pages.includes(pageNum)) {
          existing.pages.push(pageNum);
          existing.pages.sort((a, b) => a - b);
        }
        if (prov.snippet && !existing.provenances.some(pr => pr.snippet === prov.snippet)) {
          existing.provenances.push({ page: prov.page, sheet: prov.sheet, row: prov.row, snippet: prov.snippet });
        }
        if ((!existing.role || existing.role === 'Role not verified') && p.role) {
          existing.role = formatRole(p.role);
        }
      } else {
        let formattedRole = p.role ? formatRole(p.role) : null;
        if (cat === 'people' && !formattedRole) {
          formattedRole = 'Role not verified';
        }
        map.set(key, {
          id: p.id,
          category: cat,
          label,
          value: p.type === 'CaseReference' ? normVal : rawVal,
          normalizedValue: normVal,
          role: formattedRole,
          mentionCount: 1,
          pages: pageNum ? [pageNum] : [],
          provenances: prov.snippet ? [{ page: prov.page, sheet: prov.sheet, row: prov.row, snippet: prov.snippet }] : [],
          mentionIds: [p.id]
        });
      }
    }

    // Group items into the 9 categories
    const groups: Record<SectionCategory, GroupedEntity[]> = {
      case_details: [],
      people: [],
      phones_devices: [],
      vehicles: [],
      locations: [],
      dates_times: [],
      financial: [],
      organizations: [],
      other: []
    };

    map.forEach(item => {
      groups[item.category].push(item);
    });

    return groups;
  }, [mentions]);

  // Filter sections by search query and exclude empty sections
  const filteredSections = useMemo(() => {
    const q = searchFilter.trim().toLowerCase();
    const result: Array<{ id: SectionCategory; title: string; items: GroupedEntity[] }> = [];

    for (const sec of SECTION_CONFIG) {
      let items = groupedData[sec.id] || [];
      if (q) {
        items = items.filter(
          item =>
            item.value.toLowerCase().includes(q) ||
            item.label.toLowerCase().includes(q) ||
            (item.role && item.role.toLowerCase().includes(q))
        );
      }
      // "Display only sections containing actual extracted data. Do not show empty sections."
      if (items.length > 0) {
        result.push({
          id: sec.id,
          title: sec.title,
          items
        });
      }
    }

    return result;
  }, [groupedData, searchFilter]);

  const totalUniqueEntities = useMemo(() => {
    return Object.values(groupedData).reduce((sum, list) => sum + list.length, 0);
  }, [groupedData]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const ITEMS_PER_SECTION_PAGE = 10;

  return (
    <div className="evidence-workspace-container">
      {/* Header Tabs */}
      <div className="evidence-header-tabs">
        <button
          type="button"
          className={activeTab === 'upload' ? 'active' : ''}
          onClick={() => setActiveTab('upload')}
        >
          Case Evidence Ingestion
        </button>
        <button
          type="button"
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => {
            setActiveTab('dashboard');
            loadEvidence();
          }}
        >
          Data Inspection ({evidenceList.length})
        </button>
      </div>

      {/* Tab 1: Upload Panel */}
      {activeTab === 'upload' && (
        <form onSubmit={handleUpload}>
          <div className="evidence-upload-grid">
            {/* Left: Drag and Drop & Staged Files */}
            <div>
              <div
                className={`evidence-dropzone ${drag ? 'dragging' : ''}`}
                onDragOver={e => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e: DragEvent) => {
                  e.preventDefault();
                  setDrag(false);
                  if (!uploading && e.dataTransfer.files) {
                    handleSelectFiles(Array.from(e.dataTransfer.files));
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="evidence-dropzone-icon" aria-hidden="true">
                  <svg width="52" height="52" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="4.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M 19 46 C 11 44 8 36 12 28 C 15 22 21 21 24 23 C 25 14 31 9 39 10 C 46 11 50 16 51 23 C 57 24 60 30 59 36 C 57 43 51 46 45 46" />
                    <path d="M 23 34 L 32 25 L 41 34" />
                    <path d="M 32 25 V 53" />
                  </svg>
                </div>
                <h3>Drop Evidence Files Here</h3>
                <p>Upload multi-format Indian criminal investigation records.</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.csv,.xls,.xlsx,.docx,.json,.png,.jpg,.jpeg,.tiff,.bmp"
                  style={{ display: 'none' }}
                  onChange={e => {
                    if (e.target.files) {
                      handleSelectFiles(Array.from(e.target.files));
                      e.target.value = '';
                    }
                  }}
                />
                <button
                  type="button"
                  className="neu-btn primary"
                  disabled={uploading}
                  onClick={e => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  Browse Files
                </button>
                <div className="evidence-formats-badge" style={{ marginTop: 14 }}>
                  PDF · Scanned PDF · XLSX · CSV · DOCX · TXT · JSON · Images
                </div>
              </div>

              {selectionWarning && (
                <p style={{ color: '#D97706', fontSize: 12, marginTop: 8 }}>{selectionWarning}</p>
              )}

              {stagedFiles.length > 0 && (
                <div className="staged-files-panel" style={{ marginTop: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 12, fontWeight: 600 }}>
                    <span>Selected Files ({stagedFiles.length})</span>
                    <span>Total: {formatBytes(stagedFiles.reduce((acc, f) => acc + f.size, 0))}</span>
                  </div>
                  {stagedFiles.map((file, idx) => {
                    const isProcessing = ingestionProgress && ingestionProgress.currentFileName === file.name && ingestionProgress.processed < ingestionProgress.total;
                    const isDone = ingestionProgress && idx < ingestionProgress.processed;
                    return (
                      <div
                        className="staged-file-item"
                        key={`${file.name}-${idx}`}
                        style={isProcessing ? { borderColor: 'var(--palette-accent, #2563EB)', background: 'rgba(37,99,235,0.05)' } : undefined}
                      >
                        <div className="staged-file-meta">
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <strong>{file.name}</strong>
                            {isProcessing && (
                              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--palette-accent, #2563EB)', background: 'rgba(37,99,235,0.1)', padding: '1px 6px', borderRadius: 4 }}>
                                ⏳ Ingesting…
                              </span>
                            )}
                            {isDone && (
                              <span style={{ fontSize: 10, fontWeight: 700, color: '#10B981', background: 'rgba(16,185,129,0.1)', padding: '1px 6px', borderRadius: 4 }}>
                                ✓ Processed
                              </span>
                            )}
                          </div>
                          <small>{formatBytes(file.size)} · {file.name.split('.').pop()?.toUpperCase()}</small>
                        </div>
                        <button
                          type="button"
                          className="neu-btn"
                          style={{ padding: '2px 8px', fontSize: 11 }}
                          disabled={uploading}
                          onClick={() => setStagedFiles(stagedFiles.filter((_, i) => i !== idx))}
                        >
                          Remove
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Right: Case Association Controls */}
            <div className="evidence-dashboard-card">
              <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Investigation Case Binding</h3>

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 5 }}>
                  Select Existing Case or Enter FIR
                </label>
                <input
                  className="control"
                  style={{ width: '100%', marginBottom: 6 }}
                  list="existing-evidence-cases"
                  placeholder="e.g. CASE_001 or FIR/104/2026"
                  value={caseId}
                  onChange={e => setCaseId(e.target.value)}
                  required
                />
                <datalist id="existing-evidence-cases">
                  {evidenceCases.map(c => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_id} ({c.evidence_count || 0} files)
                    </option>
                  ))}
                </datalist>
                <small style={{ color: 'var(--palette-secondary)', fontSize: 10 }}>
                  Multiple files will be securely preserved and bound to this case.
                </small>
              </div>

              <div style={{ marginBottom: 18 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 5 }}>
                  Crime Category
                </label>
                <input
                  className="control"
                  style={{ width: '100%' }}
                  list="case-categories-list"
                  placeholder="Select or type crime category (e.g. Cybercrime, Money laundering, Homicide...)"
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                />
                <datalist id="case-categories-list">
                  {CASE_CATEGORIES.map(cat => (
                    <option key={cat} value={cat} />
                  ))}
                </datalist>
              </div>

              {/* Ingestion Progress Live Indicator */}
              {ingestionProgress && (
                <div
                  style={{
                    padding: '12px 14px',
                    borderRadius: 8,
                    border: '1px solid var(--palette-border, #E2E8F0)',
                    background: 'var(--palette-card, #FFFFFF)',
                    marginBottom: 14,
                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--palette-text, #0F172A)' }}>
                      Ingestion Progress
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        fontFamily: 'monospace',
                        color: 'var(--palette-accent, #2563EB)',
                        background: 'rgba(37,99,235,0.08)',
                        padding: '2px 8px',
                        borderRadius: 4
                      }}
                    >
                      {ingestionProgress.processed} / {ingestionProgress.total} Files ({ingestionProgress.percent}%)
                    </span>
                  </div>

                  {/* Progress Bar Track */}
                  <div
                    style={{
                      width: '100%',
                      height: 8,
                      backgroundColor: 'var(--palette-border, #E2E8F0)',
                      borderRadius: 9999,
                      overflow: 'hidden',
                      marginBottom: 8
                    }}
                  >
                    <div
                      style={{
                        width: `${ingestionProgress.percent}%`,
                        height: '100%',
                        backgroundColor: 'var(--palette-accent, #2563EB)',
                        borderRadius: 9999,
                        transition: 'width 0.3s ease-in-out'
                      }}
                    />
                  </div>

                  {/* Status Text & Current File */}
                  <div style={{ fontSize: 11, color: 'var(--palette-secondary, #64748B)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '85%' }}>
                        {ingestionProgress.processed < ingestionProgress.total ? (
                          <>
                            <strong style={{ color: 'var(--palette-text, #1E293B)' }}>Processing:</strong>{' '}
                            <span style={{ fontFamily: 'monospace' }}>{ingestionProgress.currentFileName}</span>
                          </>
                        ) : (
                          <strong style={{ color: '#10B981' }}>✓ All {ingestionProgress.total} files processed successfully!</strong>
                        )}
                      </span>
                    </div>
                    <span style={{ fontSize: 10, fontStyle: 'italic', color: 'var(--palette-secondary, #94A3B8)' }}>
                      {ingestionProgress.stage}
                    </span>
                  </div>
                </div>
              )}

              {uploadError && (
                <div style={{ padding: 10, background: 'rgba(220,38,38,0.1)', color: '#DC2626', borderRadius: 6, fontSize: 11, marginBottom: 12 }}>
                  {uploadError}
                </div>
              )}

              <button
                type="submit"
                className="neu-btn primary"
                style={{ width: '100%', padding: '9px 14px' }}
                disabled={uploading || stagedFiles.length === 0}
              >
                {uploading ? (
                  ingestionProgress
                    ? `Processing File ${Math.min(ingestionProgress.processed + 1, ingestionProgress.total)} of ${ingestionProgress.total} (${ingestionProgress.percent}%)…`
                    : 'Preserving & Queueing…'
                ) : (
                  `Ingest & Process ${stagedFiles.length} Evidence File(s)`
                )}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Tab 2: Dashboard & Pipeline Table */}
      {activeTab === 'dashboard' && (
        <div className="evidence-dashboard-card">
          <div className="evidence-table-toolbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--palette-secondary)' }}>Filter by Case:</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <button
                  type="button"
                  className={`neu-btn ${selectedCaseFilter === 'ALL' ? 'primary' : 'ghost'}`}
                  style={{ padding: '3px 12px', fontSize: 12, borderRadius: 6, fontWeight: 600 }}
                  onClick={() => {
                    setSelectedCaseFilter('ALL');
                    loadEvidence('ALL');
                  }}
                >
                  All Cases ({evidenceCases.reduce((acc, curr) => acc + (curr.evidence_count || 0), 0)})
                </button>
                {evidenceCases.map(c => (
                  <button
                    key={c.case_id}
                    type="button"
                    className={`neu-btn ${selectedCaseFilter === c.case_id ? 'primary' : 'ghost'}`}
                    style={{ padding: '3px 12px', fontSize: 12, borderRadius: 6, fontWeight: 600 }}
                    onClick={() => {
                      setSelectedCaseFilter(c.case_id);
                      loadEvidence(c.case_id);
                    }}
                  >
                    {c.case_id} ({c.evidence_count || 0})
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="neu-btn"
                onClick={() => loadEvidence()}
                disabled={loadingEvidence}
              >
                {loadingEvidence ? 'Refreshing…' : '↻ Refresh Pipeline'}
              </button>
              <button
                type="button"
                className="neu-btn primary"
                onClick={() => setActiveTab('upload')}
              >
                + Ingest More Evidence
              </button>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="evidence-table">
              <thead>
                <tr>
                  <th>Evidence Document</th>
                  <th>Case ID</th>
                  <th>Format</th>
                  <th>Classified Type</th>
                  <th>Processing Status</th>
                  <th>Entities Extracted</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {evidenceList.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: 30, color: 'var(--palette-secondary)' }}>
                      No evidence records found for this selection.
                    </td>
                  </tr>
                ) : (
                  evidenceList.map(item => {
                    const job = item.job;

                    return (
                      <tr key={item.evidence_id}>
                        <td>
                          <strong>{item.filename}</strong>
                          <div style={{ fontSize: 10, color: 'var(--palette-secondary)' }}>
                            {formatBytes(item.size)} · {new Date(item.uploaded_at).toLocaleDateString()}
                          </div>
                        </td>
                        <td>
                          <span style={{ fontWeight: 600 }}>{item.case_id}</span>
                        </td>
                        <td>
                          <span className="stage-pill">
                            {(item.format || 'unknown').toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span style={{ fontWeight: 550, color: 'var(--palette-accent)' }}>
                            {item.classification_override || job?.classification || 'Pending'}
                          </span>
                        </td>
                        <td>
                          {renderProcessingStatus(job, reviewedIds.has(item.evidence_id) || job?.status === 'Reviewed')}
                        </td>

                        <td>
                          <span style={{ fontWeight: 600 }}>{job?.mention_count ?? 0}</span> mentions
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <button
                              type="button"
                              className="neu-btn primary"
                              style={{ padding: '4px 12px', fontSize: 11, fontWeight: 600 }}
                              onClick={() => openInspectModal(item)}
                            >
                              Inspect
                            </button>
                            <button
                              type="button"
                              className="neu-btn danger"
                              style={{ padding: '4px 8px', fontSize: 11, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                              onClick={() => handleDeleteEvidence(item)}
                              title={`Delete evidence file "${item.filename}"`}
                              aria-label={`Delete evidence file "${item.filename}"`}
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Redesigned Dual-Panel Modal: 50% Left Preview, 50% Right Extracted Information */}
      {inspectItem && createPortal(
        <div className="evidence-modal-backdrop" onClick={e => {
          if (e.target === e.currentTarget) setInspectItem(null);
        }}>
          <div className="evidence-dual-modal" role="dialog" aria-modal="true">
            {/* Top Modal Header */}
            <div className="evidence-dual-header">
              <h2>
                <span>{inspectItem.filename}</span>
                <span className="stage-pill">{inspectItem.case_id}</span>
                <span className="stage-pill completed">
                  {inspectItem.classification_override || inspectItem.job?.classification || 'Unknown'}
                </span>
                <span
                  className="stage-pill completed"
                  style={{
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: '#16a34a',
                    border: '1px solid rgba(34, 197, 94, 0.3)',
                    fontWeight: 600
                  }}
                >
                  ✓ Reviewed
                </span>
              </h2>

              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <a
                  href={`/api/evidence/${inspectItem.evidence_id}/original?inline=true`}
                  target="_blank"
                  rel="noreferrer"
                  className="neu-btn"
                  style={{ textDecoration: 'none', fontSize: 11 }}
                  title="Open original evidence in new tab"
                >
                  Open in Tab ↗
                </a>
                <a
                  href={`/api/evidence/${inspectItem.evidence_id}/original`}
                  download={inspectItem.filename}
                  className="neu-btn"
                  style={{ textDecoration: 'none', fontSize: 11 }}
                >
                  Download Original
                </a>
                <button
                  type="button"
                  className="neu-btn danger"
                  style={{ fontSize: 11 }}
                  onClick={() => handleDeleteEvidence(inspectItem)}
                  title="Permanently delete this evidence file"
                >
                  Delete File
                </button>
                <button
                  type="button"
                  className="neu-btn"
                  onClick={() => setInspectItem(null)}
                >
                  Close
                </button>
              </div>
            </div>

            {/* Modal Body: 50% Left Preview, 50% Right Extracted Information */}
            <div className="evidence-dual-body">
              {/* Left Panel (50%): Original Evidence Preview */}
              <div className="evidence-panel-left">
                <div className="panel-sub-header">
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    ORIGINAL SOURCE EVIDENCE PREVIEW
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--palette-secondary)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {formatBytes(inspectItem.size)} · {(inspectItem.format || 'file').toUpperCase()}
                  </span>
                </div>
                {(() => {
                  const fmt = (inspectItem.format || '').toLowerCase().replace(/^\./, '');
                  const isSpreadsheet = ['xlsx', 'xls', 'csv', 'spreadsheet'].includes(fmt) || /\.(xlsx|xls|csv)$/i.test(inspectItem.filename);
                  const isPdf = fmt === 'pdf' || inspectItem.filename.toLowerCase().endsWith('.pdf');
                  const isImage = ['image', 'png', 'jpg', 'jpeg'].includes(fmt) || /\.(png|jpg|jpeg|webp)$/i.test(inspectItem.filename);

                  if (isSpreadsheet) {
                    return (
                      <div style={{ flex: 1, minHeight: 0, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                        <ExcelSpreadsheetViewer sources={sources} filename={inspectItem.filename} />
                      </div>
                    );
                  }

                  return (
                    <div className="panel-content-scroll" style={{ padding: 0 }}>
                      {isPdf ? (
                        <iframe
                          src={`/api/evidence/${inspectItem.evidence_id}/original?inline=true`}
                          title={inspectItem.filename}
                          style={{ width: '100%', height: '100%', border: 0 }}
                        />
                      ) : isImage ? (
                        <div style={{ padding: 16, display: 'flex', justifyContent: 'center' }}>
                          <img
                            src={`/api/evidence/${inspectItem.evidence_id}/original?inline=true`}
                            alt={inspectItem.filename}
                            style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }}
                          />
                        </div>
                      ) : (
                        <div style={{ padding: 16, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>
                          {sources.map(s => s.payload?.text || '').join('\n') || 'Raw record contents preserved on disk.'}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>

              {/* Right Panel (50%): Extracted Information */}
              <div className="evidence-panel-right">
                {/* Header with Classification adjustment */}
                <div className="panel-sub-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 11, color: 'var(--palette-secondary)' }}>Classification:</span>
                    <select
                      className="control"
                      style={{ height: 26, fontSize: 11 }}
                      value={classificationInput}
                      onChange={e => setClassificationInput(e.target.value)}
                    >
                      <option value="FIR">FIR</option>
                      <option value="Police report">Police report</option>
                      <option value="Witness statement">Witness statement</option>
                      <option value="CDR">CDR</option>
                      <option value="Financial record">Financial record</option>
                      <option value="Vehicle record">Vehicle record</option>
                      <option value="Surveillance report">Surveillance report</option>
                      <option value="CCTV/ANPR metadata">CCTV/ANPR metadata</option>
                      <option value="Seizure memo">Seizure memo</option>
                      <option value="Forensic device report">Forensic device report</option>
                      <option value="Forensic findings report">Forensic findings report</option>
                      <option value="Intelligence report">Intelligence report</option>
                      <option value="Criminal history">Criminal history</option>
                      <option value="Social media/OSINT">Social media/OSINT</option>
                      <option value="Unknown">Unknown</option>
                    </select>
                    {classificationInput !== (inspectItem.classification_override || inspectItem.job?.classification) && (
                      <button
                        type="button"
                        className="neu-btn primary"
                        style={{ height: 26, padding: '2px 8px', fontSize: 10 }}
                        onClick={handleSaveClassification}
                      >
                        Save & Reprocess
                      </button>
                    )}
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--palette-secondary)' }}>
                    {totalUniqueEntities} Unique Entities ({mentions.length} Mentions)
                  </span>
                </div>

                {/* Extracted Information Header (Single Heading, Tabs Removed) */}
                <div className="extracted-info-header">
                  <div className="extracted-info-title-row">
                    <h3>Extracted Information</h3>
                    <span className="extracted-info-meta">
                      {totalUniqueEntities} unique entities identified
                    </span>
                  </div>
                  <input
                    type="text"
                    className="extracted-search-input"
                    placeholder="Search extracted entities, roles, or identifiers…"
                    value={searchFilter}
                    onChange={e => setSearchFilter(e.target.value)}
                  />
                </div>

                {/* Categorized Information Sections */}
                <div className="panel-content-scroll">
                  {loadingResults ? (
                    <div style={{ padding: 30, textAlign: 'center', color: 'var(--palette-secondary)' }}>
                      Extracting and categorizing evidence details…
                    </div>
                  ) : filteredSections.length === 0 ? (
                    <div style={{ padding: 30, textAlign: 'center', color: 'var(--palette-secondary)', fontSize: 12 }}>
                      {searchFilter ? 'No matching extracted entities found.' : 'No entities extracted for this record.'}
                    </div>
                  ) : (
                    filteredSections.map(section => {
                      const currentPage = sectionPages[section.id] || 1;
                      const totalItems = section.items.length;
                      const totalPages = Math.ceil(totalItems / ITEMS_PER_SECTION_PAGE);
                      const startIndex = (currentPage - 1) * ITEMS_PER_SECTION_PAGE;
                      const paginatedItems = section.items.slice(startIndex, startIndex + ITEMS_PER_SECTION_PAGE);

                      return (
                        <div className="extracted-section" key={section.id}>
                          {/* Section Header */}
                          <div className="extracted-section-header">
                            <h4>{section.title}</h4>
                            <span className="extracted-section-count">{totalItems}</span>
                          </div>

                          {/* Section Compact Rows */}
                          <div>
                            {paginatedItems.map(item => {
                              const isExpanded = !!expandedKeys[item.id];
                              const isEditing = editingKey === item.id;
                              const correctedVal = corrections[item.id];
                              const displayVal = correctedVal || item.value;

                              return (
                                <div className="compact-info-row-container" key={item.id}>
                                  <div
                                    className="compact-info-row"
                                    onClick={() => {
                                      setExpandedKeys(prev => ({
                                        ...prev,
                                        [item.id]: !prev[item.id]
                                      }));
                                    }}
                                  >
                                    <div className="compact-info-left">
                                      <span className="compact-field-label">{item.label}</span>
                                      <span className="compact-field-value">{displayVal}</span>
                                      {item.role && (
                                        <span className="compact-field-role">
                                          — {item.role}
                                        </span>
                                      )}
                                      {item.mentionCount > 1 && (
                                        <span className="compact-field-occurrences">
                                          ({item.mentionCount}× {item.pages.length ? `· p. ${item.pages.join(', ')}` : ''})
                                        </span>
                                      )}
                                    </div>

                                    <div className="compact-info-actions" onClick={e => e.stopPropagation()}>
                                      <button
                                        type="button"
                                        className="compact-edit-btn"
                                        title="Manually correct entity"
                                        onClick={() => {
                                          if (isEditing) {
                                            setEditingKey(null);
                                          } else {
                                            setEditingKey(item.id);
                                            setEditValue(displayVal);
                                          }
                                        }}
                                      >
                                        ✎
                                      </button>
                                      <span
                                        className={`compact-expand-icon ${isExpanded ? 'expanded' : ''}`}
                                        title={isExpanded ? 'Collapse source details' : 'Expand source details'}
                                        onClick={() => {
                                          setExpandedKeys(prev => ({
                                            ...prev,
                                            [item.id]: !prev[item.id]
                                          }));
                                        }}
                                        style={{ cursor: 'pointer' }}
                                      >
                                        ▼
                                      </span>
                                    </div>
                                  </div>

                                  {/* Inline Edit Correction Form */}
                                  {isEditing && (
                                    <div className="compact-edit-row" onClick={e => e.stopPropagation()}>
                                      <input
                                        className="compact-edit-input"
                                        value={editValue}
                                        onChange={e => setEditValue(e.target.value)}
                                        autoFocus
                                      />
                                      <button
                                        type="button"
                                        className="neu-btn primary"
                                        style={{ padding: '2px 8px', fontSize: 10, height: 24 }}
                                        onClick={() => handleSaveCorrection(item)}
                                      >
                                        Save
                                      </button>
                                      <button
                                        type="button"
                                        className="neu-btn"
                                        style={{ padding: '2px 8px', fontSize: 10, height: 24 }}
                                        onClick={() => setEditingKey(null)}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  )}

                                  {/* Expandable Source Provenance Snippet */}
                                  {isExpanded && (
                                    <div className="compact-provenance-area">
                                      <div className="provenance-pages-line">
                                        Source: {item.pages.length ? `Page ${item.pages.join(', ')}` : 'Document body'}
                                        {item.provenances[0]?.sheet ? ` · Sheet: ${item.provenances[0].sheet}` : ''}
                                        {item.provenances[0]?.row ? ` · Row: ${item.provenances[0].row}` : ''}
                                      </div>
                                      {item.provenances[0]?.snippet && (
                                        <div className="provenance-snippet-text">
                                          "{item.provenances[0].snippet.slice(0, 180)}…"
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>

                          {/* Pagination controls for large files / sections (e.g. CDR files) */}
                          {totalPages > 1 && (
                            <div className="compact-section-pagination">
                              <span>
                                Showing {startIndex + 1}–{Math.min(startIndex + ITEMS_PER_SECTION_PAGE, totalItems)} of {totalItems}
                              </span>
                              <div style={{ display: 'flex', gap: 6 }}>
                                <button
                                  type="button"
                                  disabled={currentPage <= 1}
                                  onClick={() => {
                                    setSectionPages(prev => ({
                                      ...prev,
                                      [section.id]: Math.max(1, currentPage - 1)
                                    }));
                                  }}
                                >
                                  ← Prev
                                </button>
                                <span>{currentPage} / {totalPages}</span>
                                <button
                                  type="button"
                                  disabled={currentPage >= totalPages}
                                  onClick={() => {
                                    setSectionPages(prev => ({
                                      ...prev,
                                      [section.id]: Math.min(totalPages, currentPage + 1)
                                    }));
                                  }}
                                >
                                  Next →
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
