import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { NAV, TITLES, HealthStatus, OfficerSession, ThemeMode } from '../services/api';
import { SmoothThemeToggle } from './SmoothThemeToggle';

const sections = [
  { label: 'Workspace', ids: ['overview', 'cases', 'ingest'], icon: 'M3 7h18v13H3zM3 7l3-3h5l2 3M8 12h8M8 16h5' },
  { label: 'Investigate', ids: ['graph', 'search', 'path', 'rankings'], icon: 'M9 5a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm14 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM7 8l9 7M5 9v10h10' },
  { label: 'Investigation Board', ids: ['board'], icon: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2' },
  { label: 'Reports', ids: ['reports'], icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
  { label: 'Integrity', ids: ['blockchain', 'timeline'], icon: 'M12 3 3 7v5c0 5 4 8 9 10 5-2 9-5 9-10V7zM8 12l3 3 5-6' },
];
function Icon({ path }: { path: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path}/></svg>;
}
function Mark() {
  return <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M5 32 20 6l15 26M12 21h16M20 6v26" stroke="currentColor" strokeWidth="1.6"/>{[[20,6],[5,32],[35,32],[20,21]].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.5" fill="currentColor"/>)}</svg>;
}
function ThemeIcon({ theme }: { theme: 'light' | 'dark' }) {
  if (theme === 'dark') {
    return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>;
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 15A8.5 8.5 0 0 1 9 4a8.5 8.5 0 1 0 11 11Z"/></svg>;
}
export function TopHeader({ view, health, officerSession, setOfficerSession, changeView, addToast, theme, toggleTheme }: { view: string; health: HealthStatus | null; officerSession: OfficerSession | null; setOfficerSession?: React.Dispatch<React.SetStateAction<OfficerSession | null>>; changeView: (id: string) => void; addToast?: (msg: string, type?: string) => void; theme?: ThemeMode; toggleTheme?: () => void }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => { if (!menuRef.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', dismiss); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape); };
  }, [open]);
  return <header className="app-top-header">
    <button className="workspace-logo" onClick={() => changeView('home')} aria-label="ATLAS home"><Mark/></button>
    <WorkspaceTabs view={view} changeView={changeView}/>
    <span className="workspace-environment"><span className="workspace-status-dot"/>{officerSession?.isDemo ? 'Frontend preview' : health?.status === 'healthy' ? 'Services connected' : 'Offline workspace'}</span>
    {toggleTheme && theme && (
      <SmoothThemeToggle theme={theme} onToggle={toggleTheme} />
    )}
    <div className="profile-wrap" ref={menuRef}><button className="profile-button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="workspace-profile-menu" aria-label={`Account: ${officerSession?.officerName || 'Preview'}`}><span className="profile-avatar">{(officerSession?.officerName || 'Preview').slice(0,2).toUpperCase()}</span></button>
      {open && <div className="profile-menu" id="workspace-profile-menu"><div className="workspace-profile-details"><strong>{officerSession?.officerName || 'Interface preview'}</strong><span>{officerSession?.department || 'Officer workspace'}</span></div>{toggleTheme && theme && <button className="profile-menu-theme-btn" onClick={() => { toggleTheme(); setOpen(false); }}><ThemeIcon theme={theme}/><span>Switch to {theme === 'dark' ? 'Light' : 'Dark'} theme</span></button>}<button onClick={() => { setOpen(false); changeView('auth'); }}>Officer sign in</button>{officerSession && <button onClick={() => { setOfficerSession?.(null); localStorage.removeItem('atlas_officer_session'); setOpen(false); changeView('home'); addToast?.('Signed out', 'info'); }}>Sign out</button>}<button onClick={() => { setOpen(false); changeView('home'); }}>Home</button></div>}
    </div>
  </header>;
}
export function Sidebar({ view, changeView }: { view: string; changeView: (id: string) => void }) {
  return <aside className="app-sidebar"><nav aria-label="Workspace sections">{sections.map(section => {
    const active = section.ids.includes(view);
    return <button className={`workspace-rail-item ${active ? 'active' : ''}`} key={section.label} aria-current={active ? 'page' : undefined} title={section.label} onClick={() => changeView(section.ids[0])}><span className="workspace-rail-icon"><Icon path={section.icon}/></span><span>{section.label}</span></button>;
  })}</nav><button className="workspace-rail-item workspace-rail-home" onClick={() => changeView('home')}><span className="workspace-rail-icon"><Icon path="m3 10 9-7 9 7v11h-7v-7h-4v7H3z"/></span><span>Home</span></button></aside>;
}
export function WorkspaceTabs({ view, changeView }: { view: string; changeView: (id: string) => void }) {
  const section = sections.find(item => item.ids.includes(view)) || sections[0];
  const activeRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const [marker, setMarker] = useState({left:0,width:0});
  useLayoutEffect(() => {
    const measure = () => { const button=activeRef.current; if(button) setMarker({left:button.offsetLeft,width:button.offsetWidth}); };
    measure(); const observer=new ResizeObserver(measure);
    if(navRef.current) observer.observe(navRef.current);
    if(activeRef.current) observer.observe(activeRef.current);
    return () => observer.disconnect();
  }, [view]);
  useEffect(() => { activeRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }, [view]);
  return <nav ref={navRef} className="workspace-tabs" aria-label={`${section.label} tools`}><span className="workspace-tab-marker" aria-hidden="true" style={{width:marker.width,transform:`translateX(${marker.left}px)`}}/>{section.ids.map(id => {
    const item = NAV.find(entry => entry.id === id)!;
    return <button ref={view === id ? activeRef : undefined} key={id} className={view === id ? 'active' : ''} aria-current={view === id ? 'page' : undefined} onClick={() => changeView(id)}><Icon path={item.icon}/>{item.label}</button>;
  })}</nav>;
}
export function Topbar({ view }: { view: string; health?: HealthStatus | null; theme?: string; toggleTheme?: () => void; officerSession?: OfficerSession | null; changeView?: (id: string) => void; setSidebarOpen?: (open: boolean | ((prev: boolean) => boolean)) => void }) { return <div className="view-banner"><h1>{TITLES[view]?.[0]}</h1><p>{TITLES[view]?.[1]}</p></div>; }
