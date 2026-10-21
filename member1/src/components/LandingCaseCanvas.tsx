import { useState } from 'react';
import './case-canvas.css';

export interface FeatureItem {
  id: number;
  name: string;
  title: string;
  description: string;
  pinX: number; // percentage
  pinY: number; // percentage
  hubLabel: string;
}

const features: FeatureItem[] = [
  {
    id: 1,
    name: 'Unified Evidence Intelligence',
    title: '1. Unified Evidence Intelligence',
    description: 'Transform fragmented FIRs, call records, financial data, and investigation reports into structured, connected intelligence.',
    pinX: 18,
    pinY: 30,
    hubLabel: 'Intake & Document Synthesis',
  },
  {
    id: 2,
    name: 'Hidden Network Discovery',
    title: '2. Hidden Network Discovery',
    description: 'Reveal evidence-backed relationships between people, phone numbers, vehicles, accounts, and investigations.',
    pinX: 45,
    pinY: 24,
    hubLabel: 'Entity Resolution & Graph Core',
  },
  {
    id: 3,
    name: 'Intelligent Pattern Detection',
    title: '3. Intelligent Pattern Detection',
    description: 'Identify unusual communication patterns, influential entities, and potential connections across cases.',
    pinX: 63,
    pinY: 38,
    hubLabel: 'Cross-Corridor Pattern Analysis',
  },
  {
    id: 4,
    name: 'Trusted Evidence Integrity',
    title: '4. Trusted Evidence Integrity',
    description: 'Protect investigation records with cryptographic verification, traceable custody history, and accountable access logs.',
    pinX: 83,
    pinY: 26,
    hubLabel: 'Cryptographic Ledger & Audit',
  },
];

/* SVG icons matching platform core capabilities */
function UnifiedEvidenceIcon() {
  return (
    <svg className="atlas-kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="13" height="13" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  );
}

function HiddenNetworkIcon() {
  return (
    <svg className="atlas-kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="19" r="2.5" />
      <circle cx="19" cy="19" r="2.5" />
      <path d="M12 7.5V13m0 0H5v3.5m7-3.5h7v3.5" />
    </svg>
  );
}

function PatternDetectionIcon() {
  return (
    <svg className="atlas-kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EvidenceIntegrityIcon() {
  return (
    <svg className="atlas-kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

const FEATURE_ICONS = [
  UnifiedEvidenceIcon,
  HiddenNetworkIcon,
  PatternDetectionIcon,
  EvidenceIntegrityIcon,
];

export function LandingCaseCanvas() {
  const [selectedId, setSelectedId] = useState<number>(1);
  const [zoom, setZoom] = useState<number>(1);

  return (
    <section id="capabilities" className="atlas-case-section fullwidth" aria-labelledby="case-canvas-title">
      <div className="atlas-case-intro atlas-home-section-intro">
        <span className="atlas-home-eyebrow">EXPLORE THE ARCHITECTURE</span>
        <h2 id="case-canvas-title">Find clarity in the connections.</h2>
        <p>From fragmented records to unified, evidence-backed criminal network intelligence.</p>
      </div>

      {/* Full-width Edge-to-Edge Canvas (No enclosing box, 100% full screen width) */}
      <div className="atlas-fullwidth-canvas-wrapper">
        <div
          className="atlas-fullwidth-map-viewport"
          role="region"
          aria-label="Interactive ATLAS Network Map with 4 feature points"
          tabIndex={0}
        >
          {/* Scalable Map Scene */}
          <div
            className="atlas-map-scene"
            style={{ transform: `scale(${zoom})` }}
          >
            <img
              src="/background_image.png"
              alt="ATLAS National Intelligence Surface Map"
              className="atlas-map-fullwidth-img"
            />

            {/* Connecting laser traces between the 4 points */}
            <svg className="atlas-map-traces" viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
              <line
                x1={features[0].pinX * 10}
                y1={features[0].pinY * 5}
                x2={features[1].pinX * 10}
                y2={features[1].pinY * 5}
                className={selectedId === 1 || selectedId === 2 ? 'is-active-trace' : ''}
              />
              <line
                x1={features[1].pinX * 10}
                y1={features[1].pinY * 5}
                x2={features[2].pinX * 10}
                y2={features[2].pinY * 5}
                className={selectedId === 2 || selectedId === 3 ? 'is-active-trace' : ''}
              />
              <line
                x1={features[2].pinX * 10}
                y1={features[2].pinY * 5}
                x2={features[3].pinX * 10}
                y2={features[3].pinY * 5}
                className={selectedId === 3 || selectedId === 4 ? 'is-active-trace' : ''}
              />
            </svg>

            {/* 4 Feature Points on the Full-Width Image */}
            {features.map((feature, idx) => {
              const IconComponent = FEATURE_ICONS[idx];
              const isSelected = selectedId === feature.id;
              return (
                <button
                  key={feature.id}
                  type="button"
                  className={`atlas-feature-point-pin ${isSelected ? 'is-selected' : ''}`}
                  style={{ left: `${feature.pinX}%`, top: `${feature.pinY}%` }}
                  onClick={() => setSelectedId(feature.id)}
                  aria-label={`Feature ${feature.id}: ${feature.name}`}
                  aria-pressed={isSelected}
                >
                  <span className="atlas-pin-radar-ring" />
                  <span className="atlas-pin-radar-ring delay" />
                  <span className="atlas-pin-core">
                    <span className="atlas-pin-number">{feature.id}</span>
                  </span>
                  <span className="atlas-pin-label-chip">
                    <IconComponent />
                    <span>{feature.name}</span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Top Status Banner & Zoom Overlay */}
          <div className="atlas-map-top-bar-overlay">
            <div className="atlas-map-live-status">
              <span className="pulse-dot" />
              <span className="status-title">ATLAS INTELLIGENCE NETWORK</span>
              <span className="status-separator">·</span>
              <span className="status-highlight">National Surface Architecture</span>
            </div>
            <div className="atlas-case-zoom" aria-label="Map zoom controls">
              <button
                type="button"
                onClick={() => setZoom(val => Math.min(1.3, +(val + 0.1).toFixed(1)))}
                disabled={zoom >= 1.3}
                aria-label="Zoom in"
              >
                +
              </button>
              <button
                type="button"
                onClick={() => setZoom(1)}
                aria-label="Reset map zoom"
              >
                Reset
              </button>
              <button
                type="button"
                onClick={() => setZoom(val => Math.max(0.85, +(val - 0.1).toFixed(1)))}
                disabled={zoom <= 0.85}
                aria-label="Zoom out"
              >
                −
              </button>
            </div>
          </div>

          {/* 4 SEPARATE KPI CARDS (NOT IN A SINGLE BOX) */}
          <div className="atlas-kpi-cards-container" aria-label="Core Capability KPI Cards">
            <div className="atlas-kpi-cards-grid">
              {features.map((feature, idx) => {
                const IconComponent = FEATURE_ICONS[idx];
                const isSelected = selectedId === feature.id;
                return (
                  <div
                    key={feature.id}
                    className={`atlas-kpi-card ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedId(feature.id)}
                    onMouseEnter={() => setSelectedId(feature.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedId(feature.id);
                      }
                    }}
                    aria-pressed={isSelected}
                  >
                    <div className="atlas-kpi-card-header">
                      <span className="atlas-kpi-badge">0{feature.id}</span>
                      <div className="atlas-kpi-icon-wrap">
                        <IconComponent />
                      </div>
                    </div>

                    <div className="atlas-kpi-card-body">
                      <h3 className="atlas-kpi-title">{feature.name}</h3>
                      <p className="atlas-kpi-desc">{feature.description}</p>
                    </div>

                    <div className="atlas-kpi-card-footer">
                      <span className="atlas-kpi-hub-tag">
                        <span className="atlas-kpi-status-dot" />
                        {feature.hubLabel}
                      </span>
                      <span className="atlas-kpi-arrow">→</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <p className="atlas-case-note">
        ATLAS integrates multimodal intelligence across jurisdictions with automated entity resolution and verifiable cryptographic custody.
      </p>
    </section>
  );
}
