import { CASE_CATEGORIES, CASE_STATUSES } from '../services/caseOptions';
import { SpreadsheetPreview } from './SpreadsheetPreview';
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import * as vis from 'vis-network/standalone';
import { API, esc, LABEL_COLOR, getNodeLevel, getDeterministicSeed, Case, GraphNode, GraphEdge, ThemeMode, OfficerSession, addOfficerUploadedCaseId } from '../services/api';
import { FileStore, LocalCaseStore, UploadedCaseFile } from '../services/fileStore';
import { caseCategory, caseUpdated, displayDate, LoadStatus } from '../services/workspace';
import { CaseWorkspace } from './CaseWorkspace';

export interface OverlappingCase {
  case_id: string;
  case_name?: string;
  shared_count?: number;
  sample_entities?: string[];
}

export interface CaseOverlap {
  has_overlap?: boolean;
  overlap_count?: number;
  overlapping_cases: OverlappingCase[];
}

export interface SuspectOrVictim {
  name: string;
  roles?: string | string[];
}

export interface EvidenceItem {
  icon?: string;
  name: string;
  type?: string;
  count?: number;
}

declare module '../services/api' {
  interface Case {
    case_type?: string;
    priority?: string;
    date?: string;
    category_of_crime?: string;
    lead_investigator?: string;
    created_at?: string;
    summary?: string;
    case_overlap?: CaseOverlap;
    primary_suspects?: SuspectOrVictim[];
    victims?: SuspectOrVictim[];
    evidences_collected?: EvidenceItem[];
  }
}

export interface CaseRegistryModuleProps {
  loadStatus: LoadStatus;
  hasLoaded: boolean;
  openEntityModal: (id: string) => void;
  officerSession: OfficerSession | null;
  cases: Case[];
  fetchCases: () => Promise<Case[]>;
  selectedCase: string | null;
  setSelectedCase: (id: string | null) => void;
  openAiDossier: (caseId: string, caseName: string) => void;
  promptDeleteCase: (caseId: string, caseName: string) => void;
  changeView: (view: string) => void;
  theme: string;
  addToast: (msg: string, type?: string) => void;
}

export function CaseRegistryModule({
  loadStatus, hasLoaded, openEntityModal,
  officerSession,
  cases,
  fetchCases,
  selectedCase,
  setSelectedCase,
  openAiDossier,
  promptDeleteCase,
  changeView,
  theme,
  addToast
}: CaseRegistryModuleProps) {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [caseDetail, setCaseDetail] = useState<Case | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  // Ingest New Case Modal State (No JSON - PDF, TXT, CSV only)
  const [isIngestModalOpen, setIsIngestModalOpen] = useState<boolean>(false);
  const [newCaseTitle, setNewCaseTitle] = useState<string>('');
  const [ingestFiles, setIngestFiles] = useState<File[]>([]);
  const [ingesting, setIngesting] = useState<boolean>(false);
  const [ingestProgress, setIngestProgress] = useState<{
    processed: number;
    total: number;
    currentFile: string;
    percent: number;
  } | null>(null);

  // Attach File to Existing Case Modal State (No JSON)
  const [isAttachModalOpen, setIsAttachModalOpen] = useState<boolean>(false);
  const [attachFiles, setAttachFiles] = useState<File[]>([]);
  const [attaching, setAttaching] = useState<boolean>(false);
  const [attachProgress, setAttachProgress] = useState<{
    processed: number;
    total: number;
    currentFile: string;
    percent: number;
  } | null>(null);

  // Document Content Viewer Modal State
  const [viewingFile, setViewingFile] = useState<UploadedCaseFile | null>(null);
  const [csvTableView, setCsvTableView] = useState<boolean>(true);
  const [fileSearchQuery, setFileSearchQuery] = useState<string>('');


  const filteredCases = useMemo(() => cases.filter(c => {
    const query = search.trim().toLowerCase();
    return (!statusFilter || c.status === statusFilter) && (!categoryFilter || caseCategory(c) === categoryFilter)
      && (!query || [c.case_name, c.case_id, c.fir_number, c.lead_investigator].some(value => String(value || '').toLowerCase().includes(query)));
  }), [cases, statusFilter, categoryFilter, search]);

  const loadCaseDetail = useCallback(async (id: string) => {
    setSelectedCase(id);
    setLoadingDetail(true);
    setCaseDetail(previous => previous?.case_id === id ? previous : null);
    try {
      const c = await API.get<Case>(`/api/cases/${encodeURIComponent(id)}`);
      setCaseDetail(c);
    } catch (e: any) {
      addToast(e.message, 'err');
      setCaseDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, [setSelectedCase, addToast]);

  useEffect(() => {
    if (selectedCase) {
      loadCaseDetail(selectedCase);
    } else {
      setCaseDetail(null);
    }
  }, [selectedCase, loadCaseDetail]);


  // Upload Files for New Case (PDF, TXT, CSV only)
  const handleNewCaseFileUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!officerSession) { addToast('Sign in before submitting evidence.', 'err'); return; }
    if (!newCaseTitle.trim()) { addToast('Case Title / Designation is required', 'info'); return; }
    if (!ingestFiles || ingestFiles.length === 0) { addToast('Please select at least one file to upload (.pdf, .txt, .csv, .xls, .xlsx)', 'info'); return; }

    const invalid = ingestFiles.filter(f => !['.pdf', '.txt', '.csv', '.xls', '.xlsx'].some(ext => f.name.toLowerCase().endsWith(ext)));
    if (invalid.length > 0) {
      addToast('Supported formats: PDF, TXT, CSV, XLS and XLSX.', 'err');
      return;
    }

    setIngesting(true);
    try {
      const filePayloads: Array<{ name: string; type: 'pdf' | 'csv' | 'txt' | 'xls' | 'xlsx'; size: string; content: string }> = [];
      for (const f of ingestFiles) {
        const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase().replace('.', '') as 'pdf' | 'csv' | 'txt' | 'xls' | 'xlsx';
        let content = '';
        try {
          content = /\.(pdf|xls|xlsx)$/i.test(f.name) ? await FileStore.readDataUrl(f) : await f.text();
        } catch {
          content = `[Binary Document ${f.name} - Case Evidence File]`;
        }
        filePayloads.push({
          name: f.name,
          type: ext,
          size: FileStore.formatBytes(f.size),
          content: content || `[Document content for ${f.name}]`
        });
      }

      const targetCaseId = newCaseTitle.trim();
      const total = ingestFiles.length;

      for (let i = 0; i < total; i++) {
        const f = ingestFiles[i];
        setIngestProgress({
          processed: i,
          total,
          currentFile: f.name,
          percent: Math.round((i / total) * 100)
        });

        const formData = new FormData();
        formData.append('files', f);
        if (officerSession) {
          formData.append('uploaded_by', officerSession.badgeNumber);
          formData.append('officer_name', officerSession.officerName);
        }

        let url = `/api/v1/ingest?case_id=${encodeURIComponent(targetCaseId)}`;
        if (officerSession) {
          url += `&uploaded_by=${encodeURIComponent(officerSession.badgeNumber)}&officer_name=${encodeURIComponent(officerSession.officerName)}`;
        }

        await API.send<{ case_id?: string }>(url, {
          method: 'POST',
          body: formData,
          form: true
        });

        setIngestProgress({
          processed: i + 1,
          total,
          currentFile: f.name,
          percent: Math.round(((i + 1) / total) * 100)
        });
      }

      const primaryFileName = ingestFiles[0]?.name || 'Evidence File';
      const caseName = newCaseTitle.trim() || `Investigation: ${primaryFileName.replace(/\.[^/.]+$/, '')}`;
      const newCase: Case = {
        case_id: targetCaseId,
        case_name: caseName,
        status: 'UNDER_INVESTIGATION',
        crime_category: 'EVIDENCE_INGESTION',
        lead_investigator: officerSession?.officerName || 'Lead Detective',
        uploaded_by: officerSession?.badgeNumber || 'Not recorded',
        created_date: new Date().toISOString().substring(0, 10),
        created_at: new Date().toISOString(),
        summary: `Evidence docket containing ${ingestFiles.length} document(s): ${ingestFiles.map(f => f.name).join(', ')}.`,
        total_entities: undefined
      };

      // Persist to LocalCaseStore
      LocalCaseStore.saveCase(newCase);

      // Associate case with logged in officer badge
      if (officerSession) {
        addOfficerUploadedCaseId(officerSession.badgeNumber, targetCaseId);
      }

      filePayloads.forEach(fp => {
        FileStore.saveFile({
          case_id: targetCaseId,
          file_name: fp.name,
          file_type: fp.type,
          file_size: fp.size,
          uploaded_at: new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC',
          content: fp.content
        });
      });

      addToast(`Case '${targetCaseId}' created with ${filePayloads.length} evidence file(s)!`, 'ok');
      await fetchCases();
      setIsIngestModalOpen(false);
      setNewCaseTitle('');
      setIngestFiles([]);
      setSelectedCase(targetCaseId);
      loadCaseDetail(targetCaseId);
    } catch (e) {
      addToast(`Upload failed: ${(e as Error).message}`, 'err');
    } finally {
      setIngesting(false);
      setIngestProgress(null);
    }
  };

  // Attach File to Existing Case (PDF, TXT, CSV only)
  const handleAttachFileUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedCase) return;
    if (!officerSession) { addToast('Sign in before submitting evidence.', 'err'); return; }
    if (!attachFiles || attachFiles.length === 0) { addToast('Please select a file to upload (.pdf, .txt, .csv, .xls, .xlsx)', 'info'); return; }

    const invalid = attachFiles.filter(f => !['.pdf', '.txt', '.csv', '.xls', '.xlsx'].some(ext => f.name.toLowerCase().endsWith(ext)));
    if (invalid.length > 0) {
      addToast('Supported formats: PDF, TXT, CSV, XLS and XLSX.', 'err');
      return;
    }

    setAttaching(true);
    try {
      const filePayloads: Array<{ name: string; type: 'pdf' | 'csv' | 'txt' | 'xls' | 'xlsx'; size: string; content: string }> = [];
      for (const f of attachFiles) {
        const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase().replace('.', '') as 'pdf' | 'csv' | 'txt' | 'xls' | 'xlsx';
        let content = '';
        try {
          content = /\.(pdf|xls|xlsx)$/i.test(f.name) ? await FileStore.readDataUrl(f) : await f.text();
        } catch {
          content = `[Binary Document ${f.name} - Case Evidence File]`;
        }
        filePayloads.push({
          name: f.name,
          type: ext,
          size: FileStore.formatBytes(f.size),
          content: content || `[Document content for ${f.name}]`
        });
      }

      const total = attachFiles.length;
      for (let i = 0; i < total; i++) {
        const f = attachFiles[i];
        setAttachProgress({
          processed: i,
          total,
          currentFile: f.name,
          percent: Math.round((i / total) * 100)
        });

        const formData = new FormData();
        formData.append('files', f);
        if (officerSession) {
          formData.append('uploaded_by', officerSession.badgeNumber);
          formData.append('officer_name', officerSession.officerName);
        }

        let url = `/api/v1/ingest?case_id=${encodeURIComponent(selectedCase)}`;
        if (officerSession) {
          url += `&uploaded_by=${encodeURIComponent(officerSession.badgeNumber)}&officer_name=${encodeURIComponent(officerSession.officerName)}`;
        }

        await API.send<{ case_id?: string }>(url, {
          method: 'POST',
          body: formData,
          form: true
        });

        setAttachProgress({
          processed: i + 1,
          total,
          currentFile: f.name,
          percent: Math.round(((i + 1) / total) * 100)
        });
      }

      filePayloads.forEach(fp => {
        FileStore.saveFile({
          case_id: selectedCase,
          file_name: fp.name,
          file_type: fp.type,
          file_size: fp.size,
          uploaded_at: new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC',
          content: fp.content
        });
      });

      addToast(`Attached ${filePayloads.length} file(s) to Case '${selectedCase}'!`, 'ok');
      await fetchCases();
      await loadCaseDetail(selectedCase);
      setIsAttachModalOpen(false);
      setAttachFiles([]);
    } catch (e) {
      addToast(`Attachment failed: ${(e as Error).message}`, 'err');
    } finally {
      setAttaching(false);
      setAttachProgress(null);
    }
  };

  // Only show files actually uploaded locally; never synthesize evidence contents.
  const caseFiles: UploadedCaseFile[] = useMemo(() => {
    return caseDetail ? FileStore.getByCaseId(caseDetail.case_id) : [];
  }, [caseDetail]);

  // Parse CSV content for structured viewer
  const parsedCsv = useMemo(() => {
    if (!viewingFile || viewingFile.file_type !== 'csv') return null;
    const lines = viewingFile.content.trim().split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length === 0) return { headers: [], rows: [] };
    const headers = lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, ''));
    const rows = lines.slice(1).map(l => l.split(',').map(c => c.trim().replace(/^["']|["']$/g, '')));
    return { headers, rows };
  }, [viewingFile]);

  // Filter lines for text view
  const filteredTextLines = useMemo(() => {
    if (!viewingFile) return [];
    const lines = viewingFile.content.split(/\r?\n/);
    if (!fileSearchQuery.trim()) return lines;
    return lines.filter(l => l.toLowerCase().includes(fileSearchQuery.toLowerCase()));
  }, [viewingFile, fileSearchQuery]);

  const copyFileContent = () => {
    if (!viewingFile) return;
    navigator.clipboard.writeText(viewingFile.content);
    addToast('Document content copied to clipboard', 'ok');
  };

  const downloadFile = () => {
    if (!viewingFile) return;
    const blob = new Blob([viewingFile.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = viewingFile.file_name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    addToast(`Downloaded ${viewingFile.file_name}`, 'ok');
  };

  return (
    <div className="fade-in">
      {!selectedCase && <section className="card registry-panel">
        <div className="card-header"><div><h2 className="card-title">Case registry</h2><p className="workspace-muted">Records visible to your officer account.</p></div></div>
        <div className="registry-toolbar">
          <label>Find a case<input className="control" value={search} onChange={e => setSearch(e.target.value)} placeholder="Name, ID or FIR reference" type="search"/></label>
          <label>Status<select className="control" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="">All statuses</option>{Array.from(new Set([...CASE_STATUSES, ...cases.map(c => c.status).filter(Boolean)])).map(status => <option key={status} value={status}>{status?.replace(/_/g,' ')}</option>)}</select></label>
          <label>Category<select className="control" value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}><option value="">All categories</option>{Array.from(new Set([...CASE_CATEGORIES, ...cases.map(caseCategory)])).map(category => <option key={category}>{category}</option>)}</select></label>
          <button className="neu-btn ghost" onClick={fetchCases} disabled={loadStatus === 'loading'}>{loadStatus === 'loading' ? 'Loading…' : 'Refresh'}</button>
        </div>
        {hasLoaded && loadStatus === 'error' && <p className="workspace-scope-note">Previously loaded records may be outdated.</p>}
        <div className="tbl-wrap"><table><thead><tr><th>Case / FIR reference</th><th>Category</th><th>Assigned officer</th><th>Status</th><th>Last updated</th><th>Actions</th></tr></thead><tbody>
        {!hasLoaded ? <tr><td colSpan={6}>{loadStatus === 'error' ? <p className="workspace-unavailable">Case records unavailable.</p> : <div role="status" aria-label="Loading case registry"><div className="skeleton sk-row"/><div className="skeleton sk-row"/></div>}</td></tr> : filteredCases.length ? filteredCases.map(c => <tr key={c.case_id}><td><strong>{c.case_name || c.case_id}</strong><small className="registry-reference">{c.fir_number || c.case_id}</small></td><td>{caseCategory(c)}</td><td>{String(c.lead_investigator || c.assigned_officer || 'Not recorded')}</td><td><span className="tag plain">{c.status?.replace(/_/g,' ') || 'Not recorded'}</span></td><td>{displayDate(caseUpdated(c))}</td><td><button className="neu-btn ghost" onClick={() => setSelectedCase(c.case_id)} aria-label={`Open ${c.case_name || c.case_id}`}>Open →</button><button className="neu-btn ghost danger registry-delete" onClick={() => promptDeleteCase(c.case_id, c.case_name || c.case_id)} aria-label={`Delete ${c.case_name || c.case_id}`} title="Delete case"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></button></td></tr>) : <tr><td colSpan={6}><div className="investigation-empty"><h3>{cases.length ? 'No matching cases' : 'Start your first investigation'}</h3><p>{cases.length ? 'Adjust your search or filters.' : 'Add case evidence to begin analysis.'}</p></div></td></tr>}
        </tbody></table></div>
      </section>}
      {selectedCase && <CaseWorkspace cases={cases} selectedCase={selectedCase} setSelectedCase={setSelectedCase} record={caseDetail} loadingDetail={loadingDetail} retry={() => loadCaseDetail(selectedCase)} files={caseFiles} viewFile={file => { setViewingFile(file); setFileSearchQuery(''); }} attach={() => setIsAttachModalOpen(true)} dossier={() => openAiDossier(selectedCase, caseDetail?.case_name || selectedCase)} deleteCase={() => promptDeleteCase(selectedCase, caseDetail?.case_name || selectedCase)} theme={theme} addToast={addToast} openEntityModal={openEntityModal} officerSession={officerSession}/>}


      {/* MODAL: DOCUMENT CONTENT VIEWER */}
      {viewingFile && (
        <div
          className="modal-overlay open"
          onClick={(e) => { if (e.target === e.currentTarget) setViewingFile(null); }}
        >
          <div className="modal modal-large" style={{ background: '#FFFFFF', boxShadow: '0 20px 40px rgba(0,0,0, 0.08)' }}>
            <div className="file-viewer-header">
              <div>
                <div className="flex items-center gap-2">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent)' }}>
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  <h3 className="font-bold text-base m-0" style={{ color: 'var(--text)' }}>
                    {viewingFile.file_name}
                  </h3>
                  <span className="tag open text-xs uppercase">{viewingFile.file_type}</span>
                </div>
                <div className="file-viewer-meta mt-1">
                  <span>Case ID: <strong className="mono">{viewingFile.case_id}</strong></span>
                  <span>·</span>
                  <span>Size: {viewingFile.file_size}</span>
                  <span>·</span>
                  <span>Timestamp: {viewingFile.uploaded_at}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {false && (
                  <button
                    className="neu-btn ghost text-xs"
                    onClick={() => setCsvTableView(prev => !prev)}
                  >
                    {csvTableView ? 'Switch to Raw Text' : 'Switch to Table Grid'}
                  </button>
                )}
                <button className="neu-btn ghost text-xs" onClick={copyFileContent} title="Copy Content">
                  Copy
                </button>
                <button className="neu-btn ghost text-xs" onClick={downloadFile} title="Download File">
                  Download
                </button>
                <button
                  className="neu-btn ghost text-xs"
                  onClick={() => setViewingFile(null)}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Filter / Search Bar inside document */}
            <div className="my-3 flex items-center gap-2">
              <input
                className="control text-xs flex-1"
                style={{ background: '#FFFFFF' }}
                placeholder="Search keywords, phone numbers, transaction IDs inside document…"
                value={fileSearchQuery}
                onChange={e => setFileSearchQuery(e.target.value)}
              />
              {fileSearchQuery && (
                <button
                  className="neu-btn ghost text-xs"
                  onClick={() => setFileSearchQuery('')}
                >
                  Clear Filter
                </button>
              )}
            </div>

            {/* Content Display: CSV Table View vs Text Reader View */}
            {['csv', 'xls', 'xlsx'].includes(viewingFile.file_type) ? <SpreadsheetPreview content={viewingFile.content} filename={viewingFile.file_name} search={fileSearchQuery}/> : viewingFile.file_type === 'pdf' && viewingFile.content.startsWith('data:application/pdf') ? <iframe title={viewingFile.file_name} src={viewingFile.content} style={{width:'100%',height:'60vh',border:0}} /> : viewingFile.file_type === 'csv' && csvTableView && parsedCsv ? (
              <div className="tbl-wrap" style={{ maxHeight: '480px', background: '#FFFFFF' }}>
                <table className="file-table-grid">
                  <thead>
                    <tr>
                      <th style={{ width: '40px' }}>#</th>
                      {parsedCsv.headers.map((h, hIdx) => (
                        <th key={hIdx}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsedCsv.rows
                      .filter(r => !fileSearchQuery || r.some(c => c.toLowerCase().includes(fileSearchQuery.toLowerCase())))
                      .map((row, rIdx) => (
                        <tr key={rIdx}>
                          <td className="mono" style={{ color: 'var(--text-faint)', fontSize:'11px' }}>{rIdx + 1}</td>
                          {row.map((cell, cIdx) => (
                            <td key={cIdx}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="file-content-box">
                {filteredTextLines.map((line, idx) => (
                  <div key={idx} className="flex gap-3 py-0.5" style={{ alignItems: 'baseline' }}>
                    <span className="mono select-none" style={{ color: '#303A36', width: '32px', textAlign: 'right', flexShrink: 0 }}>
                      {idx + 1}
                    </span>
                    <span className="flex-1" style={{ color: '#171C1B' }}>{line || ' '}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-between items-center mt-4 pt-3 border-t text-xs" style={{ borderColor: 'var(--border)', color: 'var(--text-faint)' }}>
              <span>Local file preview · Original content retained in this browser</span>
              <button className="neu-btn ghost text-xs" onClick={() => setViewingFile(null)}>
                Close Viewer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 1: INGEST A NEW CASE (PDF, TXT, CSV only - No JSON) */}
      {isIngestModalOpen && (
        <div
          className="modal-overlay open"
          onClick={(e) => { if (e.target === e.currentTarget) setIsIngestModalOpen(false); }}
        >
          <div className="modal">
            <div className="card-header border-b pb-3 mb-4">
              <div className="card-title text-base font-bold">
                <span>➕</span> Ingest a New Case
              </div>
              <button className="neu-btn ghost text-xs" onClick={() => setIsIngestModalOpen(false)}>✕</button>
            </div>

            <form onSubmit={handleNewCaseFileUpload} className="flex flex-col gap-4">
              <div className="field">
                <label>Case Docket Designation / Title (Required)</label>
                <input
                  required
                  className="control text-sm"
                  placeholder="e.g. Operation Cyber Shield / FIR-2026-902"
                  value={newCaseTitle}
                  onChange={(e) => setNewCaseTitle(e.target.value)}
                />
              </div>

              <div
                style={{
                  padding:'19px 13px',
                  border: '2px dashed var(--border-strong)',
                  borderRadius:'8px',
                  textAlign: 'center',
                  background: 'var(--bg1)'
                }}
              >
                <div className="font-bold text-sm mb-1" style={{ color: 'var(--text)' }}>
                  Upload Case Documents (.pdf, .txt, .csv, .xls, .xlsx)
                </div>
                <div className="text-xs mb-3" style={{ color: 'var(--text-faint)' }}>
                  Upload FIR complaint text, telecom CDR calls, or bank transaction statements.
                </div>
                <input
                  type="file"
                  accept=".pdf,.txt,.csv,.xls,.xlsx"
                  multiple
                  onChange={(e) => setIngestFiles(Array.from(e.target.files || []))}
                />
                {ingestFiles.length > 0 && (
                  <div className="mt-2 font-bold text-xs" style={{ color: 'var(--accent)' }}>
                    Selected {ingestFiles.length} file(s): {ingestFiles.map(f => f.name).join(', ')}
                  </div>
                )}

                {ingestProgress && (
                  <div
                    style={{
                      padding: '10px 12px',
                      borderRadius: 6,
                      border: '1px solid var(--border-subtle, #E2E8F0)',
                      background: 'var(--bg2, #F8FAFC)',
                      fontSize: 11,
                      marginTop: 10,
                      textAlign: 'left'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                        Ingesting: {ingestProgress.processed} / {ingestProgress.total} Files Processed
                      </span>
                      <span style={{ fontWeight: 700, fontFamily: 'monospace', color: 'var(--accent, #2563EB)' }}>
                        {ingestProgress.percent}%
                      </span>
                    </div>
                    <div style={{ width: '100%', height: 6, backgroundColor: 'var(--border-strong, #CBD5E1)', borderRadius: 9999, overflow: 'hidden', marginBottom: 4 }}>
                      <div
                        style={{
                          width: `${ingestProgress.percent}%`,
                          height: '100%',
                          backgroundColor: 'var(--accent, #2563EB)',
                          borderRadius: 9999,
                          transition: 'width 0.25s ease'
                        }}
                      />
                    </div>
                    <div style={{ color: 'var(--text-faint)', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ingestProgress.processed < ingestProgress.total ? (
                        <>Current: <strong style={{ color: 'var(--text)' }}>{ingestProgress.currentFile}</strong></>
                      ) : (
                        <span style={{ color: '#10B981', fontWeight: 600 }}>✓ All {ingestProgress.total} files ingested and linked!</span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 mt-2">
                <button type="button" className="neu-btn ghost" onClick={() => setIsIngestModalOpen(false)}>Cancel</button>
                <button type="submit" className="neu-btn primary font-semibold" disabled={ingesting || ingestFiles.length === 0 || !newCaseTitle.trim()}>
                  {ingesting ? (
                    ingestProgress
                      ? `Processing ${Math.min(ingestProgress.processed + 1, ingestProgress.total)} of ${ingestProgress.total} (${ingestProgress.percent}%)…`
                      : 'Uploading & Extracting…'
                  ) : 'Ingest New Case'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: UPLOAD FILE DIRECTLY TO EXISTING CASE (PDF, TXT, CSV only) */}
      {isAttachModalOpen && selectedCase && (
        <div
          className="modal-overlay open"
          onClick={(e) => { if (e.target === e.currentTarget) setIsAttachModalOpen(false); }}
        >
          <div className="modal">
            <div className="card-header border-b pb-3 mb-4">
              <div>
                <div className="card-title text-base font-bold">
                  <span>📤</span> Attach Evidence to Case
                </div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--text-faint)' }}>
                  Target Docket: <strong className="mono" style={{ color: 'var(--accent)' }}>{selectedCase}</strong>
                </div>
              </div>
              <button className="neu-btn ghost text-xs" onClick={() => setIsAttachModalOpen(false)}>✕</button>
            </div>

            <form onSubmit={handleAttachFileUpload} className="flex flex-col gap-4">
              <div
                style={{
                  padding:'19px 13px',
                  border: '2px dashed var(--border-strong)',
                  borderRadius:'8px',
                  textAlign: 'center',
                  background: 'var(--bg1)'
                }}
              >
                <div className="font-bold text-sm mb-1" style={{ color: 'var(--text)' }}>
                  Upload Document or Data File (.pdf, .txt, .csv, .xls, .xlsx)
                </div>
                <div className="text-xs mb-3" style={{ color: 'var(--text-faint)' }}>
                  Entities will be extracted and linked directly into Case <span className="mono">{selectedCase}</span>.
                </div>
                <input
                  type="file"
                  accept=".pdf,.txt,.csv,.xls,.xlsx"
                  multiple
                  onChange={(e) => setAttachFiles(Array.from(e.target.files || []))}
                />
                {attachFiles.length > 0 && (
                  <div className="mt-2 font-bold text-xs" style={{ color: 'var(--accent)' }}>
                    Selected {attachFiles.length} file(s): {attachFiles.map(f => f.name).join(', ')}
                  </div>
                )}

                {attachProgress && (
                  <div
                    style={{
                      padding: '10px 12px',
                      borderRadius: 6,
                      border: '1px solid var(--border-subtle, #E2E8F0)',
                      background: 'var(--bg2, #F8FAFC)',
                      fontSize: 11,
                      marginTop: 10,
                      textAlign: 'left'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                        Attaching: {attachProgress.processed} / {attachProgress.total} Files Processed
                      </span>
                      <span style={{ fontWeight: 700, fontFamily: 'monospace', color: 'var(--accent, #2563EB)' }}>
                        {attachProgress.percent}%
                      </span>
                    </div>
                    <div style={{ width: '100%', height: 6, backgroundColor: 'var(--border-strong, #CBD5E1)', borderRadius: 9999, overflow: 'hidden', marginBottom: 4 }}>
                      <div
                        style={{
                          width: `${attachProgress.percent}%`,
                          height: '100%',
                          backgroundColor: 'var(--accent, #2563EB)',
                          borderRadius: 9999,
                          transition: 'width 0.25s ease'
                        }}
                      />
                    </div>
                    <div style={{ color: 'var(--text-faint)', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {attachProgress.processed < attachProgress.total ? (
                        <>Current: <strong style={{ color: 'var(--text)' }}>{attachProgress.currentFile}</strong></>
                      ) : (
                        <span style={{ color: '#10B981', fontWeight: 600 }}>✓ All {attachProgress.total} files attached!</span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 mt-2">
                <button type="button" className="neu-btn ghost" onClick={() => setIsAttachModalOpen(false)}>Cancel</button>
                <button type="submit" className="neu-btn primary font-semibold" disabled={attaching || attachFiles.length === 0}>
                  {attaching ? (
                    attachProgress
                      ? `Processing ${Math.min(attachProgress.processed + 1, attachProgress.total)} of ${attachProgress.total} (${attachProgress.percent}%)…`
                      : 'Uploading & Extracting…'
                  ) : 'Attach File to Case'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}



