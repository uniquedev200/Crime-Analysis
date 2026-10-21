import { useEffect, useRef } from 'react';
import { Case, HealthStatus, Insight, OfficerSession } from '../services/api';
import './landing.css';
import { LandingCaseCanvas } from './LandingCaseCanvas';
import { SmoothThemeToggle } from './SmoothThemeToggle';

export interface HomeModuleProps { theme: 'light' | 'dark'; setTheme: (theme: 'light' | 'dark') => void; cases: Case[]; health: HealthStatus | null; insights: Insight[]; officerSession: OfficerSession | null; setOfficerSession: (session: OfficerSession | null) => void; changeView: (view: string) => void; setSelectedCase: (id: string | null) => void; addToast: (msg: string, type?: string) => void; }

function AtlasMark() {
  return <svg className="atlas-mark" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M5 32 20 6l15 26M12 21h16M20 6v26" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>{[[20,6],[5,32],[35,32],[20,21]].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.5" fill="currentColor"/>)}</svg>;
}
function Arrow() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}
function ConnectionBackground() {
  return (
    <div className="atlas-evidence-background" aria-hidden="true">
      <div className="atlas-evidence-grid" />
      <svg className="atlas-evidence-traces" viewBox="0 0 1440 800" preserveAspectRatio="none" fill="none">
        {/* Left line: starts top-left (Y=180), wraps downward around left card (which is UP), ends at bottom (320, 530) */}
        <path d="M0 180H150Q180 180 180 210V500Q180 530 210 530H320" />
        <path className="atlas-evidence-signal" d="M0 180H150Q180 180 180 210V500Q180 530 210 530H320" />
        <circle cx="320" cy="530" r="4.5" />

        {/* Right line: REVERSED direction! starts at bottom-right (Y=620), wraps upward around right card (which is DOWN), ends at top (1120, 270) */}
        <path d="M1440 620H1290Q1260 620 1260 590V300Q1260 270 1230 270H1120" />
        <path className="atlas-evidence-signal" d="M1440 620H1290Q1260 620 1260 590V300Q1260 270 1230 270H1120" />
        <circle cx="1120" cy="270" r="4.5" />
      </svg>
      <div className="atlas-evidence-sheet atlas-evidence-sheet-left">
        <span>CASE RECORD</span>
        <i /><i /><i />
        <div className="atlas-evidence-seal">A</div>
      </div>
      <div className="atlas-evidence-sheet atlas-evidence-sheet-right">
        <span>CONNECTED EVIDENCE</span>
        <div className="atlas-evidence-bars">
          {[24, 40, 30, 58, 42, 66, 34, 48].map((height, i) => (
            <b key={i} style={{ height }} />
          ))}
        </div>
        <i /><i />
      </div>
    </div>
  );
}
function EvidenceIllustration() {
  return <div className="atlas-home-art evidence-art" role="img" aria-label="Layered case records brought together in one evidence workspace">
    <div className="record-sheet record-back"><span className="record-kicker">TRANSACTION RECORD</span><div className="record-line"/><div className="record-line short"/></div>
    <div className="record-sheet record-middle"><span className="record-kicker">COMMUNICATION LOG</span><div className="record-line"/><div className="record-line short"/></div>
    <div className="record-sheet record-front"><div className="record-top"><span className="record-kicker">CASE EVIDENCE</span><span className="record-dot"/></div><h3>Every detail.<br/>In context.</h3><div className="record-line"/><div className="record-line short"/><div className="record-rule"/>{['Witness statement','Transaction record','Communication log'].map((label,i) => <div className="record-file" key={label}><span>↳</span>{label}<span>0{i+1}</span></div>)}</div>
    <span className="art-caption"><span/> ONE CONNECTED WORKSPACE</span>
  </div>;
}
export function HomeModule({ changeView, officerSession, theme, setTheme }: HomeModuleProps) {
  const landingRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = landingRef.current;
    if (!root) return;
    const sections = Array.from(root.querySelectorAll<HTMLElement>('.atlas-scroll-pair > section'));
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    const measure = () => {
      const headerHeight = root.querySelector('header')?.getBoundingClientRect().height || 56;
      sections.forEach((section, index) => {
        // Tall sections scroll to their bottom before they pin, keeping every control reachable.
        section.style.setProperty('--stack-top', `${Math.min(headerHeight, window.innerHeight - section.offsetHeight)}px`);
        section.style.setProperty('--stack-order', String(index + 1));
      });
      root.classList.toggle('atlas-stacked-scroll', !preference.matches);
    };
    const update = () => {
      frame = 0;
      if (preference.matches) return;
      sections.forEach((section, index) => {
        const next = sections[index + 1];
        const progress = next ? Math.max(0, Math.min(1, 1 - next.getBoundingClientRect().top / window.innerHeight)) : 0;
        section.style.setProperty('--stack-scale', String(1 - progress * .025));
      });
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    const resize = new ResizeObserver(() => { measure(); onScroll(); });
    sections.forEach(section => resize.observe(section));
    measure(); update();
    window.addEventListener('scroll', onScroll, {passive: true});
    window.addEventListener('resize', measure);
    preference.addEventListener('change', measure);
    return () => {
      resize.disconnect(); cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', measure);
      preference.removeEventListener('change', measure);
      root.classList.remove('atlas-stacked-scroll');
      sections.forEach(section => ['--stack-top', '--stack-order', '--stack-scale'].forEach(key => section.style.removeProperty(key)));
    };
  }, []);
  useEffect(() => {
    const root = landingRef.current;
    if (!root || !('IntersectionObserver' in window)) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const targets = Array.from(root.querySelectorAll<HTMLElement>(
      '.atlas-home-section-intro, .atlas-home-feature-copy, .atlas-home-art, .atlas-home-workflow > .atlas-home-eyebrow, .atlas-home-workflow > h2, .atlas-timeline li, .atlas-home-footer'
    ));
    let observer: IntersectionObserver | undefined;
    const reset = () => {
      observer?.disconnect();
      targets.forEach(target => {
        target.classList.remove('atlas-scroll-reveal', 'atlas-scroll-visible');
        target.style.removeProperty('--reveal-delay');
      });
    };
    const setup = () => {
      reset();
      if (preference.matches) return;
      observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('atlas-scroll-visible');
          observer?.unobserve(entry.target);
        });
      }, { threshold: 0, rootMargin: '0px 0px -40px 0px' });
      targets.forEach(target => {
        // Already-visible content remains readable on load and when returning home.
        if (target.getBoundingClientRect().top < window.innerHeight - 40) return;
        const delay = target.matches('.atlas-timeline li')
          ? Array.from(target.parentElement!.children).indexOf(target) * 100
          : target.matches('.atlas-home-art') ? 90 : 0;
        target.style.setProperty('--reveal-delay', `${delay}ms`);
        target.classList.add('atlas-scroll-reveal');
        observer!.observe(target);
      });
    };
    setup();
    preference.addEventListener('change', setup);
    return () => {
      preference.removeEventListener('change', setup);
      reset();
    };
  }, []);
  const openWorkspace = () => changeView(officerSession ? 'overview' : 'auth');
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  return (
    <div className="atlas-landing" ref={landingRef}>
      <header className="atlas-home-header">
      <div className="atlas-header-left">
        <a className="atlas-home-brand" href="#home" aria-label="ATLAS home">
          <AtlasMark />
          <span>ATLAS</span>
        </a>
      </div>

      <nav className="atlas-header-center" aria-label="Primary navigation">
        <button type="button" onClick={() => scrollTo('capabilities')}>Capabilities</button>
        <button type="button" onClick={() => scrollTo('workflow')}>Workflow</button>
      </nav>

      <div className="atlas-header-right">
        <SmoothThemeToggle theme={theme} onToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')} />
        <button type="button" className="atlas-home-signin" onClick={openWorkspace}>
          {officerSession ? 'Workspace' : 'Sign in'}
          <Arrow />
        </button>
      </div>
    </header>
    <main id="main-content" tabIndex={-1}>
      <div className="atlas-scroll-pair"><section className="atlas-home-hero" aria-labelledby="atlas-home-title"><ConnectionBackground/><div className="atlas-home-hero-content"><span className="atlas-home-eyebrow">A CLEARER VIEW OF EVERY INVESTIGATION</span><h1 id="atlas-home-title">Uncover What<br/><span>Lies Between.</span></h1><p>Where Every Clue Finds Its Connection.</p><button className="atlas-home-button" onClick={openWorkspace}>Open workspace<Arrow/></button></div><button type="button" className="atlas-home-scroll" onClick={() => scrollTo('capabilities')} aria-label="Discover what connects"><span>DISCOVER WHAT CONNECTS</span><span>↓</span></button></section>
      <LandingCaseCanvas/></div>
      <section id="platform-overview" className="atlas-home-capabilities" aria-labelledby="capabilities-title"><div className="atlas-home-section-intro"><span className="atlas-home-eyebrow">THE DETAILS MAKE THE DIFFERENCE</span><h2 id="capabilities-title">Find clarity in the connections.</h2><p>From scattered evidence to a connected investigation.</p></div>
        <article className="atlas-home-feature atlas-home-platform-overview">
          <div className="atlas-home-feature-copy">
            <h2>Turn scattered evidence into connected intelligence.</h2>
            <p>ATLAS is an AI-powered criminal network analysis platform that helps police investigators make sense of information spread across FIRs, call records, financial transactions, vehicle records, and other case documents.</p>
            <p>It extracts key entities—such as people, phone numbers, accounts, and locations—and identifies potential matches across records, even when names or details vary. Interactive network graphs and timelines help officers explore relationships, trace events, and uncover connections between cases.</p>
            <p>Each finding links back to its supporting evidence, allowing officers to verify the information before drawing conclusions. ATLAS supports investigative judgment by making complex records easier to search, connect, and review.</p>
          </div>
          <EvidenceIllustration/>
        </article>
        <p className="atlas-home-illustration-note">Illustrations show example records and relationships.</p>
      </section>
      <section id="workflow" className="atlas-home-workflow" aria-labelledby="workflow-title">
        <span className="atlas-home-eyebrow">A CONNECTED WAY TO WORK</span>
        <h2 id="workflow-title">From the first record to the next lead.</h2>
        <div className="atlas-timeline-scroll" role="region" aria-label="Investigation workflow. Scroll horizontally on smaller screens." tabIndex={0}>
          <ol className="atlas-timeline">
            {[
              { number: '01', title: 'Gather evidence', description: 'Bring your case records into one workspace.' },
              { number: '02', title: 'Connect the clues', description: 'Find shared details across your investigations.' },
              { number: '03', title: 'Inspect the source', description: 'Follow each connection back to its evidence.' },
            ].map(step => <li key={step.number}>
              <span className="atlas-timeline-number">{step.number}</span>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </li>)}
          </ol>
        </div>
      </section>
    </main>
    <footer className="atlas-home-footer"><a className="atlas-home-brand" href="#home"><AtlasMark/><span>ATLAS</span></a><span>Investigation intelligence, connected.</span><nav aria-label="Footer navigation"><button onClick={() => scrollTo('capabilities')}>Capabilities</button><button onClick={() => scrollTo('workflow')}>Workflow</button><button onClick={openWorkspace}>{officerSession ? 'Workspace' : 'Sign in'}</button></nav></footer>
  </div>
  );
}



