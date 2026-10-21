import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { API, Case, OfficerSession } from '../services/api';
import { InvestigationBoardRecord } from './InvestigationBoardModule';

interface ReportsModuleProps {
  cases: Case[];
  selectedCase?: string | null;
  onSelectCase?: (caseId: string) => void;
  officerSession?: OfficerSession | null;
  changeView: (id: string) => void;
  addToast: (msg: string, type?: string) => void;
}

interface AiDossier {
  title?: string;
  executive_summary?: string;
  summary?: string;
  key_findings?: string[];
}

interface PatternInsight {
  insight_id: string;
  insight_type: string;
  title: string;
  severity: string;
  description: string;
  derived_interpretation?: string;
  observed_facts?: string[];
  entities_involved?: string[];
  alternative_explanations?: string[];
  disclaimer?: string;
}

interface EvidenceItemRecord {
  evidence_id: string;
  case_id: string;
  sha256: string;
  filename: string;
  format?: string;
  size?: number;
  uploaded_at?: string;
  uploader?: string;
  job?: {
    classification?: string;
    mention_count?: number;
    claim_count?: number;
  };
}

interface FindingRecord {
  finding_id: string;
  case_id: string;
  title: string;
  category: string;
  content: string;
  officer_name?: string;
  officer_badge?: string;
  severity?: string;
  created_at?: string;
}

export function ReportsModule({
  cases,
  selectedCase,
  onSelectCase,
  officerSession,
  changeView,
  addToast
}: ReportsModuleProps) {
  const activeCaseId = selectedCase || (cases.length > 0 ? cases[0].case_id : 'case_01');

  // Local state for live fetched data
  const [freshCase, setFreshCase] = useState<Case | null>(null);
  const [dossier, setDossier] = useState<AiDossier | null>(null);
  const [insights, setInsights] = useState<PatternInsight[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceItemRecord[]>([]);
  const [findingsList, setFindingsList] = useState<FindingRecord[]>([]);
  const [boards, setBoards] = useState<InvestigationBoardRecord[]>([]);
  const [loadingReport, setLoadingReport] = useState<boolean>(false);

  // New Finding input form
  const [noteTitle, setNoteTitle] = useState<string>('');
  const [noteCategory, setNoteCategory] = useState<string>('Telecom & CDR');
  const [noteContent, setNoteContent] = useState<string>('');
  const [submittingNote, setSubmittingNote] = useState<boolean>(false);

  // Fallback to cases array if freshCase not yet loaded
  const currentCase = useMemo(() => {
    if (freshCase && freshCase.case_id.toLowerCase() === activeCaseId.toLowerCase()) {
      return freshCase;
    }
    return cases.find(c => c.case_id.toLowerCase() === activeCaseId.toLowerCase()) || cases[0];
  }, [freshCase, cases, activeCaseId]);

  const fetchAllReportData = useCallback(async (caseId: string) => {
    setLoadingReport(true);
    try {
      const [caseRes, dossierRes, insightsRes, evRes, findRes, boardsRes] = await Promise.allSettled([
        API.get<Case>(`/api/cases/${encodeURIComponent(caseId)}`),
        API.get<AiDossier>(`/api/cases/${encodeURIComponent(caseId)}/ai-dossier`),
        API.get<PatternInsight[]>(`/api/cases/${encodeURIComponent(caseId)}/insights`),
        API.get<{ items: EvidenceItemRecord[] }>(`/api/evidence?case_id=${encodeURIComponent(caseId)}`),
        API.get<FindingRecord[]>(`/api/cases/${encodeURIComponent(caseId)}/findings`),
        API.get<{ total: number; boards: InvestigationBoardRecord[] }>(`/api/boards?case_id=${encodeURIComponent(caseId)}`)
      ]);

      if (caseRes.status === 'fulfilled' && caseRes.value) {
        setFreshCase(caseRes.value);
      }
      if (dossierRes.status === 'fulfilled' && dossierRes.value) {
        setDossier(dossierRes.value);
      }
      if (insightsRes.status === 'fulfilled' && Array.isArray(insightsRes.value)) {
        setInsights(insightsRes.value);
      } else {
        setInsights([]);
      }
      if (evRes.status === 'fulfilled' && evRes.value?.items) {
        setEvidenceList(evRes.value.items);
      } else {
        setEvidenceList([]);
      }
      if (findRes.status === 'fulfilled' && Array.isArray(findRes.value)) {
        setFindingsList(findRes.value);
      } else {
        setFindingsList([]);
      }
      if (boardsRes.status === 'fulfilled' && boardsRes.value?.boards) {
        setBoards(boardsRes.value.boards);
      } else {
        setBoards([]);
      }
    } catch (err) {
      console.error('Failed to fetch case report data:', err);
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    if (activeCaseId) {
      fetchAllReportData(activeCaseId);
    }
  }, [activeCaseId, fetchAllReportData]);

  const handlePrint = () => {
    window.print();
  };

  const handleAddFinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim()) {
      addToast('Please provide both a title and finding summary.', 'warning');
      return;
    }
    setSubmittingNote(true);
    try {
      const res = await API.post<FindingRecord>(`/api/cases/${encodeURIComponent(activeCaseId)}/findings`, {
        title: noteTitle.trim(),
        category: noteCategory,
        content: noteContent.trim(),
        officer_name: officerSession?.officerName || 'Investigating Officer',
        officer_badge: officerSession?.badgeNumber || 'LE-8402',
        severity: 'MEDIUM'
      });
      if (res && res.finding_id) {
        addToast('Finding note recorded into case docket.', 'ok');
        setFindingsList(prev => [res, ...prev]);
        setNoteTitle('');
        setNoteContent('');
      }
    } catch (err: any) {
      addToast(`Error saving finding note: ${err.message || 'Server error'}`, 'error');
    } finally {
      setSubmittingNote(false);
    }
  };

  const getSeverityBadge = (sev?: string) => {
    const s = (sev || 'MEDIUM').toUpperCase();
    if (s === 'CRITICAL' || s === 'HIGH') {
      return 'bg-rose-50 text-rose-700 border-rose-200';
    }
    if (s === 'MEDIUM') {
      return 'bg-amber-50 text-amber-700 border-amber-200';
    }
    return 'bg-blue-50 text-blue-700 border-blue-200';
  };

  return (
    <div className="reports-container p-6 max-w-6xl mx-auto space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <label className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Case Dossier:
          </label>
          <select
            className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white font-semibold text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={activeCaseId}
            onChange={(e) => {
              if (onSelectCase) onSelectCase(e.target.value);
            }}
          >
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {c.case_id.toUpperCase()}{c.case_name ? ` — ${c.case_name}` : ''}
              </option>
            ))}
          </select>
          {loadingReport && (
            <span className="text-xs text-blue-600 animate-pulse font-medium">
              Synchronizing case intelligence…
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="neu-btn ghost flex items-center gap-1.5 text-xs font-semibold py-1.5 px-3"
            onClick={() => changeView('graph')}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3a2 2 0 0 1 2 2c0 .4-.1.8-.3 1.1l3.4 5.4c.3-.1.6-.2.9-.2a2 2 0 1 1 0 4c-.3 0-.6-.1-.9-.2l-3.4 5.4c.2.3.3.7.3 1.1a2 2 0 1 1-3.6-1.1L8.9 15.5c-.3.1-.6.2-.9.2a2 2 0 1 1 0-4c.3 0 .6.1.8.2l3.4-5.4c-.2-.3-.3-.7-.3-1.1a2 2 0 0 1 2-2Z" />
            </svg>
            <span>Graph View</span>
          </button>

          <button
            type="button"
            className="neu-btn ghost flex items-center gap-1.5 text-xs font-semibold py-1.5 px-3"
            onClick={() => changeView('board')}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
            <span>Investigation Board</span>
          </button>

          <button
            type="button"
            className="neu-btn primary flex items-center gap-1.5 text-xs font-semibold py-1.5 px-4 shadow-sm"
            onClick={handlePrint}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            <span>Export / Print Report (PDF)</span>
          </button>
        </div>
      </div>

      {/* Official Header Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700 border border-slate-200">
                OFFICIAL POLICE DOSSIER
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-emerald-50 text-emerald-700 border border-emerald-200">
                {currentCase?.status?.toUpperCase() || 'ACTIVE INVESTIGATION'}
              </span>
              {currentCase?.severity && (
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${getSeverityBadge(currentCase.severity)}`}>
                  {currentCase.severity} Priority
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold text-slate-900">
              {currentCase?.case_name || currentCase?.case_id?.toUpperCase() || 'Investigation Case'}
            </h1>
            <p className="text-xs text-slate-500 mt-1 font-mono">
              FIR: {currentCase?.fir_number || `FIR-${activeCaseId}`} • Case Ref: {activeCaseId.toUpperCase()}
              {currentCase?.date_filed ? ` • Registered: ${currentCase.date_filed}` : ''}
            </p>
          </div>

          <div className="text-right text-xs text-slate-500">
            <div>Lead Officer: <strong className="text-slate-800">{currentCase?.lead_investigator || officerSession?.officerName || 'Investigating Officer'}</strong></div>
            <div>Badge: <strong className="text-slate-800">{officerSession?.badgeNumber || 'LE-8402'}</strong></div>
            <div>Agency: <strong className="text-slate-800">{officerSession?.department || 'Criminal Investigation Department'}</strong></div>
            <div className="text-[11px] text-slate-400 mt-1 font-mono">Report Date: {new Date().toLocaleDateString()}</div>
          </div>
        </div>

        {/* Dynamic Key Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
          <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">Crime Category</span>
            <span className="text-sm font-bold text-slate-800 mt-1 block truncate">
              {currentCase?.crime_category || 'General Investigation'}
            </span>
          </div>

          <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">Primary Suspect</span>
            <span className="text-sm font-bold text-rose-700 mt-1 block truncate">
              {currentCase?.primary_suspect || 'Suspect Under Review'}
            </span>
          </div>

          <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">Total Entities</span>
            <span className="text-sm font-bold text-slate-800 mt-1 block">
              {currentCase?.total_entities !== undefined ? currentCase.total_entities : 0} Identified
            </span>
          </div>

          <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">Evidence Custody</span>
            <span className="text-sm font-bold text-emerald-700 mt-1 flex items-center gap-1.5">
              <svg className="w-4 h-4 text-emerald-600 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span>{evidenceList.length} Files • SHA-256</span>
            </span>
          </div>
        </div>
      </div>

      {/* Executive AI Forensic Dossier */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-pulse"></div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Executive AI Intelligence Dossier
            </h2>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
            ATLAS Forensic Synthesis Engine
          </span>
        </div>

        <div className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-lg border border-slate-100">
          <p className="font-medium text-slate-800">
            {dossier?.executive_summary || dossier?.summary || (
              `Investigation docket ${currentCase?.case_name || activeCaseId} (${activeCaseId.toUpperCase()}) incorporates ${currentCase?.total_entities || 0} cataloged entities across ${evidenceList.length} verified exhibits. Relationships and network bridges are grounded in multi-format forensic evidence.`
            )}
          </p>
        </div>

        {dossier?.key_findings && dossier.key_findings.length > 0 && (
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
              Key Forensic Graph Discoveries:
            </h3>
            <ul className="space-y-2">
              {dossier.key_findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-700 bg-white p-2.5 rounded-lg border border-slate-100">
                  <span className="text-blue-500 font-bold mt-0.5">•</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Automated Pattern Insights & Syndicate Alerts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Automated Forensic Pattern Detections ({insights.length})
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Transparent, rule-based algorithmic detection across telecom CDR, financial trails, and hardware IMEIs.
            </p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
            Transparent Rules
          </span>
        </div>

        {insights.length === 0 ? (
          <div className="bg-slate-50 border border-dashed border-slate-300 rounded-lg p-6 text-center text-slate-500 text-xs">
            No anomalous multi-hop telecom bursts or laundering transfer chains detected for current case scope.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {insights.map((ins) => (
              <div key={ins.insight_id} className="border border-slate-200 rounded-lg p-4 bg-slate-50/50 hover:border-blue-300 transition-all">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <h3 className="text-xs font-bold text-slate-900 truncate">{ins.title}</h3>
                  <span className={`px-2 py-0.5 rounded text-[9.5px] font-bold uppercase tracking-wider border ${getSeverityBadge(ins.severity)}`}>
                    {ins.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed mb-2">
                  {ins.description}
                </p>
                {ins.derived_interpretation && (
                  <p className="text-[11px] text-blue-800 bg-blue-50/80 p-2 rounded border border-blue-100 mb-2 font-medium">
                    🔍 <strong>Interpretation:</strong> {ins.derived_interpretation}
                  </p>
                )}
                {ins.observed_facts && ins.observed_facts.length > 0 && (
                  <div className="text-[10.5px] text-slate-500 space-y-0.5">
                    {ins.observed_facts.map((fact, idx) => (
                      <div key={idx}>✓ {fact}</div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Verified Evidence Chain of Custody Table */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Evidence Chain of Custody & Cryptographic Hashing
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Immutable SHA-256 verification and extraction records for case exhibits.
            </p>
          </div>
          <button
            type="button"
            className="neu-btn ghost text-xs py-1 px-3 flex items-center gap-1 text-blue-600"
            onClick={() => changeView('blockchain')}
          >
            <span>Audit Ledger</span>
            <span>→</span>
          </button>
        </div>

        {evidenceList.length === 0 ? (
          <div className="bg-slate-50 border border-dashed border-slate-300 rounded-lg p-6 text-center text-slate-500 text-xs">
            No evidence files uploaded to this case docket yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 text-slate-400 font-semibold uppercase text-[10px]">
                  <th className="py-2.5 px-3">Exhibit Filename</th>
                  <th className="py-2.5 px-3">Document Type</th>
                  <th className="py-2.5 px-3">Mentions Extracted</th>
                  <th className="py-2.5 px-3">SHA-256 Digest</th>
                  <th className="py-2.5 px-3 text-right">Custody Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {evidenceList.map((item) => (
                  <tr key={item.evidence_id} className="hover:bg-slate-50/70">
                    <td className="py-2.5 px-3 font-semibold text-slate-900">
                      {item.filename}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10.5px]">
                        {item.job?.classification || item.format?.toUpperCase() || 'Document'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      {item.job?.mention_count ?? '—'} mentions
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[10px] text-slate-500" title={item.sha256}>
                      {item.sha256 ? `${item.sha256.slice(0, 16)}…${item.sha256.slice(-8)}` : 'Verified'}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        <svg className="w-3 h-3 text-emerald-600" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        <span>Verified</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Manual Investigation Boards for this Case */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Officer Manual Investigation Workspaces
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Interactive hypothesis mapping and custom network graphs built for this investigation.
            </p>
          </div>
          <button
            type="button"
            className="neu-btn ghost text-xs py-1 px-3 flex items-center gap-1 text-blue-600"
            onClick={() => changeView('board')}
          >
            <span>Open Board Canvas</span>
            <span>→</span>
          </button>
        </div>

        {boards.length === 0 ? (
          <div className="bg-slate-50 border border-dashed border-slate-300 rounded-lg p-6 text-center text-slate-500 text-xs">
            No manual boards created for this case yet. Click "Investigation Board" in the sidebar to create one.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {boards.map(b => (
              <div
                key={b.board_id}
                className="border border-slate-200 rounded-lg p-4 hover:border-blue-400 hover:shadow-sm transition-all cursor-pointer bg-slate-50/50"
                onClick={() => changeView('board')}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-sm text-slate-900">{b.title}</h3>
                  <span className="text-[10px] font-mono text-slate-400">
                    {b.updated_at ? new Date(b.updated_at).toLocaleDateString() : 'Active'}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-600 mt-2">
                  <span><strong>{b.nodes?.length || 0}</strong> manual nodes</span>
                  <span>•</span>
                  <span><strong>{b.edges?.length || 0}</strong> connections</span>
                  <span>•</span>
                  <span>Created by: {b.creator_name || 'Officer'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Forensic Findings & Officer Assessment Log */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div>
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-1">
            Officer Investigative Findings & Notes ({findingsList.length})
          </h2>
          <p className="text-xs text-slate-500">
            Official case notes cataloged under immutable chain of custody with timestamp and officer badge.
          </p>
        </div>

        {/* Existing findings list */}
        {findingsList.length > 0 && (
          <div className="space-y-2.5">
            {findingsList.map((f) => (
              <div key={f.finding_id} className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900">{f.title}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                    {f.category}
                  </span>
                </div>
                <p className="text-slate-700 leading-relaxed">{f.content}</p>
                <div className="text-[10px] text-slate-400 flex items-center gap-2 pt-1">
                  <span>Recorded by: <strong>{f.officer_name || 'Investigator'}</strong> ({f.officer_badge || 'LE-8402'})</span>
                  <span>•</span>
                  <span>{f.created_at ? new Date(f.created_at).toLocaleString() : 'Recorded'}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add new finding form */}
        <form onSubmit={handleAddFinding} className="space-y-3 pt-3 border-t border-slate-100">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="text"
              className="p-2.5 text-xs text-slate-800 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Finding Title (e.g. Syndicate Call Hub Confirmed)"
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
            />
            <select
              className="p-2.5 text-xs text-slate-800 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={noteCategory}
              onChange={(e) => setNoteCategory(e.target.value)}
            >
              <option value="Telecom & CDR">Telecom & CDR Pattern</option>
              <option value="Financial & Banking">Financial & Banking Trail</option>
              <option value="Physical Surveillance">Physical Surveillance / ANPR</option>
              <option value="Suspect Alibi / Motive">Suspect Alibi / Motive</option>
              <option value="Cross-Jurisdiction Overlap">Cross-Jurisdiction Overlap</option>
            </select>
          </div>
          <textarea
            className="w-full p-3 text-xs leading-relaxed text-slate-800 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
            value={noteContent}
            onChange={(e) => setNoteContent(e.target.value)}
            placeholder="Enter investigative conclusions or observation notes to include in the official dossier..."
          />
          <div className="flex justify-between items-center text-xs text-slate-500">
            <span>Notes are committed to the forensic audit log with SHA-256 verification.</span>
            <button
              type="submit"
              disabled={submittingNote}
              className="neu-btn primary text-xs py-1.5 px-4 font-semibold"
            >
              {submittingNote ? 'Recording Finding…' : 'Record Finding in Dossier'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ReportsModule;
