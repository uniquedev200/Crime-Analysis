import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { API, Case, OfficerSession } from '../services/api';
import './integrity.css';

export interface CaseIntegrityRecord {
  case_id: string;
  case_name: string;
  status: 'Verified' | 'Not Verified' | 'Verification Failed' | 'Verification Incomplete';
  total_files: number;
  verified_files: number;
  failed_files: number;
  missing_files: number;
  verified_by?: string | null;
  officer_badge?: string | null;
  verified_at?: string | null;
  last_verification_date?: string | null;
}

export interface CaseSummaryMetrics {
  total_cases: number;
  verified_cases: number;
  attention_cases: number;
  not_verified_cases?: number;
}

export interface ActivityTimelineItem {
  event_id: string;
  sequence_num: number;
  action_type: string;
  title: string;
  description: string;
  officer_name: string;
  officer_badge: string;
  timestamp: string;
  formatted_date: string;
  status_type: 'verified' | 'error' | 'warning' | 'info';
  icon_type: string;
}

export interface IntegrityModuleProps {
  cases: Case[];
  fetchCases: () => Promise<Case[]>;
  addToast: (msg: string, type?: string) => void;
  officerSession?: OfficerSession | null;
  selectedCase?: string | null;
  onSelectCase?: (caseId: string) => void;
  activeSection?: 'cases' | 'timeline';
  onNavigateSection?: (section: 'cases' | 'timeline') => void;
}

// Strictly format dates to "DD MMM YYYY, HH:mm" (e.g. 17 Oct 2026, 17:45)
function formatDateClean(isoString?: string | null): string {
  if (!isoString) return 'Not yet verified';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  } catch {
    return isoString;
  }
}

export function IntegrityModule({
  cases: propCases,
  fetchCases,
  addToast,
  officerSession,
  selectedCase: propSelectedCase,
  onSelectCase,
  activeSection: propActiveSection,
  onNavigateSection
}: IntegrityModuleProps) {
  // Navigation: "cases" (Case Integrity) or "timeline" (Activity Timeline)
  const [internalSection, setInternalSection] = useState<'cases' | 'timeline'>('cases');
  const activeSection = propActiveSection || internalSection;

  const setSection = (sec: 'cases' | 'timeline') => {
    setInternalSection(sec);
    if (onNavigateSection) {
      onNavigateSection(sec);
    }
  };

  // State
  const [summary, setSummary] = useState<CaseSummaryMetrics>({
    total_cases: 0,
    verified_cases: 0,
    attention_cases: 0,
    not_verified_cases: 0
  });
  const [caseRecords, setCaseRecords] = useState<CaseIntegrityRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(propSelectedCase || '');

  // Synchronize when propSelectedCase changes from parent
  useEffect(() => {
    if (propSelectedCase && propSelectedCase !== selectedCaseId) {
      setSelectedCaseId(propSelectedCase);
    }
  }, [propSelectedCase]);

  const changeSelectedCase = (cid: string) => {
    setSelectedCaseId(cid);
    if (onSelectCase) {
      onSelectCase(cid);
    }
  };

  const [timeline, setTimeline] = useState<ActivityTimelineItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [verifyingCaseId, setVerifyingCaseId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [downloadingCert, setDownloadingCert] = useState<boolean>(false);

  // Authenticated officer info
  const officerName = officerSession?.officerName || 'Rahul Sharma';
  const officerBadge = officerSession?.badgeNumber || 'IND-LE-8402';

  // Last access record ref to prevent rapid duplicates in same render
  const lastAccessLoggedRef = useRef<string>('');

  // 1. Fetch Case Integrity Records & Summary
  const loadCaseData = useCallback(async () => {
    try {
      const [sumRes, casesRes] = await Promise.all([
        API.get<CaseSummaryMetrics>('/api/v1/integrity/cases/summary').catch(() => ({
          total_cases: 0,
          verified_cases: 0,
          attention_cases: 0,
          not_verified_cases: 0
        })),
        API.get<{ total: number; cases: CaseIntegrityRecord[] }>('/api/v1/integrity/cases').catch(() => ({
          total: 0,
          cases: []
        }))
      ]);

      setSummary(sumRes);
      const list = casesRes.cases || [];
      setCaseRecords(list);

      // Select default case if none selected
      if (!selectedCaseId && list.length > 0) {
        const initial = propSelectedCase || list[0].case_id;
        setSelectedCaseId(initial);
      }
    } catch (err) {
      console.error('Failed to load integrity cases:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedCaseId, propSelectedCase]);

  // 2. Fetch Activity Timeline for Selected Case
  const loadTimeline = useCallback(async (caseId: string) => {
    if (!caseId) return;
    try {
      const res = await API.get<{ case_id: string; total_events: number; timeline: ActivityTimelineItem[] }>(
        `/api/v1/integrity/cases/${encodeURIComponent(caseId)}/timeline?limit=100`
      );
      setTimeline(res.timeline || []);
    } catch (err) {
      console.error(`Failed to load timeline for case ${caseId}:`, err);
    }
  }, []);

  // 3. Log Case Access by Authenticated Officer
  const recordCaseAccess = useCallback(async (caseId: string) => {
    if (!caseId) return;
    const key = `${caseId}_${officerBadge}`;
    if (lastAccessLoggedRef.current === key) return;
    lastAccessLoggedRef.current = key;

    try {
      await API.post(`/api/v1/integrity/cases/${encodeURIComponent(caseId)}/access`, {
        officer_name: officerName,
        officer_badge: officerBadge,
        action_type: 'CASE_VIEWED'
      });
      // Refresh timeline after recording access
      loadTimeline(caseId);
    } catch (err) {
      console.warn('Could not record case access event:', err);
    }
  }, [officerName, officerBadge, loadTimeline]);

  // Initial Data Load
  useEffect(() => {
    loadCaseData();
  }, [loadCaseData]);

  // When selectedCaseId changes, load timeline and record access
  useEffect(() => {
    if (selectedCaseId) {
      loadTimeline(selectedCaseId);
      recordCaseAccess(selectedCaseId);
    }
  }, [selectedCaseId, loadTimeline, recordCaseAccess]);

  // 4. Polling for Live Activity Timeline (every 3 seconds)
  useEffect(() => {
    if (activeSection !== 'timeline' || !selectedCaseId) return;

    const interval = setInterval(() => {
      loadTimeline(selectedCaseId);
    }, 3000);

    return () => clearInterval(interval);
  }, [activeSection, selectedCaseId, loadTimeline]);

  // 5. Verify Case Action (Genuine Background SHA-256 Recalculation)
  const handleVerifyCase = async (caseId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (verifyingCaseId) return;

    setVerifyingCaseId(caseId);
    addToast(`Running cryptographic verification for ${caseId}...`, 'info');

    try {
      const res = await API.post<CaseIntegrityRecord>(`/api/v1/integrity/cases/${encodeURIComponent(caseId)}/verify`, {
        officer_name: officerName,
        officer_badge: officerBadge
      });

      addToast(`Case ${caseId} verification result: ${res.status}`, res.status === 'Verified' ? 'success' : 'warning');
      await loadCaseData();
      if (selectedCaseId === caseId) {
        await loadTimeline(caseId);
      }
    } catch (err) {
      console.error(`Verification failed for case ${caseId}:`, err);
      addToast(`Failed to verify case ${caseId}: ${String(err)}`, 'error');
    } finally {
      setVerifyingCaseId(null);
    }
  };

  // 6. Court-Grade Verification Certificate PDF Export
  const handleExportCertificate = async (caseId: string) => {
    setDownloadingCert(true);
    addToast('Generating Court-Grade Verification Certificate (PDF)...', 'info');

    try {
      // Find an evidence item for this case to generate certificate
      const evList = await API.get<{ evidence: Array<{ evidence_id: string; filename: string }> }>(
        `/api/v1/integrity/evidence?case_id=${encodeURIComponent(caseId)}`
      );

      const targetEid = evList?.evidence?.[0]?.evidence_id;
      if (!targetEid) {
        addToast('No evidence files available in this case for certificate generation.', 'warning');
        setDownloadingCert(false);
        return;
      }

      const res = await fetch(
        `/api/v1/integrity/evidence/${encodeURIComponent(targetEid)}/certificate?officer_name=${encodeURIComponent(
          officerName
        )}&officer_badge=${encodeURIComponent(officerBadge)}`
      );

      if (!res.ok) throw new Error('Failed to download certificate');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ATLAS_FORENSIC_CERTIFICATE_${caseId.toUpperCase()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      addToast('Verification Certificate downloaded successfully', 'success');
    } catch (err) {
      console.error('Certificate generation error:', err);
      addToast('Error generating PDF certificate', 'error');
    } finally {
      setDownloadingCert(false);
    }
  };

  // Filtered cases by search query
  const filteredCases = useMemo(() => {
    if (!searchQuery.trim()) return caseRecords;
    const q = searchQuery.toLowerCase();
    return caseRecords.filter(
      (c) => c.case_id.toLowerCase().includes(q) || (c.case_name && c.case_name.toLowerCase().includes(q))
    );
  }, [caseRecords, searchQuery]);

  // Selected Case Object
  const selectedCase = useMemo(() => {
    return caseRecords.find((c) => c.case_id === selectedCaseId) || caseRecords[0];
  }, [caseRecords, selectedCaseId]);

  // Render Status Badge
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'Verified':
        return (
          <span className="status-badge-verified">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            Verified
          </span>
        );
      case 'Verification Failed':
        return (
          <span className="status-badge-mismatch">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            Verification Failed
          </span>
        );
      case 'Verification Incomplete':
        return (
          <span className="status-badge-awaiting">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            Verification Incomplete
          </span>
        );
      case 'Not Verified':
      default:
        return (
          <span className="status-badge-missing">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
                clipRule="evenodd"
              />
            </svg>
            Not Verified
          </span>
        );
    }
  };

  // Render Timeline Icon
  const renderTimelineIcon = (iconType: string, statusType: string) => {
    if (iconType === 'verified') {
      return (
        <span className="timeline-node-icon verified">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'failed') {
      return (
        <span className="timeline-node-icon failed">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'deleted') {
      return (
        <span className="timeline-node-icon failed" style={{ background: '#DC2626' }}>
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'warning') {
      return (
        <span className="timeline-node-icon warning">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'viewed') {
      return (
        <span className="timeline-node-icon viewed">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
            <path
              fillRule="evenodd"
              d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'upload') {
      return (
        <span className="timeline-node-icon upload">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }
    if (iconType === 'custody') {
      return (
        <span className="timeline-node-icon custody">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M12.586 4.586a2 2 0 112.828 2.828l-3 3a2 2 0 01-2.828 0 1 1 0 00-1.414 1.414 4 4 0 005.656 0l3-3a4 4 0 00-5.656-5.656l-1.5 1.5a1 1 0 101.414 1.414l1.5-1.5zm-5 5a2 2 0 012.828 0 1 1 0 101.414-1.414 4 4 0 00-5.656 0l-3 3a4 4 0 105.656 5.656l1.5-1.5a1 1 0 10-1.414-1.414l-1.5 1.5a2 2 0 11-2.828-2.828l3-3z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    }

    // Default activity icon
    return (
      <span className="timeline-node-icon default">
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
          <path
            fillRule="evenodd"
            d="M2 5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3 1h6v2H5V6zm6 4H5v2h6v-2zm-6 4h4v2H5v-2z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  };

  return (
    <div className="integrity-shell">
      {/* Top Header */}
      <div className="integrity-header">
        <div className="integrity-title-wrap">
          <div className="integrity-brand-icon">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <div>
            <h1 className="integrity-title">
              Evidence Integrity Center
              <span className="integrity-status-pill">
                <span className="integrity-pulse-dot" />
                Live Verification Active
              </span>
            </h1>
            <p className="integrity-subtitle">
              Case-wise cryptographic verification and multi-officer investigative audit timeline
            </p>
          </div>
        </div>
      </div>

      {/* Top 3 Summary Metric Values (Exactly 3 cards) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: Total Cases */}
        <div className="integrity-metric-card">
          <div className="metric-top-row">
            <span>TOTAL CASES</span>
            <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <div className="metric-value-num">{summary.total_cases}</div>
          <div className="metric-sub-text">Registered investigation cases</div>
        </div>

        {/* Card 2: Verified Cases */}
        <div className="integrity-metric-card verified">
          <div className="metric-top-row">
            <span>VERIFIED CASES</span>
            <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="metric-value-num text-emerald-700">{summary.verified_cases}</div>
          <div className="metric-sub-text text-emerald-600">Cryptographically verified</div>
        </div>

        {/* Card 3: Cases Needing Attention */}
        <div className={`integrity-metric-card ${summary.attention_cases > 0 ? 'tampered-alert' : ''}`}>
          <div className="metric-top-row">
            <span>CASES NEEDING ATTENTION</span>
            <svg
              className={`w-4 h-4 ${summary.attention_cases > 0 ? 'text-red-600' : 'text-slate-400'}`}
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className={`metric-value-num ${summary.attention_cases > 0 ? 'text-red-700' : 'text-slate-800'}`}>
            {summary.attention_cases}
          </div>
          <div className="metric-sub-text">
            {summary.attention_cases > 0 ? 'Verification failed or incomplete' : 'All cases verified intact'}
          </div>
        </div>
      </div>

      {/* =========================================================================
          SECTION 1: CASE INTEGRITY
          ========================================================================= */}
      {activeSection === 'cases' && (
        <div className="flex flex-col gap-4">
          {/* Controls Bar: Search & Refresh */}
          <div className="integrity-controls-wrapper">
            <div className="relative flex-1 max-w-md">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-slate-400">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </span>
              <input
                type="text"
                className="integrity-search-input"
                placeholder="Search cases by Case ID or Case Name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={loadCaseData}
                className="integrity-btn-secondary"
                title="Refresh case verification status"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            </div>
          </div>

          {/* Cases Table */}
          <div className="integrity-panel-card">
            <div className="integrity-table-container">
              <table className="integrity-table">
                <thead>
                  <tr>
                    <th>CASE ID</th>
                    <th>CASE NAME / TITLE</th>
                    <th>LAST VERIFICATION</th>
                    <th>VERIFICATION STATUS</th>
                    <th style={{ textAlign: 'right' }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-slate-500">
                        <div className="flex items-center justify-center gap-2">
                          <svg className="animate-spin h-5 w-5 text-slate-500" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                          </svg>
                          Loading case records...
                        </div>
                      </td>
                    </tr>
                  ) : filteredCases.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-slate-500">
                        No registered cases found matching your criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredCases.map((c) => {
                      const isVerifying = verifyingCaseId === c.case_id;
                      const isSelected = selectedCaseId === c.case_id;

                      return (
                        <tr
                          key={c.case_id}
                          className={`cursor-pointer transition-colors ${
                            isSelected ? 'bg-slate-50' : 'hover:bg-slate-50'
                          }`}
                          onClick={() => {
                            changeSelectedCase(c.case_id);
                            setSection('timeline');
                          }}
                        >
                          {/* Case ID */}
                          <td>
                            <div className="font-bold text-slate-900 flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-slate-400" />
                              {c.case_id}
                            </div>
                          </td>

                          {/* Case Name / Title */}
                          <td>
                            <div className="font-semibold text-slate-800">
                              {c.case_name || c.case_id.toUpperCase()}
                            </div>
                          </td>

                          {/* Last Verification Date & Time */}
                          <td className="text-slate-600 font-mono text-xs">
                            {formatDateClean(c.verified_at)}
                          </td>

                          {/* Verification Status */}
                          <td>
                            <div className="flex flex-col items-start gap-0.5">
                              {renderStatusBadge(c.status)}
                              {c.missing_files > 0 && (
                                <span className="text-[11px] text-amber-700 font-semibold flex items-center gap-1 mt-0.5">
                                  <svg className="w-3 h-3 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                  </svg>
                                  {c.missing_files} file(s) missing/deleted
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Verify Case Action */}
                          <td style={{ textAlign: 'right' }}>
                            <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={(e) => handleVerifyCase(c.case_id, e)}
                                disabled={isVerifying}
                                className="integrity-btn-primary"
                                style={{ padding: '6px 12px', fontSize: '12px' }}
                              >
                                {isVerifying ? (
                                  <>
                                    <svg className="animate-spin h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                                    </svg>
                                    Verifying...
                                  </>
                                ) : (
                                  <>
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                                    </svg>
                                    Verify Case
                                  </>
                                )}
                              </button>

                              <button
                                onClick={() => {
                                  setSelectedCaseId(c.case_id);
                                  setSection('timeline');
                                }}
                                className="integrity-btn-secondary"
                                style={{ padding: '6px 10px', fontSize: '12px' }}
                                title="View activity timeline for this case"
                              >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                Timeline
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
        </div>
      )}

      {/* =========================================================================
          SECTION 2: ACTIVITY TIMELINE
          ========================================================================= */}
      {activeSection === 'timeline' && (
        <div className="flex flex-col gap-4">
          {/* Timeline Header & Case Selector */}
          <div className="integrity-panel-card p-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  Select Case:
                </label>
                <select
                  value={selectedCaseId}
                  onChange={(e) => changeSelectedCase(e.target.value)}
                  className="integrity-select-control font-semibold"
                >
                  {caseRecords.map((c) => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_id} - {c.case_name || 'Investigation'}
                    </option>
                  ))}
                </select>
              </div>

              {/* Case Action Buttons */}
              {selectedCase && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => handleVerifyCase(selectedCase.case_id, e)}
                    disabled={verifyingCaseId === selectedCase.case_id}
                    className="integrity-btn-primary"
                  >
                    {verifyingCaseId === selectedCase.case_id ? (
                      <>
                        <svg className="animate-spin h-4 w-4 text-white" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                        Verifying...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                        Verify Case
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => handleExportCertificate(selectedCase.case_id)}
                    disabled={downloadingCert}
                    className="integrity-btn-secondary"
                    title="Export court-ready official verification certificate PDF"
                  >
                    <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Certificate PDF
                  </button>
                </div>
              )}
            </div>

            {/* Selected Case Overview Pill Bar */}
            {selectedCase && (
              <div className="mt-4 pt-3 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-4">
                  <div>
                    <span className="text-slate-500 font-medium">Case ID:</span>{' '}
                    <span className="font-bold text-slate-800">{selectedCase.case_id}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 font-medium">Title:</span>{' '}
                    <span className="font-semibold text-slate-800">{selectedCase.case_name}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div>
                    <span className="text-slate-500 font-medium">Last Verification:</span>{' '}
                    <span className="font-mono text-slate-800">{formatDateClean(selectedCase.verified_at)}</span>
                  </div>
                  <div className="flex flex-col items-end gap-0.5">
                    {renderStatusBadge(selectedCase.status)}
                    {selectedCase.missing_files > 0 && (
                      <span className="text-[11px] text-amber-700 font-semibold flex items-center gap-1">
                        <svg className="w-3 h-3 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        {selectedCase.missing_files} file(s) missing/deleted
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Vertical Chronological Timeline */}
          <div className="integrity-panel-card p-6">
            <div className="flex items-center justify-between mb-6 pb-3 border-b border-slate-200">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Case Activity Audit Trail
              </h2>
              <span className="text-xs text-slate-500 flex items-center gap-1.5 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Live Polling (3s) · Multi-Officer Tracking
              </span>
            </div>

            {timeline.length === 0 ? (
              <div className="py-12 text-center text-slate-500">
                No activity events recorded yet for this case.
              </div>
            ) : (
              <div className="relative pl-8 space-y-6 before:content-[''] before:absolute before:left-3.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                {timeline.map((event) => (
                  <div key={event.event_id} className="relative group">
                    {/* Timeline Node Icon */}
                    <div className="absolute -left-8 top-1.5 flex items-center justify-center">
                      {renderTimelineIcon(event.icon_type, event.status_type)}
                    </div>

                    {/* Timeline Event Card */}
                    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:border-slate-400 transition-colors">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-1.5">
                        <div className="font-bold text-sm text-slate-900 flex items-center gap-2">
                          {event.title}
                        </div>
                        <div className="text-xs font-mono text-slate-500 font-medium">
                          {event.formatted_date || formatDateClean(event.timestamp)}
                        </div>
                      </div>

                      <p className="text-xs text-slate-700 leading-relaxed mb-3">
                        {event.description}
                      </p>

                      <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
                        <div className="flex items-center gap-1.5 text-slate-600">
                          <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                          </svg>
                          <span className="font-semibold text-slate-800">{event.officer_name}</span>
                          <span className="text-slate-400">·</span>
                          <span className="font-mono text-slate-500">{event.officer_badge}</span>
                        </div>

                        <span className="text-[11px] font-mono text-slate-400">
                          SEQ #{event.sequence_num}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
