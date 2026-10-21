import { useEffect, useMemo, useState } from 'react';
import { API, Case, Insight, HealthStatus, GraphNode, GraphEdge } from '../services/api';
import { caseCategory, displayDate, LoadStatus } from '../services/workspace';
import { FileStore } from '../services/fileStore';
import { WorkspaceDetails } from './WorkspaceDetails';
import './overview.css';

export interface OverviewModuleProps { cases: Case[]; health: HealthStatus | null; insights: Insight[]; setInsights: (insights: Insight[]) => void; changeView: (view: string) => void; openAiDossier: (caseId: string, caseName: string) => void; loadStatus: LoadStatus; hasLoaded: boolean; onRetry: () => Promise<Case[]>; openCase: (id: string) => void; }
type Network = { nodes: GraphNode[]; edges: GraphEdge[] };
type Connection = GraphEdge & { caseId: string };
const LIMIT = 500;
const text = (value: unknown, fallback = 'Not recorded') => value == null || value === '' ? fallback : String(value);
const stamp = (value: unknown) => Number.isFinite(Date.parse(String(value))) ? Date.parse(String(value)) : 0;
const time = (value: unknown) => stamp(value) ? new Date(String(value)).toLocaleString('en-IN', { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }) : 'Not recorded';
function MetricIcon({ index }: {index:number}) {
  const paths = ['M3 7h7l2 2h9v11H3z M3 7V4h7l2 3', 'M6 3h8l4 4v14H6z M14 3v5h5 M9 12h6 M9 16h6', 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M17 4a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87', 'M8 7l8 10 M8 17l8-10 M8 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M20 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M8 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M20 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0'];
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={paths[index]}/></svg>;
}
export function OverviewModule({cases, changeView, loadStatus, hasLoaded, onRetry, openCase}: OverviewModuleProps) {
  const [networks, setNetworks] = useState<Record<string,Network>>({});
  const [networkStatus, setNetworkStatus] = useState<LoadStatus>('loading');
  const [failed, setFailed] = useState(0);
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState<{title:string; record:Record<string,unknown>} | null>(null);
  const ids = cases.map(c => c.case_id);
  const files = useMemo(() => FileStore.getAll().filter(f => cases.some(c => c.case_id.toLowerCase() === f.case_id.toLowerCase())), [cases]);
  useEffect(() => {
    let active = true;
    setNetworks({}); setFailed(0);
    if (!hasLoaded) { setNetworkStatus(loadStatus); return; }
    if (!cases.length) { setNetworkStatus('ready'); return; }
    setNetworkStatus('loading');
    Promise.allSettled(cases.slice(0,8).map(async c => ({id:c.case_id, data:await API.get<Network>('/api/graph?case_id=' + encodeURIComponent(c.case_id) + '&limit=' + LIMIT)})))
      .then(results => {
        if (!active) return;
        const next:Record<string,Network> = {};
        results.forEach(result => { if (result.status === 'fulfilled') next[result.value.id] = result.value.data; });
        setNetworks(next); setFailed(results.filter(r => r.status === 'rejected').length);
        setNetworkStatus(Object.keys(next).length ? 'ready' : 'error');
      });
    return () => {active = false;};
  }, [cases, hasLoaded, loadStatus, reload]);
  const entities = new Map<string,GraphNode>();
  const connections = new Map<string,Connection>();
  Object.entries(networks).forEach(([caseId, network]) => {
    network.nodes.forEach(n => {if (!n.labels?.some(l => ['Case','SourceRecord'].includes(l))) entities.set(n.id,n);});
    network.edges.forEach(e => {
      if (entities.has(e.source) && entities.has(e.target)) connections.set(e.id || [e.source,e.type,e.target,caseId].join('|'), {...e,caseId});
    });
  });
  const ready = hasLoaded && loadStatus !== 'error';
  const number = (n:number) => n.toLocaleString('en-IN');
  const graphValue = (n:number) => !ready || networkStatus === 'error' ? '—' : networkStatus === 'loading' ? '…' : number(n);
  const totalEvidenceCount = useMemo(() => {
    const localCount = files.length;
    const serverCount = cases.reduce((sum, c) => sum + (Number((c as any).evidence_count || (c.evidences ? c.evidences.length : 0)) || 0), 0);
    return Math.max(localCount, serverCount);
  }, [files, cases]);
  const metrics = [
    {label:'Total cases', value:hasLoaded ? number(cases.length) : loadStatus === 'loading' ? '…' : '—', note:'Cases loaded in this workspace', action:() => changeView('cases')},
    {label:'Evidence files', value:hasLoaded ? number(totalEvidenceCount) : '—', note:'Forensic evidence records', action:() => changeView('ingest')},
    {label:'Extracted entities', value:graphValue(entities.size), note:'Unique entities in loaded networks', action:() => changeView('search')},
    {label:'Connections detected', value:graphValue(connections.size), note:'Entity relationships in loaded networks', action:() => changeView('graph')}
  ];
  const matching = cases.filter(c => [c.case_id,c.case_name,c.fir_number].some(v => String(v || '').toLowerCase().includes(query.toLowerCase())));
  const activity = [
    ...files.filter(f => stamp(f.uploaded_at)).map(f => ({id:f.id, label:'Evidence file recorded', caseId:f.case_id, name:f.file_name, date:f.uploaded_at})),
    ...cases.filter(c => stamp(c.updated_at || c.last_updated)).map(c => ({id:'case-'+c.case_id,label:'Case updated',caseId:c.case_id,name:c.case_name || c.case_id,date:String(c.updated_at || c.last_updated)}))
  ].sort((a,b) => stamp(b.date)-stamp(a.date)).slice(0,5);
  const blank = (message:string) => <p className="ov-empty">{message}</p>;
  return <div className="overview-v2">
    <header className="ov-heading"><div><h2>Investigation overview</h2><p>Review your cases, evidence, and recorded connections.</p></div></header>
    {loadStatus === 'error' && <div className="workspace-error-panel" role="alert"><span>Case records are unavailable.{hasLoaded ? ' Showing previously loaded records.' : ''}</span><button className="neu-btn ghost" onClick={onRetry}>Retry</button></div>}
    <div className="ov-metrics">{metrics.map((m,index) => <button key={m.label} className="ov-metric" onClick={m.action}><span className="ov-metric-top"><span>{m.label}</span><MetricIcon index={index}/></span><strong>{m.value}</strong><small>{m.note}<span aria-hidden="true"> ↗</span></small></button>)}</div>
    <div className="ov-scope"><span>Network summary: up to 8 cases, {LIMIT} elements per request. Counts may be partial; source and case links are excluded.</span>{(failed > 0 || networkStatus === 'error') && <button className="workspace-text-button" onClick={() => setReload(n => n+1)}>Retry unavailable networks ({failed})</button>}</div>
    <section className="ov-panel"><header><div><h3>Case registry</h3><p>Case references and evidence at a glance</p></div><div className="ov-registry-actions"><input aria-label="Find a case" placeholder="Search case or FIR…" value={query} onChange={e => setQuery(e.target.value)}/><button className="workspace-text-button" onClick={() => changeView('cases')}>View all →</button></div></header>
      {!hasLoaded ? blank(loadStatus === 'error' ? 'Case records are unavailable.' : 'Loading case records…') : <div className="ov-table-wrap"><table><thead><tr><th>Case / FIR reference</th><th>Title</th><th>Category</th><th>Evidence*</th><th>Processing status</th><th>Last updated</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{matching.slice(0,5).map(c => <tr key={c.case_id}><td className="ov-reference">{c.fir_number || c.case_id}</td><td>{c.case_name || 'Untitled case'}</td><td>{caseCategory(c)}</td><td>{files.filter(f => f.case_id.toLowerCase() === c.case_id.toLowerCase()).length}</td><td><span className="ov-status">{text(c.processing_status).replace(/_/g,' ')}</span></td><td>{displayDate(c.updated_at || c.last_updated)}</td><td><button className="workspace-text-button" onClick={() => openCase(c.case_id)}>Open case →</button></td></tr>)}</tbody></table>{!matching.length && blank(query ? 'No cases match your search.' : 'No cases yet. Upload evidence to begin.')}</div>}
      <footer>*Evidence counts reflect files retained in this browser. Showing up to 5 cases.</footer>
    </section>
    <div className="ov-columns">
      <section className="ov-panel" id="overview-processing"><header><div><h3>Evidence processing</h3><p>Available file records</p></div><span className="ov-count">{files.length} files</span></header>
        {!hasLoaded ? blank('File records will appear after cases load.') : files.length ? <div className="ov-table-wrap"><table><thead><tr><th>Filename / case</th><th>Upload time</th><th>Status</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{[...files].sort((a,b)=>stamp(b.uploaded_at)-stamp(a.uploaded_at)).slice(0,5).map(f => <tr key={f.id}><td><strong>{f.file_name}</strong><small>{f.case_id}</small></td><td>{time(f.uploaded_at)}</td><td><span className="ov-status">Not recorded</span></td><td><button className="workspace-text-button" onClick={() => setDetail({title:f.file_name,record:{filename:f.file_name,case_id:f.case_id,uploaded_at:f.uploaded_at,file_type:f.file_type,file_size:f.file_size,processing_status:'Not recorded',storage:'Original retained in this browser'}})}>View details →</button></td></tr>)}</tbody></table></div> : blank('No evidence files retained in this browser.')}
        <footer>Queued, processing, completed, and failed states are not supplied by the current service. Retrying a job is not supported.</footer>
      </section>
      <section className="ov-panel"><header><div><h3>Recent activity</h3><p>Recorded uploads and case updates</p></div></header>
        {!hasLoaded ? blank('Load cases to view related activity.') : activity.length ? <ol className="ov-activity">{activity.map(a => <li key={a.id}><span className="ov-activity-dot" aria-hidden="true"/><div><strong>{a.label}</strong><p>{a.name} · {a.caseId}</p><time>{time(a.date)}</time></div><button className="workspace-text-button" onClick={() => openCase(a.caseId)}>Open record →</button></li>)}</ol> : blank('No dated uploads or case updates available.')}
        <footer>Analysis actions are not currently retained in an activity log.</footer>
      </section>
    </div>
    {detail && <WorkspaceDetails title={detail.title} record={detail.record} allowedCaseIds={ids} onClose={() => setDetail(null)}/>}
  </div>;
}
