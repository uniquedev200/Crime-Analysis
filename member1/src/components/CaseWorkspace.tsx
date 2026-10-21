import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { API, Case, OfficerSession } from '../services/api';
import { UploadedCaseFile } from '../services/fileStore';
import { caseCategory, caseUpdated, displayDate } from '../services/workspace';
import { GraphExplorerModuleProps } from './GraphExplorerModule';

export interface FindingAttachment {
  attachment_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  uploaded_by?: string;
}

export interface CaseFindingNote {
  finding_id: string;
  case_id: string;
  title: string;
  category: string;
  content: string;
  officer_name?: string;
  officer_badge?: string;
  severity?: string;
  created_at: string;
  updated_at?: string;
  attachments?: FindingAttachment[];
}

type Props = GraphExplorerModuleProps & {
  record: Case | null;
  loadingDetail: boolean;
  retry: () => void;
  files: UploadedCaseFile[];
  viewFile: (file: UploadedCaseFile) => void;
  attach: () => void;
  dossier: () => void;
  deleteCase: () => void;
  officerSession?: OfficerSession | null;
};

const FINDING_CATEGORIES = [
  'Critical Lead',
  'Suspect Observation',
  'Alibi Verification',
  'Witness Statement',
  'Financial Clue',
  'Telecom / CDR Lead',
  'Forensic Device',
  'Surveillance Sighting',
  'General Note'
];

const ALLOWED_ATTACHMENT_EXTS = ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx', '.csv'];
const MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024; // 25 MB

function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(filename: string) {
  const ext = '.' + filename.split('.').pop()?.toLowerCase();
  if (ext === '.pdf') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="9" y1="15" x2="15" y2="15"></line>
      </svg>
    );
  }
  if (ext === '.xlsx' || ext === '.csv') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#16A34A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="8" y1="13" x2="16" y2="13"></line>
        <line x1="8" y1="17" x2="16" y2="17"></line>
        <line x1="12" y1="9" x2="12" y2="21"></line>
      </svg>
    );
  }
  if (ext === '.jpg' || ext === '.jpeg' || ext === '.png') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <circle cx="8.5" cy="8.5" r="1.5"></circle>
        <polyline points="21 15 16 10 5 21"></polyline>
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
    </svg>
  );
}

export function CaseWorkspace(props: Props) {
  const { selectedCase, record, loadingDetail, officerSession } = props;
  const [tab, setTab] = useState<'Summary' | 'Case Files' | 'Findings'>('Summary');
  const [findings, setFindings] = useState<CaseFindingNote[]>([]);
  const [loadingFindings, setLoadingFindings] = useState<boolean>(false);

  // Case Evidence Files State
  const [caseEvidenceFiles, setCaseEvidenceFiles] = useState<any[]>([]);
  const [loadingCaseFiles, setLoadingCaseFiles] = useState<boolean>(false);

  const fetchCaseEvidenceFiles = useCallback(async () => {
    if (!selectedCase) return;
    setLoadingCaseFiles(true);
    try {
      const res = await fetch(`/api/evidence?case_id=${encodeURIComponent(selectedCase)}`);
      if (res.ok) {
        const data = await res.json();
        setCaseEvidenceFiles(data.items || []);
      }
    } catch (e) {
      console.warn('Failed to fetch case evidence files', e);
    } finally {
      setLoadingCaseFiles(false);
    }
  }, [selectedCase]);

  useEffect(() => {
    fetchCaseEvidenceFiles();
  }, [fetchCaseEvidenceFiles]);

  const handleDeleteCaseEvidence = async (item: any) => {
    const confirmMsg = `Permanently delete "${item.filename}" from ${selectedCase}?\n\nThis will remove the file from case records, pipeline extraction, and data inspections.`;
    if (!window.confirm(confirmMsg)) return;

    const officerName = officerSession?.officerName || (record?.lead_investigator as string) || 'Investigator';
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
      props.addToast?.(`Evidence file "${item.filename}" deleted.`, 'ok');
      await fetchCaseEvidenceFiles();
    } catch (err: any) {
      props.addToast?.(`Delete failed: ${err.message}`, 'err');
    }
  };

  // Officer Note Form state
  const [newTitle, setNewTitle] = useState('');
  const [newCategory, setNewCategory] = useState(FINDING_CATEGORIES[0]);
  const [newSeverity, setNewSeverity] = useState('HIGH');
  const [newContent, setNewContent] = useState('');
  const [submittingNote, setSubmittingNote] = useState(false);
  const [noteError, setNoteError] = useState('');

  // Supporting Documents upload state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<{ url: string; filename: string; mime?: string } | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  // Storage key for localStorage cache
  const localCacheKey = useMemo(() => `atlas_findings_${selectedCase}`, [selectedCase]);

  // Load findings on mount or selectedCase change
  useEffect(() => {
    if (!selectedCase) return;
    setTab('Summary');
    setLoadingFindings(true);

    // Initial cache read
    try {
      const cached = localStorage.getItem(localCacheKey);
      if (cached) {
        setFindings(JSON.parse(cached));
      }
    } catch {
      // ignore JSON parse error
    }

    // Fetch from backend
    API.get<CaseFindingNote[]>(`/api/cases/${encodeURIComponent(selectedCase)}/findings`)
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setFindings(data);
          try {
            localStorage.setItem(localCacheKey, JSON.stringify(data));
          } catch {
            // ignore localStorage quota
          }
        }
      })
      .catch(err => {
        console.warn('Could not fetch backend case findings, using local cache:', err);
      })
      .finally(() => {
        setLoadingFindings(false);
      });
  }, [selectedCase, localCacheKey]);

  // Handle files selected via file dialog or drag & drop
  const handleFilesSelected = (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    const validFiles: File[] = [];
    const errors: string[] = [];

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_ATTACHMENT_EXTS.includes(ext)) {
        errors.push(`${file.name}: unsupported format. Supported: PDF, JPG, PNG, DOCX, XLSX, CSV`);
        continue;
      }
      if (file.size > MAX_ATTACHMENT_SIZE) {
        errors.push(`${file.name}: exceeds maximum size (25MB)`);
        continue;
      }
      if (selectedFiles.some(f => f.name === file.name && f.size === file.size)) {
        continue;
      }
      validFiles.push(file);
    }

    if (errors.length > 0) {
      setNoteError(errors.join('. '));
    } else {
      setNoteError('');
    }

    if (validFiles.length > 0) {
      setSelectedFiles(prev => [...prev, ...validFiles]);
    }
  };

  const handleRemoveSelectedFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Save new finding note (with optional supporting documents)
  const handleAddFinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCase) return;
    if (!newContent.trim()) {
      setNoteError('Please enter finding details before saving.');
      return;
    }
    setNoteError('');
    setSubmittingNote(true);

    const officerName = officerSession?.officerName || (record?.lead_investigator as string) || 'Investigating Officer';
    const officerBadge = officerSession?.badgeNumber || 'PS-1001';

    try {
      let res: CaseFindingNote;
      if (selectedFiles.length > 0) {
        const formData = new FormData();
        formData.append('title', newTitle.trim() || `${newCategory} Observation`);
        formData.append('category', newCategory);
        formData.append('severity', newSeverity);
        formData.append('content', newContent.trim());
        formData.append('officer_name', officerName);
        formData.append('officer_badge', officerBadge);
        for (const file of selectedFiles) {
          formData.append('files', file);
        }

        res = await API.send<CaseFindingNote>(`/api/cases/${encodeURIComponent(selectedCase)}/findings`, {
          method: 'POST',
          body: formData,
          form: true
        });
      } else {
        const payload = {
          title: newTitle.trim() || `${newCategory} Observation`,
          category: newCategory,
          severity: newSeverity,
          content: newContent.trim(),
          officer_name: officerName,
          officer_badge: officerBadge
        };
        res = await API.post<CaseFindingNote>(`/api/cases/${encodeURIComponent(selectedCase)}/findings`, payload);
      }

      const updated = [res, ...findings.filter(f => f.finding_id !== res.finding_id)];
      setFindings(updated);
      try {
        localStorage.setItem(localCacheKey, JSON.stringify(updated));
      } catch {
        // ignore
      }
      // Reset form
      setNewTitle('');
      setNewContent('');
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (props.addToast) {
        props.addToast('Officer finding note recorded successfully!', 'ok');
      }
    } catch (err: any) {
      console.warn('Error saving finding note:', err);
      // Local fallback
      const fallbackNote: CaseFindingNote = {
        finding_id: `local_${Date.now()}`,
        case_id: selectedCase,
        title: newTitle.trim() || `${newCategory} Observation`,
        category: newCategory,
        severity: newSeverity,
        content: newContent.trim(),
        officer_name: officerName,
        officer_badge: officerBadge,
        created_at: new Date().toISOString(),
        attachments: []
      };
      const updated = [fallbackNote, ...findings];
      setFindings(updated);
      try {
        localStorage.setItem(localCacheKey, JSON.stringify(updated));
      } catch {
        // ignore
      }
      setNewTitle('');
      setNewContent('');
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (props.addToast) {
        props.addToast('Finding note saved.', 'ok');
      }
    } finally {
      setSubmittingNote(false);
    }
  };

  // Delete finding note
  const handleDeleteFinding = async (findingId: string) => {
    if (!selectedCase) return;
    try {
      await API.delete(`/api/cases/${encodeURIComponent(selectedCase)}/findings/${encodeURIComponent(findingId)}`);
    } catch (err) {
      console.warn('Backend delete finding warning:', err);
    }
    const updated = findings.filter(f => f.finding_id !== findingId);
    setFindings(updated);
    try {
      localStorage.setItem(localCacheKey, JSON.stringify(updated));
    } catch {
      // ignore
    }
    if (props.addToast) {
      props.addToast('Finding note removed.', 'info');
    }
  };

  // Download finding attachment
  const handleDownloadAttachment = (findingId: string, att: FindingAttachment) => {
    if (!selectedCase) return;
    const url = `/api/cases/${encodeURIComponent(selectedCase)}/findings/${encodeURIComponent(findingId)}/attachments/${encodeURIComponent(att.attachment_id)}/download`;
    const link = document.createElement('a');
    link.href = url;
    link.download = att.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Preview finding attachment
  const handlePreviewAttachment = (findingId: string, att: FindingAttachment) => {
    if (!selectedCase) return;
    const url = `/api/cases/${encodeURIComponent(selectedCase)}/findings/${encodeURIComponent(findingId)}/attachments/${encodeURIComponent(att.attachment_id)}/preview`;
    setPreviewDoc({ url, filename: att.filename, mime: att.file_type });
  };

  // Delete finding attachment
  const handleDeleteAttachment = async (findingId: string, attachmentId: string) => {
    if (!selectedCase) return;
    try {
      await API.delete(`/api/cases/${encodeURIComponent(selectedCase)}/findings/${encodeURIComponent(findingId)}/attachments/${encodeURIComponent(attachmentId)}`);
    } catch (err) {
      console.warn('Backend delete attachment warning:', err);
    }
    const updated = findings.map(f => {
      if (f.finding_id === findingId) {
        return {
          ...f,
          attachments: (f.attachments || []).filter(a => a.attachment_id !== attachmentId)
        };
      }
      return f;
    });
    setFindings(updated);
    try {
      localStorage.setItem(localCacheKey, JSON.stringify(updated));
    } catch {
      // ignore
    }
    if (props.addToast) {
      props.addToast('Attachment removed.', 'info');
    }
  };

  // Summary, Case Files, and Findings tabs
  const tabs: Array<'Summary' | 'Case Files' | 'Findings'> = ['Summary', 'Case Files', 'Findings'];

  return (
    <div className="selected-case-workspace">
      {/* CASE WORKSPACE HEADER */}
      <header className="case-workspace-header">
        <div>
          {/* Back button with 50% round pill shape and arrow SVG */}
          <button
            type="button"
            className="neu-btn ghost back-button"
            onClick={() => props.setSelectedCase(null)}
            style={{ borderRadius: '9999px', padding: '6px 16px', display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Back
          </button>
          <h2 style={{ margin: '0 0 6px', fontSize: '24px', fontWeight: 700 }}>
            {record?.case_name || selectedCase}
          </h2>
          <p style={{ margin: '2px 0 0', fontSize: '12.5px', color: 'var(--palette-secondary, #64748B)' }}>
            <span>{String(record?.police_station || record?.station || record?.jurisdiction || 'State Police Jurisdiction')}</span>
            {' · '}
            <span>{String(record?.lead_investigator || record?.assigned_officer || 'Officer not recorded')}</span>
            {' '}
            <span className="tag plain" style={{ textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 600 }}>
              {String(record?.status || 'Under Investigation').replace(/_/g, ' ')}
            </span>
          </p>
        </div>

        {/* NEUMORPHIC PILL ACTION BUTTONS */}
        <div className="case-header-actions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button className="neu-btn ghost" onClick={props.dossier} title="Generate AI Executive Dossier">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            AI dossier
          </button>

          {/* Delete case button using ONLY the trash icon symbol, no word delete */}
          <button
            className="neu-btn danger icon-btn"
            onClick={props.deleteCase}
            title="Delete case"
            aria-label="Delete case"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      </header>

      {/* TABS: Summary, Case Files, Findings */}
      <nav className="case-workspace-tabs" aria-label="Case views">
        {tabs.map(name => (
          <button
            key={name}
            aria-current={tab === name ? 'page' : undefined}
            onClick={() => setTab(name)}
          >
            {name === 'Case Files' && caseEvidenceFiles.length > 0
              ? `Case Files (${caseEvidenceFiles.length})`
              : name === 'Findings' && findings.length > 0
              ? `Findings (${findings.length})`
              : name}
          </button>
        ))}
      </nav>

      {/* CASE CONTENT VIEW PANEL */}
      <section className="card case-view-panel">
        {loadingDetail ? (
          <div role="status" aria-label="Loading case details" style={{ padding: '24px 0' }}>
            <div className="skeleton sk-row" />
            <div className="skeleton sk-row" style={{ width: '80%', marginTop: '12px' }} />
            <div className="skeleton sk-row" style={{ width: '60%', marginTop: '12px' }} />
          </div>
        ) : !record ? (
          <div className="workspace-error-panel" role="alert">
            <strong>Case details are temporarily unavailable.</strong>
            <button className="neu-btn ghost" onClick={props.retry}>
              Retry
            </button>
          </div>
        ) : (
          <>
            {/* TAB: SUMMARY */}
            {tab === 'Summary' && (
              <div>
                <div className="card-header" style={{ marginBottom: '16px' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Case Particulars & Registry Details</h3>
                  <span className="workspace-muted" style={{ fontSize: '11.5px' }}>
                    Record updated {displayDate(caseUpdated(record))}
                  </span>
                </div>

                {/* NEATLY ORDERED STRUCTURED CASE DETAILS */}
                <div className="case-overview-structured">
                  {/* Card 1: Identification & Legal Status */}
                  <div className="case-detail-card">
                    <h4>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                      Docket Particulars
                    </h4>
                    <div className="case-field-list">
                      <div className="case-field-row">
                        <span className="case-field-label">Case ID / Reference</span>
                        <span className="case-field-value mono">{record.case_id}</span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">FIR Reference Number</span>
                        <span className="case-field-value mono font-semibold" style={{ color: 'var(--palette-accent, #2E5A88)' }}>
                          {record.fir_number || `FIR/${record.case_id}`}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Crime Classification</span>
                        <span className="case-field-value">{caseCategory(record)}</span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Investigation Status</span>
                        <span className="case-field-value">
                          <span className="tag plain" style={{ display: 'inline-block', padding: '2px 8px', fontSize: '11px', fontWeight: 600 }}>
                            {String(record.status || 'Under Investigation').replace(/_/g, ' ')}
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 2: Occurrence Specifics (FIR) */}
                  <div className="case-detail-card">
                    <h4>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                      </svg>
                      Incident Occurrence
                    </h4>
                    <div className="case-field-list">
                      <div className="case-field-row">
                        <span className="case-field-label">Date of Occurrence</span>
                        <span className="case-field-value font-semibold">
                          {String(record.occurrence_date || record.incident_date || record.date || 'Not recorded')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Occurrence Time Window</span>
                        <span className="case-field-value">
                          {String(record.occurrence_time || '18:30 – 18:50 hrs')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Place of Occurrence (Scene)</span>
                        <span className="case-field-value">
                          {String(record.place_of_occurrence || record.jurisdiction || 'Not recorded')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Properties Stolen / Involved Value</span>
                        <span className="case-field-value font-semibold" style={{ color: '#0F766E' }}>
                          {String(record.total_value || 'INR 72,000')}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 3: Officers & Informant */}
                  <div className="case-detail-card">
                    <h4>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                        <circle cx="12" cy="7" r="4"></circle>
                      </svg>
                      Officers & Informant
                    </h4>
                    <div className="case-field-list">
                      <div className="case-field-row">
                        <span className="case-field-label">Complainant / Informant</span>
                        <span className="case-field-value font-semibold">
                          {String(record.complainant || (record as any).victim || 'Rita Sen (Workshop Manager)')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Assigned Investigating Officer</span>
                        <span className="case-field-value font-semibold">
                          {String(record.lead_investigator || record.assigned_officer || 'Inspector Anaya Sen')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Police Station / Beat Jurisdiction</span>
                        <span className="case-field-value">
                          {String(record.police_station || record.jurisdiction || 'Nandipur East Police Station')}
                        </span>
                      </div>
                      <div className="case-field-row">
                        <span className="case-field-label">Case Priority</span>
                        <span className="case-field-value">
                          <span className="badge-severity medium" style={{ display: 'inline-block', padding: '2px 8px' }}>
                            {String(record.priority || 'MEDIUM')}
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* DEDICATED FIR STATEMENT & NARRATIVE CARD */}
                <div className="fir-statement-card">
                  <div className="fir-card-header">
                    <div className="fir-title-group">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--palette-accent, #2E5A88)' }} aria-hidden="true">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                          <polyline points="14 2 14 8 20 8"></polyline>
                          <line x1="16" y1="13" x2="8" y2="13"></line>
                          <line x1="16" y1="17" x2="8" y2="17"></line>
                          <polyline points="10 9 9 9 8 9"></polyline>
                        </svg>
                        <h3>First Information Report (F.I.R.) Official Statement</h3>
                      </div>
                      <p>Verbatim incident statement recorded under Section 154 Cr.P.C (Item 12 F.I.R. Contents)</p>
                    </div>

                    <span className="fir-clue-pill mono" style={{ fontSize: '11px', background: 'var(--palette-selected, #F1F5F9)' }}>
                      FIR REF: {record.fir_number || `SYN-E-0001/2026`}
                    </span>
                  </div>

                  {/* FIR Content Body */}
                  <div className="fir-statement-box">
                    {String(record.fir_description || record.summary || 'No FIR description supplied.')}
                  </div>

                  {/* FIR Clue & Entity Highlights */}
                  <div className="fir-tags-row">
                    {Boolean(record.complainant) && (
                      <span className="fir-clue-pill">
                        👤 Complainant: <strong>{String(record.complainant)}</strong>
                      </span>
                    )}
                    {Boolean(record.place_of_occurrence) && (
                      <span className="fir-clue-pill">
                        📍 Scene: <strong>{String(record.place_of_occurrence)}</strong>
                      </span>
                    )}
                    {Boolean(record.total_value) && (
                      <span className="fir-clue-pill">
                        💰 Valuation: <strong>{String(record.total_value)}</strong>
                      </span>
                    )}
                    {Boolean(record.occurrence_time) && (
                      <span className="fir-clue-pill">
                        🕒 Time: <strong>{String(record.occurrence_time)}</strong>
                      </span>
                    )}
                  </div>

                </div>
              </div>
            )}

            {/* TAB: CASE EVIDENCE FILES */}
            {tab === 'Case Files' && (
              <div className="case-evidence-manager">
                <div className="card-header" style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Case Evidence Documents & Source Files</h3>
                    <p className="workspace-muted" style={{ margin: '4px 0 0', fontSize: '11.5px' }}>
                      Official investigation documents, digital forensics, CDRs, and reports registered under {selectedCase}.
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      className="neu-btn ghost"
                      onClick={fetchCaseEvidenceFiles}
                      disabled={loadingCaseFiles}
                      style={{ fontSize: '11px' }}
                    >
                      {loadingCaseFiles ? 'Refreshing…' : '↻ Refresh'}
                    </button>
                    <button
                      type="button"
                      className="neu-btn primary"
                      onClick={props.attach}
                      style={{ fontSize: '11px', fontWeight: 600 }}
                    >
                      + Attach File
                    </button>
                  </div>
                </div>

                {loadingCaseFiles ? (
                  <div role="status" style={{ padding: '24px 0' }}>
                    <div className="skeleton sk-row" />
                    <div className="skeleton sk-row" style={{ width: '80%', marginTop: '10px' }} />
                  </div>
                ) : caseEvidenceFiles.length === 0 ? (
                  <div className="investigation-empty" style={{ padding: '36px 16px', textAlign: 'center' }}>
                    <p style={{ color: 'var(--palette-secondary)', fontSize: '13px', margin: '0 0 12px' }}>
                      No evidence documents or source files found for this case.
                    </p>
                    <button type="button" className="neu-btn primary" onClick={props.attach}>
                      + Upload Case Evidence
                    </button>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="evidence-table" style={{ width: '100%', fontSize: '12px' }}>
                      <thead>
                        <tr>
                          <th>Document</th>
                          <th>Format</th>
                          <th>Classification</th>
                          <th>Status</th>
                          <th>Extracted Mentions</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {caseEvidenceFiles.map(file => (
                          <tr key={file.evidence_id}>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                {getFileIcon(file.filename)}
                                <div>
                                  <strong>{file.filename}</strong>
                                  <div style={{ fontSize: '10px', color: 'var(--palette-secondary)' }}>
                                    {formatAttachmentSize(file.size || 0)} · {new Date(file.uploaded_at).toLocaleDateString()}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className="stage-pill">{(file.format || 'unknown').toUpperCase()}</span>
                            </td>
                            <td>
                              <span style={{ fontWeight: 600, color: 'var(--palette-accent)' }}>
                                {file.classification_override || file.job?.classification || 'Pending'}
                              </span>
                            </td>
                            <td>
                              <span className="tag plain">{file.job?.status || 'Uploaded'}</span>
                            </td>
                            <td>
                              <span style={{ fontWeight: 600 }}>{file.job?.mention_count ?? 0}</span> mentions
                            </td>
                            <td>
                              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                <a
                                  href={`/api/evidence/${file.evidence_id}/original?inline=true`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="neu-btn"
                                  style={{ padding: '4px 10px', fontSize: '11px', textDecoration: 'none' }}
                                  title="View original file"
                                >
                                  View
                                </a>
                                <a
                                  href={`/api/evidence/${file.evidence_id}/original`}
                                  download={file.filename}
                                  className="neu-btn"
                                  style={{ padding: '4px 10px', fontSize: '11px', textDecoration: 'none' }}
                                  title="Download file"
                                >
                                  Download
                                </a>
                                <button
                                  type="button"
                                  className="neu-btn danger"
                                  style={{ padding: '4px 8px', fontSize: '11px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                                  onClick={() => handleDeleteCaseEvidence(file)}
                                  title={`Delete "${file.filename}"`}
                                  aria-label={`Delete "${file.filename}"`}
                                >
                                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                    <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                  </svg>
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* TAB: FINDINGS (OFFICER NOTE TAKING) */}
            {tab === 'Findings' && (
              <div className="case-findings-manager">
                {/* NOTE COMPOSER FORM FOR INVESTIGATING OFFICERS */}
                <div className="findings-composer-card">
                  <div className="findings-composer-header">
                    <h3>Investigative Findings & Case Notes</h3>
                    <p>Enter field observations, verification leads, suspect deductions, or interview notes related to this investigation.</p>
                  </div>

                  <form onSubmit={handleAddFinding}>
                    <div className="findings-form-grid">
                      <div className="field">
                        <label>Finding Title / Subject</label>
                        <input
                          className="control"
                          placeholder="e.g. CCTV Lead on White Delivery Van, Alibi Inconsistency..."
                          value={newTitle}
                          onChange={e => setNewTitle(e.target.value)}
                        />
                      </div>

                      <div className="field">
                        <label>Finding Category</label>
                        <select
                          className="control"
                          value={newCategory}
                          onChange={e => setNewCategory(e.target.value)}
                        >
                          {FINDING_CATEGORIES.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </div>

                      <div className="field">
                        <label>Priority / Severity</label>
                        <select
                          className="control"
                          value={newSeverity}
                          onChange={e => setNewSeverity(e.target.value)}
                        >
                          <option value="HIGH">High Priority</option>
                          <option value="MEDIUM">Medium Priority</option>
                          <option value="LOW">Low Priority</option>
                        </select>
                      </div>
                    </div>

                    <div className="field" style={{ marginBottom: '12px' }}>
                      <label>Finding Details & Officer Notes *</label>
                      <textarea
                        className="findings-textarea"
                        placeholder="Describe the investigative finding, verified facts, evidence links, or next action steps for officers..."
                        value={newContent}
                        onChange={e => setNewContent(e.target.value)}
                        rows={4}
                      />
                    </div>

                    {/* COMPACT SUPPORTING DOCUMENTS UPLOAD SECTION */}
                    <div className="supporting-docs-section">
                      <div className="supporting-docs-label">
                        <span>Supporting Documents (Optional)</span>
                        <small>PDF, JPG, PNG, DOCX, XLSX, CSV · Max 25MB each</small>
                      </div>

                      <div
                        className={`compact-dropzone ${dragOver ? 'dragging' : ''}`}
                        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOver(false);
                          handleFilesSelected(e.dataTransfer.files);
                        }}
                      >
                        <input
                          ref={fileInputRef}
                          type="file"
                          multiple
                          accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.csv"
                          style={{ display: 'none' }}
                          onChange={(e) => handleFilesSelected(e.target.files)}
                        />
                        <div className="compact-dropzone-inner">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="17 8 12 3 7 8"></polyline>
                            <line x1="12" y1="3" x2="12" y2="15"></line>
                          </svg>
                          <span className="compact-dropzone-text">
                            Drag & drop supporting files here, or
                          </span>
                          <button
                            type="button"
                            className="neu-btn ghost dropzone-browse-btn"
                            onClick={() => fileInputRef.current?.click()}
                          >
                            Choose Files
                          </button>
                        </div>
                      </div>

                      {/* Selected files list */}
                      {selectedFiles.length > 0 && (
                        <div className="selected-files-list">
                          {selectedFiles.map((file, idx) => (
                            <div key={`${file.name}-${idx}`} className="selected-file-row">
                              <div className="selected-file-info">
                                {getFileIcon(file.name)}
                                <span className="selected-file-name" title={file.name}>{file.name}</span>
                                <span className="selected-file-size">({formatAttachmentSize(file.size)})</span>
                              </div>
                              <div className="selected-file-actions">
                                <span className="selected-file-status">Ready to attach</span>
                                <button
                                  type="button"
                                  className="neu-btn danger icon-btn small-btn"
                                  onClick={() => handleRemoveSelectedFile(idx)}
                                  title="Remove file"
                                  aria-label="Remove file"
                                >
                                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                    <line x1="18" y1="6" x2="6" y2="18"></line>
                                    <line x1="6" y1="6" x2="18" y2="18"></line>
                                  </svg>
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {noteError && (
                      <p style={{ color: '#DC2626', fontSize: '12px', margin: '4px 0 10px' }}>
                        {noteError}
                      </p>
                    )}

                    <div className="findings-composer-actions">
                      <button
                        type="submit"
                        className="neu-btn primary"
                        disabled={submittingNote}
                        style={{ padding: '8px 22px' }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                          <line x1="12" y1="5" x2="12" y2="19"></line>
                          <line x1="5" y1="12" x2="19" y2="12"></line>
                        </svg>
                        {submittingNote ? 'Recording Finding…' : 'Record Finding Note'}
                      </button>
                    </div>
                  </form>
                </div>

                {/* RECORDED FINDINGS LIST */}
                <div>
                  <div className="card-header" style={{ marginBottom: '14px' }}>
                    <h3 style={{ fontSize: '15px', fontWeight: 700, margin: 0 }}>
                      Logged Officer Findings ({findings.length})
                    </h3>
                    <span className="workspace-muted" style={{ fontSize: '11px' }}>
                      Chronological case notes and investigative claims
                    </span>
                  </div>

                  {loadingFindings ? (
                    <div role="status" style={{ padding: '20px 0' }}>
                      <div className="skeleton sk-row" />
                      <div className="skeleton sk-row" style={{ marginTop: '10px' }} />
                    </div>
                  ) : findings.length === 0 ? (
                    <div className="workspace-quiet-state" style={{ textAlign: 'center', padding: '30px 16px', background: 'var(--palette-selected, #F8FAFC)', borderRadius: '12px' }}>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--palette-secondary, #94A3B8)', margin: '0 auto 10px', display: 'block' }} aria-hidden="true">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                      </svg>
                      <h4 style={{ margin: '0 0 6px', fontSize: '14px', fontWeight: 600 }}>No case findings recorded yet</h4>
                      <p style={{ margin: 0, fontSize: '12px', color: 'var(--palette-secondary, #64748B)' }}>
                        Use the form above to add the first officer finding or observation note for this docket.
                      </p>
                    </div>
                  ) : (
                    <div className="findings-list">
                      {findings.map(finding => (
                        <div key={finding.finding_id} className="finding-note-item">
                          <div className="finding-header">
                            <div className="finding-header-left">
                              <span className="badge-category">{finding.category}</span>
                              <span className={`badge-severity ${(finding.severity || 'medium').toLowerCase()}`}>
                                {finding.severity || 'MEDIUM'}
                              </span>
                              <h4>{finding.title}</h4>
                            </div>

                            {/* DELETE BUTTON: ONLY TRASH ICON SYMBOL, NO WORD DELETE */}
                            <button
                              className="neu-btn danger icon-btn"
                              onClick={() => handleDeleteFinding(finding.finding_id)}
                              title="Delete finding note"
                              aria-label="Delete finding note"
                            >
                              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                              </svg>
                            </button>
                          </div>

                          <div className="finding-meta">
                            <span>
                              Logged by: <strong>{finding.officer_name || 'Investigating Officer'}</strong>
                              {finding.officer_badge ? ` (${finding.officer_badge})` : ''}
                            </span>
                            <span>·</span>
                            <span>{displayDate(finding.created_at)}</span>
                          </div>

                          <p className="finding-body">{finding.content}</p>

                          {/* ATTACHED SUPPORTING DOCUMENTS LIST */}
                          {Boolean(finding.attachments && finding.attachments.length > 0) && (
                            <div className="finding-attachments-section">
                              <div className="finding-attachments-header">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
                                </svg>
                                <span>Attached Supporting Documents ({finding.attachments!.length})</span>
                              </div>
                              <div className="finding-attachments-grid">
                                {finding.attachments!.map(att => (
                                  <div key={att.attachment_id} className="finding-attachment-card">
                                    <div className="attachment-meta-row">
                                      {getFileIcon(att.filename)}
                                      <span className="attachment-filename" title={att.filename}>{att.filename}</span>
                                      <span className="attachment-filesize">({formatAttachmentSize(att.file_size)})</span>
                                    </div>
                                    <div className="attachment-btn-group">
                                      <button
                                        type="button"
                                        className="neu-btn ghost icon-btn small-btn"
                                        onClick={() => handlePreviewAttachment(finding.finding_id, att)}
                                        title="Preview document"
                                        aria-label="Preview document"
                                      >
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                          <circle cx="12" cy="12" r="3"></circle>
                                        </svg>
                                      </button>
                                      <button
                                        type="button"
                                        className="neu-btn ghost icon-btn small-btn"
                                        onClick={() => handleDownloadAttachment(finding.finding_id, att)}
                                        title="Download document"
                                        aria-label="Download document"
                                      >
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                          <polyline points="7 10 12 15 17 10"></polyline>
                                          <line x1="12" y1="15" x2="12" y2="3"></line>
                                        </svg>
                                      </button>
                                      <button
                                        type="button"
                                        className="neu-btn danger icon-btn small-btn"
                                        onClick={() => handleDeleteAttachment(finding.finding_id, att.attachment_id)}
                                        title="Delete attachment"
                                        aria-label="Delete attachment"
                                      >
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                          <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        </svg>
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* ATTACHMENT PREVIEW MODAL */}
      {previewDoc && (
        <div className="workspace-drawer-overlay" onClick={() => setPreviewDoc(null)} style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div
            className="card preview-modal-card"
            onClick={e => e.stopPropagation()}
            style={{ width: 'min(860px, 92vw)', maxHeight: '88vh', display: 'flex', flexDirection: 'column', padding: '18px 20px', borderRadius: '16px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '12px', borderBottom: '1px solid var(--palette-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                {getFileIcon(previewDoc.filename)}
                <strong style={{ fontSize: '14px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{previewDoc.filename}</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <a
                  href={previewDoc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="neu-btn ghost"
                  style={{ borderRadius: '9999px', fontSize: '11px', padding: '5px 14px' }}
                >
                  Open in New Window
                </a>
                <button
                  type="button"
                  className="neu-btn ghost icon-btn small-btn"
                  onClick={() => setPreviewDoc(null)}
                  title="Close preview"
                  aria-label="Close preview"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>
            </div>
            <div style={{ flex: 1, minHeight: '380px', maxHeight: '65vh', overflow: 'auto', marginTop: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--palette-selected, #F8FAFC)', borderRadius: '8px' }}>
              {previewDoc.filename.match(/\.(jpg|jpeg|png)$/i) ? (
                <img src={previewDoc.url} alt={previewDoc.filename} style={{ maxWidth: '100%', maxHeight: '60vh', objectFit: 'contain' }} />
              ) : (
                <iframe src={previewDoc.url} title={previewDoc.filename} style={{ width: '100%', height: '60vh', border: 'none' }} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
