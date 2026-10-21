import React, { useState } from 'react';
import { API, OfficerSession, ThemeMode } from '../services/api';
import './auth.css';
import { SmoothThemeToggle } from './SmoothThemeToggle';

export interface AuthModuleProps {
  setOfficerSession: (session: OfficerSession | null) => void;
  changeView: (view: string) => void;
  addToast: (msg: string, type?: string) => void;
  onClose?: () => void;
  isModal?: boolean;
  theme?: ThemeMode;
  toggleTheme?: () => void;
}

// Temporary until the email verification service is implemented.
const REQUIRE_EMAIL_VERIFICATION = false;
type Screen = 'signin' | 'register' | 'verify' | 'forgot';
function Eye({ visible }: { visible: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>{visible && <path d="m3 3 18 18"/>}</svg>;
}
function AuthBrandMark() {
  return <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M5 32 20 6l15 26M12 21h16M20 6v26" stroke="currentColor" strokeWidth="1.6"/>{[[20,6],[5,32],[35,32],[20,21]].map(([x,y]) => <circle key={x + '-' + y} cx={x} cy={y} r="2.5" fill="currentColor"/>)}</svg>;
}
function PasswordField({ id, label, value, onChange, autoComplete }: {
  id: string; label: string; value: string; onChange: (value: string) => void; autoComplete: string;
}) {
  const [visible, setVisible] = useState(false);
  return <div className="atlas-auth-field"><label htmlFor={id}>{label}</label><div className="atlas-auth-password">
    <input id={id} type={visible ? 'text' : 'password'} autoComplete={autoComplete} value={value} onChange={e => onChange(e.target.value)} required minLength={autoComplete === 'new-password' ? 8 : undefined} placeholder={label === 'Confirm password' ? 'Re-enter your password' : 'Enter your password'}/>
    <button type="button" aria-label={visible ? 'Hide ' + label.toLowerCase() : 'Show ' + label.toLowerCase()} aria-pressed={visible} aria-controls={id} onClick={() => setVisible(!visible)}><Eye visible={visible}/></button>
  </div></div>;
}

export function AuthModule({ setOfficerSession, changeView, addToast, onClose, isModal = false, theme, toggleTheme }: AuthModuleProps) {
  const [screen, setScreen] = useState<Screen>('signin');
  const [officerName, setOfficerName] = useState('');
  const [badgeId, setBadgeId] = useState('');
  const [email, setEmail] = useState('');
  const [unit, setUnit] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const isRegister = screen === 'register';
  const isVerify = screen === 'verify';

  const go = (next: Screen) => {
    setScreen(next); setError(null); setNotice(''); setCode('');
    if (next === 'signin' || next === 'forgot') { setPassword(''); setConfirmPassword(''); }
    requestAnimationFrame(() => document.getElementById('auth-title')?.focus());
  };
  const navigateToSection = (id: string) => {
    changeView('home');
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'
    })));
  };
  // Temporary local workspace access while account verification is being built.
  const demoLogin = () => {
    if (busy) return;
    setOfficerSession({
      isDemo: true,
      badgeNumber: 'ATLAS-DEMO',
      officerName: 'Demo Officer',
      department: 'Demo workspace',
      clearanceLevel: 'Demo access',
      signedInAt: new Date().toISOString(),
    });
    setPassword(''); setConfirmPassword(''); setError(null);
    onClose?.();
    changeView('overview');
    addToast('Demo workspace opened.', 'ok');
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (isRegister) {
      if (![officerName, badgeId, email, unit].every(value => value.trim())) { setError('Complete all officer details.'); return; }
      if (password !== confirmPassword) { setError('The passwords do not match. Please enter them again.'); return; }
      if (REQUIRE_EMAIL_VERIFICATION) { go('verify'); return; }
    }
    if (isVerify) {
      setError('Email verification is not available yet. Your account has not been created.');
      return;
    }
    if (!badgeId.trim()) { setError('Enter your officer ID.'); return; }
    setBusy(true);
    try {
      const response = await API.post<{ success: boolean; session: OfficerSession }>(
        isRegister ? '/api/auth/signup' : '/api/auth/login',
        isRegister
          ? { officerName: officerName.trim(), badgeNumber: badgeId.trim(), password, department: unit.trim(), unit: unit.trim() }
          : { badgeNumber: badgeId.trim(), password }
      );
      if (!response?.success || !response.session?.badgeNumber) throw new Error(isRegister ? 'Account creation was not confirmed. Please try again.' : 'Sign-in was not confirmed. Please try again.');
      setOfficerSession({ ...response.session, isDemo: false });
      setPassword(''); setConfirmPassword('');
      addToast(isRegister ? 'Account created successfully.' : 'Signed in successfully.', 'ok'); onClose?.(); changeView('overview');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : (isRegister ? 'Unable to create your account. Please try again.' : 'Unable to sign in. Please try again.'));
    } finally { setBusy(false); }
  };
  const title = { signin: 'Sign in to ATLAS', register: 'Create your account', verify: 'Verify your email', forgot: 'Forgot your password?' }[screen];
  const description = {
    signin: 'Access your cases and connected evidence.',
    register: 'Enter your officer details to get started.',
    verify: 'Confirm your official email before creating your account.',
    forgot: 'Get help accessing your officer account.'
  }[screen];

  const content = <section className="atlas-auth-card" aria-labelledby="auth-title">
    <div className="auth-card-emblem"><AuthBrandMark/></div>
    <h1 id="auth-title" tabIndex={-1}>{title}</h1>
    <p className="atlas-auth-description">{description}</p>
    {REQUIRE_EMAIL_VERIFICATION && (isRegister || isVerify) && <ol className="auth-progress" aria-label="Account creation progress">
      <li aria-current={isRegister ? 'step' : undefined}><span>{isVerify ? '✓' : '1'}</span> Officer details</li>
      <li aria-current={isVerify ? 'step' : undefined}><span>2</span> Verify email</li>
    </ol>}
    {screen === 'forgot' ? <>
      <div className="auth-service-note" role="status">Password recovery is not available yet. Contact your ATLAS administrator for help with your account.</div>
      <button type="button" className="atlas-auth-submit atlas-auth-submit-compact" onClick={() => go('signin')}>Return to sign in</button>
    </> : <form onSubmit={submit}>
      <fieldset className="atlas-auth-fields" disabled={busy}>
        {screen === 'signin' && <>
          <div className="atlas-auth-field"><label htmlFor="officer-badge">Officer ID</label><input id="officer-badge" autoComplete="username" autoCapitalize="none" spellCheck={false} value={badgeId} onChange={e => setBadgeId(e.target.value)} maxLength={100} placeholder="Enter your officer ID" required/></div>
          <PasswordField key="login-password" id="officer-password" label="Password" value={password} onChange={setPassword} autoComplete="current-password"/>
        </>}
        {isRegister && <>
          <div className="atlas-auth-field"><label htmlFor="officer-name">Full name</label><input id="officer-name" autoComplete="name" value={officerName} onChange={e => setOfficerName(e.target.value)} maxLength={150} placeholder="Enter your full name" required/></div>
          <div className="atlas-auth-field"><label htmlFor="officer-service-id">Officer ID</label><input id="officer-service-id" autoComplete="username" autoCapitalize="none" spellCheck={false} value={badgeId} onChange={e => setBadgeId(e.target.value)} maxLength={100} placeholder="Department-issued ID" required/></div>
          <div className="atlas-auth-field"><label htmlFor="officer-email">Official email</label><input id="officer-email" type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} value={email} onChange={e => setEmail(e.target.value)} maxLength={254} placeholder="you@department.gov.in" required/></div>
          <div className="atlas-auth-field"><label htmlFor="officer-unit">Police unit / station</label><input id="officer-unit" autoComplete="organization" value={unit} onChange={e => setUnit(e.target.value)} maxLength={150} placeholder="Enter your unit or station" required/></div>
          <PasswordField key="new-password" id="officer-new-password" label="Password" value={password} onChange={setPassword} autoComplete="new-password"/>
          <PasswordField id="officer-confirm-password" label="Confirm password" value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password"/>
        </>}
        {isVerify && <>
          <div className="auth-email-summary"><span>Official email</span><strong>{email}</strong><button type="button" className="auth-text-link" onClick={() => go('register')}>Change email</button></div>
          <div className="atlas-auth-field"><label htmlFor="officer-otp">Six-digit verification code</label><input className="auth-otp" id="officer-otp" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0,6))} placeholder="000000" aria-describedby="otp-service-status" required/></div>
          <div className="auth-service-note" id="otp-service-status">Email verification is not connected yet. No code has been sent, and your account has not been created.</div>
        </>}
      </fieldset>
      {screen === 'signin' && <div className="auth-recovery"><button type="button" className="auth-text-link" disabled={busy} onClick={() => go('forgot')}>Forgot password?</button></div>}
      {isRegister && <p className="auth-field-hint">Use at least 8 characters for your password.</p>}
      {error && <div className="atlas-auth-error" role="alert">{error}</div>}
      <button type="submit" disabled={busy || isVerify} aria-describedby={isVerify ? 'otp-service-status' : undefined} aria-busy={busy} className="atlas-auth-submit atlas-auth-submit-compact">{busy ? (isRegister ? 'Creating account…' : 'Signing in…') : isVerify ? 'Verify and create account' : isRegister ? (REQUIRE_EMAIL_VERIFICATION ? 'Verify email' : 'Create account') : 'Sign in'}<span aria-hidden="true">→</span></button>
      {isVerify && <div className="auth-resend"><button type="button" className="auth-text-link" onClick={() => setNotice('A new code cannot be sent until email verification is connected.')}>Resend code</button><p role="status">{notice}</p></div>}
    </form>}
    <button type="button" className="atlas-auth-submit atlas-auth-submit-compact auth-demo-login" disabled={busy} onClick={demoLogin}>Demo login<span aria-hidden="true">→</span></button>
    {screen !== 'forgot' && <p className="auth-account-link">{screen === 'signin' ? 'New to ATLAS? ' : 'Already have an account? '}<button type="button" className="auth-text-link" disabled={busy} onClick={() => go(screen === 'signin' ? 'register' : 'signin')}>{screen === 'signin' ? 'Create account' : 'Sign in'}</button></p>}
    {isModal && onClose && <button type="button" className="atlas-auth-back" disabled={busy} onClick={onClose}>Close</button>}
  </section>;

  const className = 'atlas-auth auth-flow-v2' + (isRegister ? ' atlas-auth-register' : '');
  if (isModal) return <div className={className + ' atlas-auth-modal'}>{content}</div>;
  return <div className={className}>
    <header className="atlas-auth-navbar">
      <button className="atlas-auth-nav-brand" disabled={busy} onClick={() => changeView('home')} aria-label="ATLAS home"><AuthBrandMark/><span>ATLAS</span></button>
      <nav aria-label="Main navigation">
        {toggleTheme && theme && (
          <SmoothThemeToggle theme={theme} onToggle={toggleTheme} />
        )}
        <button disabled={busy} onClick={() => navigateToSection('capabilities')}>Capabilities</button>
        <button disabled={busy} onClick={() => navigateToSection('workflow')}>Workflow</button>
        <button className="atlas-auth-nav-signin" disabled={busy} onClick={() => go('signin')}>Sign in <span aria-hidden="true">→</span></button>
      </nav>
    </header>
    <main className="atlas-auth-main" id="main-content">{content}<p className="atlas-auth-bottom">ATLAS · Connected investigation workspace</p></main>
  </div>;
}
