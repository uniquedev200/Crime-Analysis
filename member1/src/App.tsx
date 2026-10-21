import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  API,
  NAV,
  TITLES,
  Case,
  Entity,
  Insight,
  HealthStatus,
  ViewId,
  ThemeMode,
  Toast,
  ModalState,
  OfficerSession,
  filterCasesForOfficer
} from './services/api';
import { LoadStatus } from './services/workspace';
import { Sidebar, TopHeader } from './components/Sidebar';
import { HomeModule } from './components/HomeModule';
import { AuthModule } from './components/AuthModule';
import { OverviewModule } from './components/OverviewModule';
import { GraphExplorerModule } from './components/GraphExplorerModule';
import { EntitySearchModule } from './components/EntitySearchModule';
import { ShortestPathModule } from './components/ShortestPathModule';
import { RankingsModule } from './components/RankingsModule';
import { PatternInsightsModule } from './components/PatternInsightsModule';
import { IntegrityModule } from './components/IntegrityModule';
import { CaseRegistryModule } from './components/CaseRegistryModule';
import { DataIngestionModule } from './components/DataIngestionModule';
import { InvestigationBoardModule } from './components/InvestigationBoardModule';
import { ReportsModule } from './components/ReportsModule';
import {
  EntityModalContent,
  AiDossierModalContent,
  ResetDbConfirmContent,
  DeleteCaseConfirmContent
} from './components/Modals';



export default function App() {
  // Default to clean Light Theme as requested
  const [theme, setTheme] = useState<ThemeMode>(() => { try { return localStorage.getItem('atlas_theme') === 'dark' ? 'dark' : 'light'; } catch { return 'light'; } });

  // Default to dedicated Home page
  const [view, setView] = useState<string>(() => {
    const h = location.hash.replace('#', '');
    return NAV.find(n => n.id === h) || h === 'auth' ? h : 'home';
  });

  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [caseLoadError, setCaseLoadError] = useState('');
  const [caseLoadStatus, setCaseLoadStatus] = useState<LoadStatus>('loading');
  const [casesHaveLoaded, setCasesHaveLoaded] = useState(false);
  const casesLoadingRef = useRef(false);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [modal, setModal] = useState<ModalState | null>(null);

  // Dynamic Investigator Session (No hardcoded default officer)
  const [officerSession, setOfficerSession] = useState<OfficerSession | null>(() => {
    try {
      const saved = localStorage.getItem('atlas_officer_session');
      if (saved) {
        const session = JSON.parse(saved) as OfficerSession;
        return session;
      }
      return null;
    } catch {
      return null;
    }
  });


  useEffect(() => {
    if (officerSession) {
      localStorage.setItem('atlas_officer_session', JSON.stringify(officerSession));
    } else {
      localStorage.removeItem('atlas_officer_session');
    }
  }, [officerSession]);

  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setModal(null); }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, []);

  // Apply theme to html root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('atlas_theme', theme);
  }, [theme]);

  // Sync Hash
  useEffect(() => {
    const handleHashChange = () => {
      const h = location.hash.replace('#', '');
      if (NAV.find(n => n.id === h) || h === 'auth') {
        setView(prev => (prev === h ? prev : h));
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const changeView = useCallback((newView: string): void => {
    setView(prev => {
      if (prev === newView) return prev;
      return newView;
    });
    if (window.location.hash !== `#${newView}`) {
      window.history.replaceState(null, '', `#${newView}`);
    }
    window.scrollTo(0, 0);
  }, []);

  const addToast = useCallback((msg: string, type: string = 'info'): void => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, msg, type, out: false }]);
    setTimeout(() => {
      setToasts(prev => prev.map(t => t.id === id ? { ...t, out: true } : t));
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 350);
    }, type === 'err' ? 6500 : 3800);
  }, []);

  // Health check
  const fetchHealth = useCallback(async (): Promise<void> => {
    try {
      const h = await API.get<HealthStatus>('/api/health');
      setHealth(h);
    } catch {
      setHealth(null);
    }
  }, []);

  // Backend records are authoritative; local evidence previews do not replace API cases.
  const fetchCases = useCallback(async (): Promise<Case[]> => {
    if (casesLoadingRef.current) return [];
    casesLoadingRef.current = true;
    setCaseLoadStatus('loading');
    try {
      const list = await API.get<Case[]>('/api/cases?limit=200');
      if (!Array.isArray(list)) throw new Error('Unexpected case list response.');
      setCases(list);
      setCaseLoadError('');
      setCaseLoadStatus('ready');
      setCasesHaveLoaded(true);
      return list;
    } catch (exception) {
      console.error('ATLAS case load failed', exception);
      setCaseLoadError('Case records are temporarily unavailable.');
      setCaseLoadStatus('error');
      return [];
    } finally { casesLoadingRef.current = false; }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchCases();
    const interval = setInterval(() => { fetchHealth(); fetchCases(); }, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchCases]);

  const toggleTheme = (): void => setTheme(prev => prev === 'dark' ? 'light' : 'dark');

  // Open Entity Modal
  const openEntityModal = useCallback(async (entityId: string): Promise<void> => {
    try {
      const e = await API.get<Record<string, unknown>>(`/api/entities/${encodeURIComponent(entityId)}`);
      setModal({ type: 'entity', data: e });
    } catch (err: unknown) {
      const error = err as Error;
      addToast(`Could not load entity: ${error.message}`, 'err');
    }
  }, [addToast]);

  // Open AI Insights Modal
  const openAiDossierModal = useCallback((caseId: string, caseName: string): void => {
    setModal({ type: 'ai_dossier', data: { caseId, caseName } });
  }, []);

  // Open Reset DB Confirmation
  const promptResetDatabase = useCallback((): void => {
    setModal({ type: 'reset_db' });
  }, []);

  // Open Delete Case Confirmation
  const promptDeleteCase = useCallback((caseId: string, caseName: string): void => {
    setModal({ type: 'delete_case', data: { caseId, caseName } });
  }, []);

  // Filter cases visible to the active officer session
  const visibleCases = useMemo(() => {
    return filterCasesForOfficer(cases, officerSession);
  }, [cases, officerSession]);

  return (
    <React.Fragment>
      <a className="skip-link" href="#main-content">Skip to workspace</a>
      {/* Dedicated Dynamic Auth Page */}
      {view === 'auth' ? (
        <AuthModule
          setOfficerSession={setOfficerSession}
          changeView={changeView}
          addToast={addToast}
          theme={theme}
          toggleTheme={toggleTheme}
        />
      ) : view === 'home' ? (
        <HomeModule
          theme={theme}
          setTheme={setTheme}
          cases={visibleCases}
          health={health}
          insights={insights}
          officerSession={officerSession}
          setOfficerSession={setOfficerSession}
          changeView={changeView}
          setSelectedCase={setSelectedCase}
          addToast={addToast}
        />
      ) : (
        <div className={`app-shell ${view === 'graph' ? 'investigate-shell' : ''}`}>
          {/* Top Bar: Left ATLAS brand, Right corner user profile with dropdown as logout */}
          <TopHeader
            view={view}
            health={health}
            officerSession={officerSession}
            setOfficerSession={setOfficerSession}
            changeView={changeView}
            addToast={addToast}
            theme={theme}
            toggleTheme={toggleTheme}
          />

          <div className="app-layout">
            {/* Section rail and the existing tools in a horizontal tab row. */}
            <Sidebar
              view={view}
              changeView={changeView}
            />

            {/* Main Right Content Area */}
            <div className="app-content">
              <div className="view-banner" style={(view === 'overview' || view === 'board' || (view === 'cases' && Boolean(selectedCase))) ? {display: 'none'} : undefined}>
                <h1>{TITLES[view]?.[0] || 'Command Center'}</h1>
              </div>




              <main className="main" id="main-content">
              {caseLoadError && view === 'cases' && <div className="service-notice" role="alert"><div><strong>{caseLoadError}</strong><p>{casesHaveLoaded ? 'Previously loaded records may be outdated.' : 'Retry to load your investigations.'}</p></div><button className="neu-btn ghost" onClick={() => { fetchHealth(); fetchCases(); }}>Retry</button></div>}
              {/* View Component Dispatcher */}
              <div key={view} className="view-pane">
                {view === 'overview' && (
                  <OverviewModule
                    cases={visibleCases}
                    loadStatus={caseLoadStatus}
                    hasLoaded={casesHaveLoaded}
                    onRetry={fetchCases}
                    openCase={id => { setSelectedCase(id); changeView('cases'); }}
                    health={health}
                    insights={insights}
                    setInsights={setInsights}
                    changeView={changeView}
                    openAiDossier={openAiDossierModal}
                  />
                )}
                {view === 'graph' && (
                  <GraphExplorerModule
                    cases={visibleCases}
                    selectedCase={selectedCase}
                    setSelectedCase={setSelectedCase}
                    openEntityModal={openEntityModal}
                    addToast={addToast}
                    theme={theme}
                  />
                )}
                {view === 'search' && (
                  <EntitySearchModule
                    openEntityModal={openEntityModal}
                    addToast={addToast}
                  />
                )}
                {view === 'path' && (
                  <ShortestPathModule
                    openEntityModal={openEntityModal}
                    addToast={addToast}
                  />
                )}
                {view === 'rankings' && (
                  <RankingsModule
                    cases={visibleCases}
                    openEntityModal={openEntityModal}
                    addToast={addToast}
                  />
                )}
                {view === 'insights' && (
                  <PatternInsightsModule
                    cases={visibleCases}
                    insights={insights}
                    setInsights={setInsights}
                    openAiDossier={openAiDossierModal}
                    addToast={addToast}
                  />
                )}
                {(view === 'blockchain' || view === 'timeline') && (
                  <IntegrityModule
                    cases={visibleCases}
                    fetchCases={fetchCases}
                    addToast={addToast}
                    officerSession={officerSession}
                    selectedCase={selectedCase}
                    onSelectCase={(cid) => setSelectedCase(cid)}
                    activeSection={view === 'timeline' ? 'timeline' : 'cases'}
                    onNavigateSection={(sec) => changeView(sec === 'timeline' ? 'timeline' : 'blockchain')}
                  />
                )}
                {view === 'cases' && (
                  <CaseRegistryModule
                    officerSession={officerSession}
                    loadStatus={caseLoadStatus}
                    hasLoaded={casesHaveLoaded}
                    openEntityModal={openEntityModal}
                    cases={visibleCases}
                    fetchCases={fetchCases}
                    selectedCase={selectedCase}
                    setSelectedCase={setSelectedCase}
                    openAiDossier={openAiDossierModal}
                    promptDeleteCase={promptDeleteCase}
                    changeView={changeView}
                    theme={theme}
                    addToast={addToast}
                  />
                )}
                {view === 'ingest' && (
                  <DataIngestionModule
                    officerSession={officerSession}
                    fetchCases={fetchCases}
                    changeView={changeView}
                    addToast={addToast}
                  />
                )}
                {view === 'board' && (
                  <InvestigationBoardModule
                    cases={visibleCases}
                    selectedCase={selectedCase}
                    onSelectCase={(cid) => setSelectedCase(cid)}
                    officerSession={officerSession}
                    addToast={addToast}
                    changeView={changeView}
                  />
                )}
                {view === 'reports' && (
                  <ReportsModule
                    cases={visibleCases}
                    selectedCase={selectedCase}
                    onSelectCase={(cid) => setSelectedCase(cid)}
                    officerSession={officerSession}
                    changeView={changeView}
                    addToast={addToast}
                  />
                )}
              </div>
            </main>
          </div>
        </div>
      </div>
    )}


      {/* Toast Notifications */}
      <div id="toasts" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type} ${t.out ? 'out' : ''}`}>{t.msg}</div>
        ))}
      </div>

      {/* Global Modal Overlay */}
      {modal && (
        <div
          className="modal-overlay open"
          onClick={(e: React.MouseEvent<HTMLDivElement>) => {
            if (e.target === e.currentTarget) setModal(null);
          }}
        >
          <div className={`modal ${modal.type === 'entity' ? 'entity-details-modal' : ''}`} role="dialog" aria-modal="true" aria-label="Record details">
            {modal.type === 'entity' && (
              <EntityModalContent
                data={modal.data as unknown as Entity}
                onClose={() => setModal(null)}
                openEntityModal={openEntityModal}
              />
            )}
            {modal.type === 'ai_dossier' && (
              <AiDossierModalContent
                caseId={String(modal.data?.caseId ?? '')}
                caseName={String(modal.data?.caseName ?? '')}
                onClose={() => setModal(null)}
              />
            )}
            {modal.type === 'reset_db' && (
              <ResetDbConfirmContent
                onClose={() => setModal(null)}
                addToast={addToast}
                onSuccess={() => {
                  fetchCases();
                  setInsights([]);
                  changeView('home');
                }}
              />
            )}
            {modal.type === 'delete_case' && (
              <DeleteCaseConfirmContent
                caseId={String(modal.data?.caseId ?? '')}
                caseName={String(modal.data?.caseName ?? '')}
                onClose={() => setModal(null)}
                addToast={addToast}
                officerBadge={officerSession?.badgeNumber}
                onSuccess={() => {
                  fetchCases();
                  if (selectedCase === modal.data?.caseId) setSelectedCase(null);
                }}
              />
            )}
          </div>
        </div>
      )}
    </React.Fragment>
  );
}
