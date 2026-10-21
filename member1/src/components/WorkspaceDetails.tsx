import React, { useEffect, useRef, useState } from 'react';
import { API } from '../services/api';
import { sourceReferences } from '../services/workspace';
import { EntityPropertiesTable } from './EntityPropertiesTable';

export interface WorkspaceDetailsProps {
  title: string;
  record: Record<string, unknown>;
  onClose: () => void;
  allowedCaseIds: string[];
  activeCaseId?: string;
  onFindingAdded?: (msg: string) => void;
}

export function WorkspaceDetails({
  title,
  record,
  onClose,
  allowedCaseIds,
  activeCaseId,
  onFindingAdded
}: WorkspaceDetailsProps) {
  const [source, setSource] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const closeRef = useRef<HTMLButtonElement>(null);

  // Finding form state
  const [showFindingForm, setShowFindingForm] = useState(false);
  const [findingTitle, setFindingTitle] = useState('');
  const [findingCategory, setFindingCategory] = useState('Graph Analysis');
  const [findingSeverity, setFindingSeverity] = useState('HIGH');
  const [findingContent, setFindingContent] = useState('');
  const [savingFinding, setSavingFinding] = useState(false);
  const [findingSuccess, setFindingSuccess] = useState('');

  const props = (record.properties || record) as Record<string, unknown>;
  const references = sourceReferences(record);

  // Effective Case ID
  const caseId =
    activeCaseId ||
    (Array.isArray(props.case_ids) && props.case_ids[0]) ||
    (typeof props.case_id === 'string' && props.case_id) ||
    allowedCaseIds[0] ||
    '';

  // Initialize finding pre-fill when toggled open
  const handleOpenFindingForm = () => {
    const isRelationship = Boolean(record.from || record.relationship_type);
    const rType = String(record.relationship_type || props.type || '');
    const fromId = String(record.from || '');
    const toId = String(record.to || '');

    const defaultTitle = isRelationship
      ? `Link: ${fromId} [${rType}] ${toId}`
      : `Entity Observation: ${title}`;

    const quote = String(props.verbatim_quote || props.verbatim_source_quote || props.summary || '');
    const conf = props.confidence ? ` (Confidence: ${props.confidence})` : '';
    const srcDoc = props.supporting_file ? `\nSupporting Document: ${props.supporting_file}` : '';

    const defaultContent = isRelationship
      ? `Observed Relationship in Knowledge Graph:\n• Type: ${rType}${conf}\n• Source: ${fromId}\n• Target: ${toId}\n• Evidence / Details: ${quote || 'Evidence-backed connection'}${srcDoc}`
      : `Observed Entity in Knowledge Graph:\n• Identifier: ${String(props.id || props.person_id || props.phone_number || title)}\n• Role / Attributes: ${String(props.role || props.device_type || props.description || 'N/A')}\n• Evidence: ${quote || 'Extracted from case documents'}${srcDoc}`;

    setFindingTitle(defaultTitle);
    setFindingCategory(isRelationship ? 'Graph Analysis' : 'Lead');
    setFindingSeverity('HIGH');
    setFindingContent(defaultContent);
    setShowFindingForm(true);
    setFindingSuccess('');
  };

  const handleSaveFinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseId) {
      setError('Cannot associate finding: No active case identifier found.');
      return;
    }
    if (!findingContent.trim()) {
      setError('Finding note content cannot be empty.');
      return;
    }

    setSavingFinding(true);
    setError('');
    try {
      await API.post(`/api/cases/${encodeURIComponent(caseId)}/findings`, {
        title: findingTitle.trim() || 'Knowledge Graph Observation',
        category: findingCategory,
        severity: findingSeverity,
        content: findingContent.trim(),
        officer_name: 'Investigating Officer',
        officer_badge: 'PS-1001'
      });

      setFindingSuccess('Finding note recorded successfully in Case Registry.');
      setShowFindingForm(false);
      if (onFindingAdded) {
        onFindingAdded(`Finding added to case ${caseId}`);
      }
    } catch (err: any) {
      setError(`Failed to save finding: ${err.message || 'Server error'}`);
    } finally {
      setSavingFinding(false);
    }
  };

  useEffect(() => {
    const prior = document.activeElement as HTMLElement;
    closeRef.current?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
      if (event.key === 'Tab') {
        const panel = closeRef.current?.closest('[role="dialog"]');
        const controls = Array.from(
          panel?.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, [tabindex="0"]') || []
        );
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.removeEventListener('keydown', handler);
      prior?.focus();
    };
  }, [onClose]);

  const openSource = async (id: string) => {
    setLoading(true);
    setError('');
    setSource(null);
    try {
      const data = await API.get<Record<string, unknown>>(`/api/entities/${encodeURIComponent(id)}`);
      const node = (data.node || data) as Record<string, unknown>;
      const p = (node.properties || node) as Record<string, unknown>;
      const ids = Array.isArray(p.case_ids) ? (p.case_ids as string[]) : [];
      if (ids.length && !ids.some(cid => allowedCaseIds.includes(cid))) {
        throw new Error('Source outside current scope.');
      }
      setSource(p);
    } catch {
      setError('Supporting evidence is unavailable in your current workspace.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="workspace-drawer-overlay"
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section className="workspace-drawer" role="dialog" aria-modal="true" aria-labelledby="workspace-detail-title">
        <div className="card-header">
          <h2 id="workspace-detail-title">{title}</h2>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="neu-btn primary"
              style={{ fontSize: '12px', padding: '4px 10px' }}
              onClick={handleOpenFindingForm}
              title="Record this node or link as an official finding note"
            >
              + Add to Findings
            </button>
            <button ref={closeRef} className="neu-btn ghost" onClick={onClose} aria-label="Close details">
              Close
            </button>
          </div>
        </div>

        {findingSuccess && (
          <div
            style={{
              background: 'rgba(22, 133, 104, 0.15)',
              border: '1px solid #168568',
              color: 'var(--text)',
              padding: '8px 12px',
              borderRadius: '6px',
              margin: '8px 0',
              fontSize: '12px'
            }}
          >
            ✓ {findingSuccess}
          </div>
        )}

        {showFindingForm && (
          <div
            style={{
              background: 'var(--panel-bg, #1a201e)',
              border: '1px solid rgba(255,255,255,0.15)',
              padding: '12px',
              borderRadius: '8px',
              margin: '10px 0 16px 0'
            }}
          >
            <h3 style={{ margin: '0 0 10px 0', fontSize: '13px', fontWeight: 600 }}>
              Record Investigation Finding Note
            </h3>
            <form onSubmit={handleSaveFinding} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div>
                <label style={{ fontSize: '11px', display: 'block', marginBottom: '2px', color: 'var(--text-dim)' }}>
                  Finding Title
                </label>
                <input
                  type="text"
                  className="control"
                  style={{ width: '100%', fontSize: '12px', padding: '6px 8px' }}
                  value={findingTitle}
                  onChange={e => setFindingTitle(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '11px', display: 'block', marginBottom: '2px', color: 'var(--text-dim)' }}>
                    Category
                  </label>
                  <select
                    className="control"
                    style={{ width: '100%', fontSize: '12px', padding: '6px 8px' }}
                    value={findingCategory}
                    onChange={e => setFindingCategory(e.target.value)}
                  >
                    <option value="Graph Analysis">Graph Analysis</option>
                    <option value="Communication Link">Communication Link</option>
                    <option value="Lead">Investigative Lead</option>
                    <option value="Forensic Lead">Forensic Lead</option>
                    <option value="Financial Transfer">Financial Transfer</option>
                    <option value="Vehicle Movement">Vehicle Movement</option>
                    <option value="Observation">General Observation</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '11px', display: 'block', marginBottom: '2px', color: 'var(--text-dim)' }}>
                    Severity / Priority
                  </label>
                  <select
                    className="control"
                    style={{ width: '100%', fontSize: '12px', padding: '6px 8px' }}
                    value={findingSeverity}
                    onChange={e => setFindingSeverity(e.target.value)}
                  >
                    <option value="LOW">LOW</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="HIGH">HIGH</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', display: 'block', marginBottom: '2px', color: 'var(--text-dim)' }}>
                  Officer's Finding Notes & Observations
                </label>
                <textarea
                  className="control"
                  rows={4}
                  style={{ width: '100%', fontSize: '12px', padding: '6px 8px', resize: 'vertical' }}
                  value={findingContent}
                  onChange={e => setFindingContent(e.target.value)}
                  placeholder="Record observations, corroborating leads, or analysis notes..."
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' }}>
                <button
                  type="button"
                  className="neu-btn ghost"
                  style={{ fontSize: '12px', padding: '4px 10px' }}
                  onClick={() => setShowFindingForm(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="neu-btn primary"
                  style={{ fontSize: '12px', padding: '4px 12px' }}
                  disabled={savingFinding}
                >
                  {savingFinding ? 'Saving…' : 'Save to Case Findings'}
                </button>
              </div>
            </form>
          </div>
        )}

        <p className="workspace-detail-note">
          {String(props.review_status || props.verification_status || 'Review status: Evidence Verified')}
        </p>

        <EntityPropertiesTable properties={props} />

        <h3>Supporting evidence</h3>
        {references.length ? (
          references.map(id => (
            <button key={id} className="source-reference-button" onClick={() => openSource(id)}>
              View supporting evidence <span className="mono">{id}</span>
            </button>
          ))
        ) : (
          <p className="workspace-muted">
            {props.supporting_file
              ? `Source document: ${props.supporting_file}`
              : 'No source reference supplied for this record.'}
          </p>
        )}

        {loading && <p role="status">Loading source record…</p>}
        {error && <p role="alert" style={{ color: 'var(--danger, #ef4444)' }}>{error}</p>}
        {source && (
          <div className="source-record-panel">
            <h3>Source record</h3>
            <EntityPropertiesTable properties={source} />
          </div>
        )}
      </section>
    </div>
  );
}
