import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import * as vis from 'vis-network/standalone';
import { API, esc, LABEL_COLOR, getNodeLevel, getDeterministicSeed, Case, GraphNode, GraphEdge, AiChatMessage, ThemeMode } from '../services/api';
import { FormattedAiMessage } from './FormattedAiMessage';
import { EntityPropertiesTable } from './EntityPropertiesTable';
import { WorkspaceDetails } from './WorkspaceDetails';

function GraphControlIcon({ kind }: { kind: string }) {
  const paths: Record<string, string> = {
    copilot: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',
    fit: 'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M8 8h8v8H8Z',
    expand: 'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M4 4l5 5M20 4l-5 5M20 20l-5-5M4 20l5-5',
    compress: 'M4 14h6v6M10 14l-7 7M20 10h-6V4M14 10l7-7',
    reset: 'M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5',
    focus: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM3 12h3M18 12h3M12 3v3M12 18v3',
    plus_circle: 'M12 8v8M8 12h8M12 22A10 10 0 1 0 12 2a10 10 0 0 0 0 20Z',
    up: 'm6 14 6-6 6 6', down: 'm6 10 6 6 6-6', left: 'm14 6-6 6 6 6', right: 'm10 6 6 6-6 6',
    plus: 'M5 12h14M12 5v14', minus: 'M5 12h14',
    chevron_left: 'm15 18-6-6 6-6',
    sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
    labels: 'M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82zM7 7h.01',
    legend: 'M4 6h.01M9 6h11M4 12h.01M9 12h11M4 18h.01M9 18h11'
  };
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[kind] || paths.fit} />
    </svg>
  );
}

export type EntityCategory =
  | 'Person'
  | 'Phone'
  | 'Device'
  | 'Vehicle'
  | 'Account'
  | 'Location'
  | 'Organization'
  | 'Evidence'
  | 'Case';

export function getEntityCategory(labels: string[] = []): EntityCategory {
  if (labels.includes('Person')) return 'Person';
  if (labels.includes('Organization') || labels.includes('Company')) return 'Organization';
  if (labels.includes('Phone') || labels.includes('PhoneNumber')) return 'Phone';
  if (labels.includes('Device') || labels.includes('IMEI') || labels.includes('Exhibit')) return 'Device';
  if (labels.includes('Vehicle')) return 'Vehicle';
  if (labels.includes('BankAccount') || labels.includes('Account') || labels.includes('Transaction')) return 'Account';
  if (labels.includes('Location') || labels.includes('CellTower') || labels.includes('Address')) return 'Location';
  if (labels.includes('Case')) return 'Case';
  if (labels.includes('Evidence') || labels.includes('SourceRecord') || labels.includes('Document')) return 'Evidence';
  return 'Person';
}

// Consistent ATLAS entity color system matching forensic specification
export function getNodePalette(category: EntityCategory, isLight: boolean) {
  switch (category) {
    case 'Person':
      // Person / Suspects → Sky Blue (#92C5FC in light, #3B82F6 in dark)
      return isLight
        ? { bg: '#92C5FC', border: '#2563EB', ring: 'rgba(37, 99, 235, 0.45)' }
        : { bg: '#3B82F6', border: '#60A5FA', ring: 'rgba(59, 130, 246, 0.45)' };
    case 'Account':
      // Bank accounts / Financial → Soft Lavender (#EAD5FE in light, #A78BFA in dark)
      return isLight
        ? { bg: '#EAD5FE', border: '#7C3AED', ring: 'rgba(124, 58, 237, 0.45)' }
        : { bg: '#A78BFA', border: '#C084FC', ring: 'rgba(167, 139, 250, 0.45)' };
    case 'Phone':
      // Phone numbers / Telecom → Warm Orange (#FDBA74 in light, #F97316 in dark)
      return isLight
        ? { bg: '#FDBA74', border: '#EA580C', ring: 'rgba(234, 88, 12, 0.45)' }
        : { bg: '#F97316', border: '#FB923C', ring: 'rgba(249, 115, 22, 0.45)' };
    case 'Vehicle':
      // Vehicles → Soft Pink (#FBCFE8 in light, #EC4899 in dark)
      return isLight
        ? { bg: '#FBCFE8', border: '#DB2777', ring: 'rgba(219, 39, 119, 0.45)' }
        : { bg: '#EC4899', border: '#F472B6', ring: 'rgba(236, 72, 153, 0.45)' };
    case 'Device':
      // Devices / IMEI → Soft Blue (#BAE6FD in light, #0284C7 in dark)
      return isLight
        ? { bg: '#BAE6FD', border: '#0284C7', ring: 'rgba(2, 132, 199, 0.45)' }
        : { bg: '#0284C7', border: '#38BDF8', ring: 'rgba(2, 132, 199, 0.45)' };
    case 'Location':
      // Locations / towers → Lime Green (#D9F99D in light, #84CC16 in dark)
      return isLight
        ? { bg: '#D9F99D', border: '#65A30D', ring: 'rgba(101, 163, 13, 0.45)' }
        : { bg: '#84CC16', border: '#A3E635', ring: 'rgba(132, 204, 22, 0.45)' };
    case 'Organization':
      // Organization / company → Warm Amber (#FEF3C7 in light, #F59E0B in dark)
      return isLight
        ? { bg: '#FEF3C7', border: '#D97706', ring: 'rgba(217, 119, 6, 0.45)' }
        : { bg: '#F59E0B', border: '#FBBF24', ring: 'rgba(245, 158, 11, 0.45)' };
    case 'Evidence':
      // Evidence / documents / exhibits → Slate Gray
      return isLight
        ? { bg: '#E2E8F0', border: '#64748B', ring: 'rgba(100, 116, 139, 0.45)' }
        : { bg: '#334155', border: '#475569', ring: 'rgba(51, 65, 85, 0.45)' };
    case 'Case':
      // Case node → Indigo (#E0E7FF in light, #6366F1 in dark)
      return isLight
        ? { bg: '#E0E7FF', border: '#4F46E5', ring: 'rgba(79, 70, 229, 0.45)' }
        : { bg: '#6366F1', border: '#818CF8', ring: 'rgba(99, 102, 241, 0.45)' };
    default:
      return isLight
        ? { bg: '#E2E8F0', border: '#64748B', ring: 'rgba(100, 116, 139, 0.45)' }
        : { bg: '#64748B', border: '#94A3B8', ring: 'rgba(100, 116, 139, 0.45)' };
  }
}

// Inner SVG paths for all 9 categories (centered in 24x24 viewBox)
export const ENTITY_ICON_INNER_SVGS: Record<EntityCategory, string> = {
  Person: '<circle cx="12" cy="7" r="4.2" stroke="white" stroke-width="2" fill="none"/><path d="M4 21v-1.5a6.5 6.5 0 0 1 13 0v1.5" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>',
  Phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  Device: '<rect x="5.5" y="2.5" width="13" height="19" rx="2.5" stroke="white" stroke-width="2" fill="none"/><line x1="12" y1="17.5" x2="12.01" y2="17.5" stroke="white" stroke-width="2.5" stroke-linecap="round"/>',
  Vehicle: '<path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><rect x="3" y="11" width="18" height="6.5" rx="2" stroke="white" stroke-width="2" fill="none"/><circle cx="7" cy="14.2" r="1.2" fill="white"/><circle cx="17" cy="14.2" r="1.2" fill="white"/><path d="M5 17.5v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2M16 17.5v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2" stroke="white" stroke-width="1.8" stroke-linecap="round" fill="none"/>',
  Account: '<polygon points="3 8 12 3 21 8" stroke="white" stroke-width="1.8" fill="none" stroke-linejoin="round"/><line x1="6" y1="10" x2="6" y2="17" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="10" x2="12" y2="17" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="18" y1="10" x2="18" y2="17" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="17" x2="21" y2="17" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="2" y1="20" x2="22" y2="20" stroke="white" stroke-width="2" stroke-linecap="round"/>',
  Location: '<path d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7z" stroke="white" stroke-width="2" fill="none"/><circle cx="12" cy="9" r="2.5" stroke="white" stroke-width="2" fill="none"/>',
  Organization: '<path d="M4 21V6a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v15" stroke="white" stroke-width="2" stroke-linejoin="round" fill="none"/><path d="M12 21V11a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v10" stroke="white" stroke-width="2" stroke-linejoin="round" fill="none"/><line x1="2" y1="21" x2="22" y2="21" stroke="white" stroke-width="2" stroke-linecap="round"/>',
  Evidence: '<rect x="5" y="3" width="14" height="18" rx="2.5" stroke="white" stroke-width="2" fill="none"/><line x1="8.5" y1="8" x2="15.5" y2="8" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="8.5" y1="12" x2="15.5" y2="12" stroke="white" stroke-width="2" stroke-linecap="round"/><line x1="8.5" y1="16" x2="12.5" y2="16" stroke="white" stroke-width="2" stroke-linecap="round"/>',
  Case: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" stroke="white" stroke-width="2" stroke-linejoin="round" fill="none"/>'
};

const svgDataUriCache = new Map<EntityCategory, string>();

export function getEntityIconDataUri(category: EntityCategory): string {
  if (svgDataUriCache.has(category)) return svgDataUriCache.get(category)!;
  const innerSvg = ENTITY_ICON_INNER_SVGS[category] || ENTITY_ICON_INNER_SVGS.Person;
  // ViewBox -8 -8 40 40 gives an 8px margin around 24x24 icon so the white icon sits neatly inside the circle
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="-8 -8 40 40">${innerSvg}</svg>`;
  const uri = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  svgDataUriCache.set(category, uri);
  return uri;
}

export function truncateName(text: string, maxLen: number): string {
  const clean = text.replace(/\n+/g, ' ').trim();
  if (clean.length <= maxLen) return clean;
  return `${clean.slice(0, maxLen - 1)}…`;
}

export function abbreviatePersonName(name: string, maxLen: number): string {
  const clean = name.replace(/\n+/g, ' ').trim();
  if (clean.length <= maxLen) return clean;
  const parts = clean.split(/\s+/);
  if (parts.length > 1) {
    const first = parts[0];
    const lastInitial = `${parts[parts.length - 1][0]}.`;
    const candidate = `${first} ${lastInitial}`;
    if (candidate.length <= maxLen) return candidate;
  }
  return `${clean.slice(0, maxLen - 1)}…`;
}

// Clean, abbreviated display labels formatted specifically for canvas nodes
export function formatDisplayLabel(node: GraphNode, category: EntityCategory): string {
  const rawName = String(node.name || node.properties?.name || '').trim();
  const rawId = String(node.id || '').trim();

  if (category === 'Phone') {
    const rawNum = String(node.properties?.phone_number || rawName || rawId).replace(/[^\d+]/g, '');
    if (rawNum.length >= 8) {
      // Formats as 9100…0101 exactly matching reference
      const start = rawNum.startsWith('+') ? rawNum.slice(0, 5) : rawNum.slice(0, 4);
      const end = rawNum.slice(-4);
      return `${start}…${end}`;
    }
    return rawNum || rawName || rawId;
  }

  if (category === 'Location') {
    const isTower = (node.labels || []).includes('CellTower') ||
                    rawId.toLowerCase().includes('tower') ||
                    rawName.toLowerCase().includes('tower') ||
                    Boolean(node.properties?.tower_code) ||
                    Boolean(node.properties?.cell_tower_id);
    if (isTower) {
      const towerCode = String(node.properties?.tower_code || node.properties?.cell_tower_id || rawName || rawId);
      // Converts CellTower_1_3 or cell_tower_1_3 -> Tower 1-3
      const cleaned = towerCode
        .replace(/^CellTower_/i, 'Tower ')
        .replace(/^cell_tower_/i, 'Tower ')
        .replace(/^tower_/i, 'Tower ')
        .replace(/_/g, '-');
      if (cleaned.toLowerCase().startsWith('tower')) {
        return truncateName(cleaned, 16);
      }
      return `Tower ${truncateName(cleaned, 10)}`;
    }
    // Location address: extract street/first clause (e.g. 19 Foundry Rd)
    const address = String(node.properties?.address || node.properties?.location_name || rawName || rawId);
    const firstClause = address.split(',')[0].trim();
    if (firstClause && !firstClause.toLowerCase().startsWith('location_')) {
      return truncateName(firstClause, 18);
    }
    return rawId.length > 8 ? `Loc …${rawId.slice(-4)}` : (rawName || rawId);
  }

  if (category === 'Account') {
    const acc = String(node.properties?.account_number || rawName || rawId).replace(/\s+/g, '');
    const last4 = acc.length > 4 ? acc.slice(-4) : acc;
    return `Acct …${last4}`;
  }

  if (category === 'Device') {
    const imei = node.properties?.imei || node.properties?.imei_number;
    if (imei) {
      const imeiStr = String(imei).trim();
      return `IMEI …${imeiStr.slice(-4)}`;
    }
    if (rawName && !rawName.toLowerCase().startsWith('device_')) {
      return truncateName(rawName, 16);
    }
    return rawId.length > 8 ? `Device …${rawId.slice(-4)}` : (rawName || rawId);
  }

  if (category === 'Vehicle') {
    const plate = node.properties?.license_plate || node.properties?.plate;
    if (plate) return String(plate).trim();
    if (rawName && !rawName.toLowerCase().startsWith('vehicle_')) {
      return truncateName(rawName, 16);
    }
    return rawId.length > 8 ? `Vehicle …${rawId.slice(-4)}` : (rawName || rawId);
  }

  if (category === 'Person') {
    if (rawName && !rawName.toLowerCase().startsWith('person_') && !rawName.toLowerCase().startsWith('entity_')) {
      return abbreviatePersonName(rawName, 16);
    }
    return rawId.length > 8 ? `Person …${rawId.slice(-4)}` : (rawName || rawId);
  }

  if (category === 'Case') {
    const cname = String(node.properties?.case_name || rawName || rawId);
    return truncateName(cname, 16);
  }

  if (category === 'Evidence') {
    const docType = String(node.properties?.source_type || node.properties?.record_type || rawName || rawId);
    return truncateName(docType.startsWith('Doc') ? docType : `Doc: ${docType}`, 16);
  }

  const labelToUse = rawName || rawId;
  if (!labelToUse) return category;
  return truncateName(labelToUse, 18);
}

export type StructuredTier = 0 | 1 | 2;

export function getStructuredTier(category: EntityCategory, labels: string[] = []): StructuredTier {
  // Tier 0: Top layer: Persons, aliases, Case/FIR node, Organizations
  if (category === 'Person' || category === 'Case' || category === 'Organization') {
    return 0;
  }
  if (labels.some(l => ['Person', 'Case', 'Organization', 'Company', 'FIR', 'PriorCase', 'Suspect', 'Target'].includes(l))) {
    return 0;
  }

  // Tier 1: Middle layer: Phones, Vehicles, Bank Accounts, Major operational assets
  if (category === 'Phone' || category === 'Vehicle' || category === 'Account') {
    return 1;
  }
  if (labels.some(l => ['Phone', 'PhoneNumber', 'Vehicle', 'BankAccount', 'Account', 'Transaction'].includes(l))) {
    return 1;
  }

  // Tier 2: Bottom layer: Devices, IMEI, Cell Towers, Locations, Technical/supporting forensic entities
  return 2;
}

export interface StructuredNodePosition {
  x: number;
  y: number;
  tier: StructuredTier;
}

export function computeStructuredPositions(
  nodes: GraphNode[],
  edges: GraphEdge[],
  degrees: Record<string, number>
): Record<string, StructuredNodePosition> {
  const positions: Record<string, StructuredNodePosition> = {};
  if (!nodes || nodes.length === 0) return positions;

  const tier0: GraphNode[] = [];
  const tier1: GraphNode[] = [];
  const tier2: GraphNode[] = [];

  const tierMap: Record<string, StructuredTier> = {};
  nodes.forEach(n => {
    const cat = getEntityCategory(n.labels);
    const tier = getStructuredTier(cat, n.labels);
    tierMap[n.id] = tier;
    if (tier === 0) tier0.push(n);
    else if (tier === 1) tier1.push(n);
    else tier2.push(n);
  });

  const adj: Record<string, Set<string>> = {};
  edges.forEach(e => {
    if (!adj[e.source]) adj[e.source] = new Set();
    if (!adj[e.target]) adj[e.target] = new Set();
    adj[e.source].add(e.target);
    adj[e.target].add(e.source);
  });

  const TIER_Y: Record<StructuredTier, number> = {
    0: -190,
    1: 0,
    2: 190
  };

  // 1. Order Tier 0 nodes (Actors & Command):
  // Sort by degree descending so central hub nodes sit in the middle of the top row
  tier0.sort((a, b) => (degrees[b.id] || 0) - (degrees[a.id] || 0));
  const balancedTier0: GraphNode[] = [];
  tier0.forEach((n, idx) => {
    if (idx % 2 === 0) balancedTier0.push(n);
    else balancedTier0.unshift(n);
  });

  const count0 = balancedTier0.length;
  const X_SPACING_0 = Math.max(160, Math.min(240, 1400 / Math.max(count0, 1)));
  balancedTier0.forEach((n, idx) => {
    const x = (idx - (count0 - 1) / 2) * X_SPACING_0;
    positions[n.id] = { x, y: TIER_Y[0], tier: 0 };
  });

  // 2. Order Tier 1 nodes (Operations & Assets):
  // Sort barycentrically based on average x of connected Tier 0 parents
  const tier1WithTarget = tier1.map(n => {
    const neighbors = Array.from(adj[n.id] || []);
    const tier0Neighbors = neighbors.filter(nbrId => tierMap[nbrId] === 0 && positions[nbrId]);
    let targetX = 0;
    if (tier0Neighbors.length > 0) {
      targetX = tier0Neighbors.reduce((sum, nbrId) => sum + positions[nbrId].x, 0) / tier0Neighbors.length;
    }
    return { node: n, targetX, degree: degrees[n.id] || 0 };
  });

  tier1WithTarget.sort((a, b) => {
    if (Math.abs(a.targetX - b.targetX) > 1) {
      return a.targetX - b.targetX;
    }
    return b.degree - a.degree;
  });

  const count1 = tier1WithTarget.length;
  const X_SPACING_1 = Math.max(150, Math.min(220, 1400 / Math.max(count1, 1)));
  tier1WithTarget.forEach((item, idx) => {
    const x = (idx - (count1 - 1) / 2) * X_SPACING_1;
    positions[item.node.id] = { x, y: TIER_Y[1], tier: 1 };
  });

  // 3. Order Tier 2 nodes (Technical & Forensics):
  // Sort barycentrically based on average x of connected Tier 1 or Tier 0 parents
  const tier2WithTarget = tier2.map(n => {
    const neighbors = Array.from(adj[n.id] || []);
    const connectedParents = neighbors.filter(nbrId => positions[nbrId]);
    let targetX = 0;
    if (connectedParents.length > 0) {
      targetX = connectedParents.reduce((sum, nbrId) => sum + positions[nbrId].x, 0) / connectedParents.length;
    }
    return { node: n, targetX, degree: degrees[n.id] || 0 };
  });

  tier2WithTarget.sort((a, b) => {
    if (Math.abs(a.targetX - b.targetX) > 1) {
      return a.targetX - b.targetX;
    }
    return b.degree - a.degree;
  });

  const count2 = tier2WithTarget.length;
  const X_SPACING_2 = Math.max(150, Math.min(220, 1400 / Math.max(count2, 1)));
  tier2WithTarget.forEach((item, idx) => {
    const x = (idx - (count2 - 1) / 2) * X_SPACING_2;
    positions[item.node.id] = { x, y: TIER_Y[2], tier: 2 };
  });

  return positions;
}

// React Icon component for Legend and UI lists
export function EntityIcon({ category, size = 14, color = '#FFFFFF' }: { category: EntityCategory; size?: number; color?: string }) {
  const stroke = color;
  switch (category) {
    case 'Person':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="7" r="4.2" />
          <path d="M4 21v-1.5a6.5 6.5 0 0 1 13 0v1.5" />
        </svg>
      );
    case 'Phone':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
        </svg>
      );
    case 'Device':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="5.5" y="2.5" width="13" height="19" rx="2.5" />
          <line x1="12" y1="17.5" x2="12.01" y2="17.5" strokeWidth="2.5" />
        </svg>
      );
    case 'Vehicle':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" />
          <rect x="3" y="11" width="18" height="6.5" rx="2" />
          <circle cx="7" cy="14.2" r="1.2" fill={stroke} />
          <circle cx="17" cy="14.2" r="1.2" fill={stroke} />
          <path d="M5 17.5v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2M16 17.5v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-2" strokeWidth="1.8" />
        </svg>
      );
    case 'Account':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="3 8 12 3 21 8" strokeWidth="1.8" />
          <line x1="6" y1="10" x2="6" y2="17" />
          <line x1="12" y1="10" x2="12" y2="17" />
          <line x1="18" y1="10" x2="18" y2="17" />
          <line x1="3" y1="17" x2="21" y2="17" />
          <line x1="2" y1="20" x2="22" y2="20" />
        </svg>
      );
    case 'Location':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7z" />
          <circle cx="12" cy="9" r="2.5" />
        </svg>
      );
    case 'Organization':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 21V6a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v15" />
          <path d="M12 21V11a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v10" />
          <line x1="2" y1="21" x2="22" y2="21" />
        </svg>
      );
    case 'Evidence':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="5" y="3" width="14" height="18" rx="2.5" />
          <line x1="8.5" y1="8" x2="15.5" y2="8" />
          <line x1="8.5" y1="12" x2="15.5" y2="12" />
          <line x1="8.5" y1="16" x2="12.5" y2="16" />
        </svg>
      );
    case 'Case':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      );
  }
}

export const ENTITY_LEGEND_CONFIG: { type: string; label: string; color: string; category: EntityCategory }[] = [
  { type: 'Person', label: 'Person', color: '#3B82F6', category: 'Person' },
  { type: 'Phone', label: 'Phone', color: '#F97316', category: 'Phone' },
  { type: 'Device', label: 'Device', color: '#0284C7', category: 'Device' },
  { type: 'Vehicle', label: 'Vehicle', color: '#EC4899', category: 'Vehicle' },
  { type: 'BankAccount', label: 'Account', color: '#A78BFA', category: 'Account' },
  { type: 'Location', label: 'Location', color: '#84CC16', category: 'Location' },
  { type: 'Organization', label: 'Organization', color: '#F59E0B', category: 'Organization' },
  { type: 'Evidence', label: 'Evidence', color: '#64748B', category: 'Evidence' },
  { type: 'Case', label: 'Case', color: '#6366F1', category: 'Case' },
];

function nodeHoverCard(type: string, name: string, id: string, lines: string[]) {
  const card = document.createElement('div');
  card.className = 'graph-node-preview';
  let content = card;
  const add = (tag: string, className: string, value: string) => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = value;
    content.appendChild(element);
  };
  add('div', 'graph-node-preview-type', type.replace(/([a-z])([A-Z])/g, '$1 $2'));
  add('div', 'graph-node-preview-name', name.replace(/\n/g, ' '));
  add('div', 'graph-node-preview-id', `ID · ${id}`);
  const body = document.createElement('div');
  body.className = 'graph-node-preview-body';
  card.appendChild(body);
  content = body;
  lines.slice(2).forEach(line => {
    const text = line.replace(/[📌👤📞💳]/gu, '').trim();
    if (text) add('div', text.startsWith('•') ? 'graph-node-preview-row' : 'graph-node-preview-detail', text.replace(/^•\s*/, ''));
  });
  content = card;
  add('div', 'graph-node-preview-footer', 'Click node to inspect dossier, sources, and connections');
  return card;
}

export interface GraphExplorerModuleProps {
  cases: Case[];
  selectedCase: string | null;
  setSelectedCase: (id: string | null) => void;
  openEntityModal: (id: string) => void;
  addToast: (msg: string, type?: string) => void;
  theme: string;
}

export function GraphExplorerModule({ cases, selectedCase, setSelectedCase, openEntityModal, addToast, theme }: GraphExplorerModuleProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<any>(null);
  const nodesDataSetRef = useRef<any>(null);
  const edgesDataSetRef = useRef<any>(null);
  const rawNodesRef = useRef<any[]>([]);
  const rawEdgesRef = useRef<any[]>([]);
  const nodeLabelMap = useRef<Record<string, string>>({});
  const edgeLabelMap = useRef<Record<string, string>>({});
  const keyNodeIdsRef = useRef<Set<string>>(new Set());
  const selectedNodeRef = useRef<GraphNode | null>(null);
  const selectedRelationshipRef = useRef<GraphEdge | null>(null);
  const matchingNodeIdsRef = useRef<Set<string>>(new Set());
  const focusedNodeIdRef = useRef<string | null>(null);
  const focusedNeighborIdsRef = useRef<Set<string>>(new Set());
  const hasInitializedViewportRef = useRef<boolean>(false);
  const primaryComponentCenterRef = useRef<{ x: number; y: number } | null>(null);

  const [caseFilter, setCaseFilter] = useState<string>(selectedCase || '');
  const [graphType, setGraphType] = useState<string>('focused');
  const [limit, setLimit] = useState<number>(300);

  // Graph Presentation Mode: Structured (aligned hierarchical lanes) vs Investigation (force exploration)
  const [presentationMode, setPresentationMode] = useState<'structured' | 'investigation'>('structured');

  // Core visual toggles
  const [showCaseNodes, setShowCaseNodes] = useState<boolean>(false);
  const [showIsolated, setShowIsolated] = useState<boolean>(false);
  const [showAllLabels, setShowAllLabels] = useState<boolean>(false);
  const [showEdgeLabels, setShowEdgeLabels] = useState<boolean>(false);

  // UI state: Collapsible sidebar & canvas legend
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [legendCollapsed, setLegendCollapsed] = useState<boolean>(false);
  const [showCanvasLegend, setShowCanvasLegend] = useState<boolean>(false);

  const [totalIsolatedCount, setTotalIsolatedCount] = useState<number>(0);
  const [expanding, setExpanding] = useState<boolean>(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());

  const [physicsEnabled, setPhysicsEnabled] = useState<boolean>(true);
  const [aiPanelCollapsed, setAiPanelCollapsed] = useState<boolean>(true);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const graphStageRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [graphError, setGraphError] = useState('');
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [selectedRelationship, setSelectedRelationship] = useState<GraphEdge | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    selectedNodeRef.current = selectedNode;
  }, [selectedNode]);

  useEffect(() => {
    selectedRelationshipRef.current = selectedRelationship;
  }, [selectedRelationship]);

  // AI Copilot state
  const [aiChatLog, setAiChatLog] = useState<AiChatMessage[]>([
    {
      sender: 'bot',
      model: 'Atlas AI Graph Extractor',
      content: "How can I assist your investigation? Ask about key suspects, communication clusters, or financial trails.",
      chips: [
        'Who is the main suspect?',
        'Show financial transfer trail',
        'Summarize top communications'
      ]
    }
  ]);
  const [aiInput, setAiInput] = useState<string>('');
  const [aiQuerying, setAiQuerying] = useState<boolean>(false);
  const aiBodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (aiBodyRef.current) {
      aiBodyRef.current.scrollTop = aiBodyRef.current.scrollHeight;
    }
  }, [aiChatLog, aiQuerying]);

  // Search in network state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchIndex, setSearchIndex] = useState<number>(0);

  const matchingNodes = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const q = searchQuery.toLowerCase().trim();
    return (graphNodes || []).filter(n => {
      const nameMatch = n.name && n.name.toLowerCase().includes(q);
      const idMatch = n.id && n.id.toLowerCase().includes(q);
      const phoneMatch = n.properties?.phone_number && String(n.properties.phone_number).toLowerCase().includes(q);
      const plateMatch = n.properties?.license_plate && String(n.properties.license_plate).toLowerCase().includes(q);
      const roleMatch = n.properties?.role && String(n.properties.role).toLowerCase().includes(q);
      return Boolean(nameMatch || idMatch || phoneMatch || plateMatch || roleMatch);
    });
  }, [searchQuery, graphNodes]);

  useEffect(() => {
    matchingNodeIdsRef.current = new Set(matchingNodes.map(m => m.id));
  }, [matchingNodes]);

  // Apply neighborhood focus (interactive dimming)
  const applyNeighborhoodHighlight = useCallback((selNodeId: string | null) => {
    const nodesDs = nodesDataSetRef.current;
    const edgesDs = edgesDataSetRef.current;
    const rawNodes = rawNodesRef.current;
    const rawEdges = rawEdgesRef.current;
    if (!nodesDs || !edgesDs || !rawNodes.length) return;

    const isLight = theme !== 'dark';

    if (!selNodeId) {
      // Restore all nodes and edges to default appearance
      focusedNodeIdRef.current = null;
      focusedNeighborIdsRef.current = new Set();
      nodesDs.update(rawNodes);
      edgesDs.update(rawEdges);
      networkRef.current?.redraw();
      return;
    }

    // Direct 1-hop neighborhood
    const neighborNodeIds = new Set<string>([selNodeId]);
    const connectingEdgeIds = new Set<string>();

    rawEdges.forEach(e => {
      if (e.from === selNodeId || e.to === selNodeId) {
        connectingEdgeIds.add(e.id);
        neighborNodeIds.add(e.from);
        neighborNodeIds.add(e.to);
      }
    });

    focusedNodeIdRef.current = selNodeId;
    focusedNeighborIdsRef.current = neighborNodeIds;

    const nodeUpdates = rawNodes.map(n => {
      const isNeighbor = neighborNodeIds.has(n.id);
      const isTarget = n.id === selNodeId;
      const label = nodeLabelMap.current[n.id] || n.label;
      const isKey = keyNodeIdsRef.current.has(n.id);
      return {
        id: n.id,
        opacity: isNeighbor ? 1.0 : 0.15,
        label: label,
        size: isTarget ? (isKey ? 23 : 20) : n.size,
        borderWidth: isTarget ? 3.5 : n.borderWidth,
        color: isTarget
          ? { background: n.color?.background, border: '#F59E0B', highlight: { background: n.color?.background, border: '#F59E0B' } }
          : n.color,
        shadow: isTarget
          ? { enabled: true, color: 'rgba(245, 158, 11, 0.65)', size: 10, x: 0, y: 0 }
          : n.shadow
      };
    });
    nodesDs.update(nodeUpdates);

    const edgeUpdates = rawEdges.map(e => {
      const isConnecting = connectingEdgeIds.has(e.id);
      const edgeLabel = isConnecting ? (edgeLabelMap.current[e.id] || e.label || '') : (showEdgeLabels ? (edgeLabelMap.current[e.id] || e.label || '') : '');
      return {
        id: e.id,
        width: isConnecting ? Math.max(e.width || 1.8, 2.8) : 1.0,
        label: edgeLabel,
        color: isConnecting
          ? { color: isLight ? '#0F172A' : '#38BDF8', highlight: '#F59E0B' }
          : { color: isLight ? 'rgba(148, 163, 184, 0.08)' : 'rgba(100, 116, 139, 0.08)' },
        font: {
          ...e.font,
          color: isConnecting ? (isLight ? '#0F172A' : '#E2E8F0') : 'transparent',
          background: isConnecting ? (isLight ? 'rgba(255,255,255,0.94)' : 'rgba(15,23,42,0.92)') : 'transparent'
        }
      };
    });
    edgesDs.update(edgeUpdates);
    networkRef.current?.redraw();
  }, [theme, showAllLabels, showEdgeLabels]);

  const focusNode = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setSelectedRelationship(null);
    applyNeighborhoodHighlight(node.id);
    networkRef.current?.selectNodes([node.id]);
    // Preserve current scale when focusing node
    const currentScale = networkRef.current?.getScale() || 1.2;
    networkRef.current?.focus(node.id, {
      scale: Math.max(currentScale, 1.15),
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    });
  }, [applyNeighborhoodHighlight]);

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e && e.preventDefault) e.preventDefault();
    if (matchingNodes.length === 0) return;
    const nextIdx = (searchIndex + 1) % matchingNodes.length;
    setSearchIndex(nextIdx);
    focusNode(matchingNodes[nextIdx]);
  };

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    hasInitializedViewportRef.current = false;
    try {
      const url = `/api/graph?limit=${limit}&graph_type=${encodeURIComponent(graphType)}${caseFilter ? `&case_id=${encodeURIComponent(caseFilter)}` : ''}&include_isolated=${showIsolated}`;
      const g = await API.get<{ nodes?: GraphNode[]; edges?: GraphEdge[]; total_isolated_nodes?: number }>(url);
      setGraphNodes(g.nodes || []);
      setGraphEdges(g.edges || []);
      setTotalIsolatedCount(g.total_isolated_nodes || 0);
      setGraphError('');
      setGraphLoaded(true);
      setSelectedNode(null);
      setSelectedRelationship(null);
    } catch (e: any) {
      console.error('ATLAS graph unavailable', e);
      setGraphError('Case network is temporarily unavailable.');
    } finally {
      setLoading(false);
    }
  }, [limit, graphType, caseFilter, showIsolated]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  useEffect(() => {
    setCaseFilter(selectedCase || '');
  }, [selectedCase]);

  // Expand 1-Hop Neighbors of selected node
  const handleExpandNeighbors = async () => {
    if (!selectedNode) return;
    setExpanding(true);
    try {
      const url = `/api/graph/expand?node_id=${encodeURIComponent(selectedNode.id)}${caseFilter ? `&case_id=${encodeURIComponent(caseFilter)}` : ''}`;
      const res = await API.get<{ nodes?: GraphNode[]; edges?: GraphEdge[]; total_nodes?: number; total_edges?: number }>(url);
      const existingNodeIds = new Set((graphNodes || []).map(n => n.id));
      const existingEdgeKeys = new Set((graphEdges || []).map(e => `${e.source}_${e.type}_${e.target}`));

      const newNodes = (res.nodes || []).filter(n => !existingNodeIds.has(n.id));
      const newEdges = (res.edges || []).filter(e => !existingEdgeKeys.has(`${e.source}_${e.type}_${e.target}`));

      if (newNodes.length === 0 && newEdges.length === 0) {
        addToast(`No additional unmapped neighbors found for ${selectedNode.name || selectedNode.id}`, 'plain');
      } else {
        setGraphNodes(prev => [...prev, ...newNodes]);
        setGraphEdges(prev => [...prev, ...newEdges]);
        addToast(`Expanded ${newNodes.length} neighbor(s) and ${newEdges.length} link(s) for ${selectedNode.name || selectedNode.id}`, 'ok');
      }
    } catch (err: any) {
      addToast(`Neighbor expansion failed: ${err.message}`, 'error');
    } finally {
      setExpanding(false);
    }
  };

  // Reset View handler (re-centers primary component at comfortable zoom)
  const handleResetView = () => {
    if (!networkRef.current) return;
    if (presentationMode === 'structured') {
      (networkRef.current as any)?.fit({
        animation: true
      });
      setTimeout(() => {
        if (networkRef.current) {
          const sc = networkRef.current.getScale();
          if (sc > 1.30) {
            networkRef.current.moveTo({ scale: 1.15, animation: true });
          }
        }
      }, 250);
      addToast('Reset Structured Layout: Aligned tiers centered', 'ok');
      return;
    }

    const center = primaryComponentCenterRef.current;
    if (center) {
      networkRef.current.moveTo({
        position: center,
        scale: 1.25,
        animation: true
      });
    } else {
      const rawNodes = rawNodesRef.current;
      const keyNode = rawNodes.find(n => n.size > 18) || rawNodes[0];
      if (keyNode) {
        networkRef.current.focus(keyNode.id, { scale: 1.25, animation: true });
      } else {
        networkRef.current.moveTo({ position: { x: 0, y: 0 }, scale: 1.25, animation: true });
      }
    }
    addToast('Viewport centered on primary network at 100% zoom', 'ok');
  };

  // Fit Structured Graph handler
  const handleFitStructured = () => {
    if (!networkRef.current) return;
    (networkRef.current as any)?.fit({
      animation: true
    });
    addToast('Structured tiers fitted to canvas', 'ok');
  };

  // Focus Selection handler
  const handleFocusSelection = () => {
    if (!networkRef.current || !selectedNode) return;
    networkRef.current.focus(selectedNode.id, {
      scale: 1.35,
      animation: true
    });
  };

  // Fit view manual button (allows user to see full graph if explicitly chosen)
  const handleFitNetwork = () => {
    if (!networkRef.current) return;
    (networkRef.current as any)?.fit({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    });
  };

  // Resize listener
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        networkRef.current?.setSize('100%', '100%');
        networkRef.current?.redraw();
      });
    };
    window.addEventListener('resize', measure);
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', escape);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', measure);
      window.removeEventListener('keydown', escape);
    };
  }, []);

  // When expand canvas changes, re-measure canvas immediately
  useEffect(() => {
    const t = setTimeout(() => {
      networkRef.current?.setSize('100%', '100%');
      networkRef.current?.redraw();
    }, 100);
    return () => clearTimeout(t);
  }, [expanded, sidebarCollapsed]);

  // Render Vis.js Network
  useEffect(() => {
    if (!containerRef.current) return;
    if (networkRef.current) {
      networkRef.current.destroy();
      networkRef.current = null;
    }

    const isLight = theme !== 'dark';
    const textColor = isLight ? '#0F172A' : '#F8FAFC';
    const edgeColor = isLight ? 'rgba(100, 116, 139, 0.45)' : 'rgba(148, 163, 184, 0.40)';

    // Filter nodes:
    // 1. By default, hide Case & Evidence nodes unless showCaseNodes is enabled
    // 2. Hide entities whose primary label is in hiddenTypes
    const visibleGraphNodes = (graphNodes || []).filter(n => {
      if (!n || !n.id) return false;
      const isCaseOrEvidence = n.labels?.some(l => ['Case', 'SourceRecord', 'Document', 'Exhibit'].includes(l));
      if (!showCaseNodes && isCaseOrEvidence) return false;
      const primaryLabel = n.labels?.[0];
      if (primaryLabel && hiddenTypes.has(primaryLabel)) return false;
      return true;
    });
    const visibleNodeIdSet = new Set(visibleGraphNodes.map(n => n.id));

    // Filter edges to only those connecting visible nodes
    const visibleGraphEdges = (graphEdges || []).filter(e => {
      if (!e || !e.source || !e.target) return false;
      return visibleNodeIdSet.has(e.source) && visibleNodeIdSet.has(e.target);
    });

    // Compute degrees
    const degrees: Record<string, number> = {};
    visibleGraphEdges.forEach(e => {
      degrees[e.source] = (degrees[e.source] || 0) + 1;
      degrees[e.target] = (degrees[e.target] || 0) + 1;
    });

    const isStructured = presentationMode === 'structured';
    const structuredPositions = isStructured
      ? computeStructuredPositions(visibleGraphNodes, visibleGraphEdges, degrees)
      : {};

    const keyIds = new Set<string>();
    const seenNodeIds = new Set<string>();
    const nodes: any[] = [];
    const localNodeLabelMap: Record<string, string> = {};

    visibleGraphNodes.forEach(n => {
      if (!n || !n.id || seenNodeIds.has(n.id)) return;
      seenNodeIds.add(n.id);

      const category = getEntityCategory(n.labels);
      const isCase = category === 'Case';
      const isPhone = category === 'Phone';
      const isVeh = category === 'Vehicle';
      const isBank = category === 'Account';

      const roleStr = String(n.properties?.role || '').toLowerCase();
      const isKey = Boolean(
        n.is_key_entity ||
        (degrees[n.id] || 0) >= 4 ||
        n.properties?.is_key_entity ||
        isCase ||
        roleStr.includes('suspect') ||
        roleStr.includes('target') ||
        roleStr.includes('leader')
      );

      if (isKey) keyIds.add(n.id);

      // Node Size: Target typical node diameter: 30 px (radius 15 px).
      // Key hub node diameter: 36 px (radius 18 px).
      const nodeSize = isKey ? 18 : 15;
      const palette = getNodePalette(category, isLight);
      const sPos = structuredPositions[n.id];

      // Resolve associated person name for phone or asset
      let associatedPerson = (n.properties?.associated_person_name || n.properties?.registered_owner || n.properties?.subscriber_name || n.properties?.owner_name) as string | undefined;

      if (isPhone && !associatedPerson) {
        const ownerEdge = (visibleGraphEdges || []).find(e =>
          (e.type === 'OWNS' || e.type === 'USES' || e.type === 'HAS_PHONE' || e.type === 'USES_PHONE') &&
          (e.target === n.id || e.source === n.id)
        );
        if (ownerEdge) {
          const pId = ownerEdge.target === n.id ? ownerEdge.source : ownerEdge.target;
          const pNode = (graphNodes || []).find(x => x.id === pId);
          if (pNode && pNode.labels?.includes('Person')) {
            associatedPerson = (pNode.properties?.name || pNode.name || pId) as string;
          }
        }
      }

      let fullLabel = n.name || n.id;
      if (isPhone && associatedPerson && String(associatedPerson).toLowerCase() !== 'unknown') {
        const rawPhone = String(n.properties?.phone_number || n.name?.split('\n')[0] || n.id).trim();
        const cleanPerson = String(associatedPerson).split('\n')[0].replace(/^\(|\)$/g, '').trim();
        fullLabel = `${rawPhone} (${cleanPerson})`;
      } else if (isVeh && n.properties?.license_plate) {
        fullLabel = String(n.properties.license_plate);
      } else if (isBank && n.properties?.account_number) {
        const acc = String(n.properties.account_number);
        const last4 = acc.length > 4 ? acc.slice(-4) : acc;
        const holder = n.properties?.holder_name ? ` (${String(n.properties.holder_name).split(' ')[0]})` : '';
        fullLabel = `Acct …${last4}${holder}`;
      }

      // High-contrast abbreviated canvas display label (every single node gets a valid display label)
      const displayLabel = formatDisplayLabel(n, category);
      localNodeLabelMap[n.id] = displayLabel;

      const isMatched = matchingNodes.some(m => m.id === n.id);

      // Tooltip Lines
      const tooltipLines: string[] = [
        `📌 ${category}: ${fullLabel.replace('\n', ' ')}`,
        `ID: ${n.id}`
      ];
      if (associatedPerson && String(associatedPerson).toLowerCase() !== 'unknown') {
        tooltipLines.push(`👤 Associated Person: ${String(associatedPerson).split('\n')[0].replace(/^\(|\)$/g, '').trim()}`);
      }
      if (n.properties?.role) tooltipLines.push(`Role: ${n.properties.role}`);
      if (n.properties?.phone_number && n.properties.phone_number !== n.name) tooltipLines.push(`Phone: ${n.properties.phone_number}`);
      if (n.properties?.risk_score !== undefined) tooltipLines.push(`Risk Score: ${n.properties.risk_score}`);

      const comms = n.properties?.communications;
      const totalCalls = Number(n.properties?.total_calls || 0);
      if (totalCalls > 0) tooltipLines.push(`\n📞 Total Calls Logged: ${totalCalls}`);
      if (comms && typeof comms === 'object') {
        const commList = Object.values(comms) as any[];
        if (commList.length > 0) {
          tooltipLines.push(`📞 Communication Breakdown:`);
          commList.slice(0, 3).forEach(c => {
            const partner = c.partner_name || c.partner_id;
            const cCount = Number(c.call_count || 1);
            const dur = c.summary ? ` (${c.summary})` : '';
            tooltipLines.push(`  • ${partner}: ${cCount} time${cCount > 1 ? 's' : ''}${dur}`);
          });
          if (commList.length > 3) tooltipLines.push(`  • +${commList.length - 3} more contacts`);
        }
      }

      const txs = n.properties?.transactions;
      const totalTx = Number(n.properties?.total_transactions || 0);
      const totalAmt = Number(n.properties?.total_amount_transferred || 0);
      if (totalTx > 0) tooltipLines.push(`\n💳 Total Transactions: ${totalTx}${totalAmt > 0 ? ` (₹${Math.round(totalAmt).toLocaleString()})` : ''}`);

      nodes.push({
        id: n.id,
        label: displayLabel,
        level: getNodeLevel(n.labels),
        title: nodeHoverCard(category, fullLabel, n.id, tooltipLines),
        shape: 'circularImage', // Circular node with centered white SVG icon
        image: getEntityIconDataUri(category),
        size: nodeSize,
        x: isStructured && sPos ? sPos.x : undefined,
        y: isStructured && sPos ? sPos.y : undefined,
        physics: !isStructured,
        fixed: isStructured ? { x: false, y: false } : false,
        shapeProperties: {
          useImageSize: false,
          interpolation: true
        },
        borderWidth: isMatched ? 3.5 : (isKey ? 2.5 : 2.0),
        borderWidthSelected: 3.5,
        shadow: isMatched
          ? {
              enabled: true,
              color: 'rgba(245, 158, 11, 0.65)',
              size: 10,
              x: 0,
              y: 0
            }
          : {
              enabled: true,
              color: 'rgba(0, 0, 0, 0.16)',
              size: 4,
              x: 0,
              y: 1
            },
        color: {
          background: palette.bg,
          border: isMatched ? '#F59E0B' : palette.border,
          highlight: { background: palette.bg, border: '#F59E0B' },
          hover: { background: palette.bg, border: '#38BDF8' }
        },
        font: {
          color: 'transparent', // Custom rounded pill container & bold text drawn in afterDrawing
          size: 11.5,
          face: 'Inter, system-ui, -apple-system, sans-serif',
          vadjust: 8,
          strokeWidth: 0,
          background: 'transparent'
        }
      });
    });

    nodeLabelMap.current = localNodeLabelMap;
    keyNodeIdsRef.current = keyIds;

    // Count edges per connected pair to detect parallel relationships
    const pairEdgeCount: Record<string, number> = {};
    visibleGraphEdges.forEach(e => {
      if (!e || !e.source || !e.target) return;
      const pairKey = [e.source, e.target].sort().join('___');
      pairEdgeCount[pairKey] = (pairEdgeCount[pairKey] || 0) + 1;
    });

    const seenEdgeIds = new Set<string>();
    const edges: any[] = [];
    const localEdgeLabelMap: Record<string, string> = {};

    visibleGraphEdges.forEach((e, idx) => {
      if (!e || !e.source || !e.target) return;
      if (!seenNodeIds.has(e.source) || !seenNodeIds.has(e.target)) return;

      let edgeId = String(e.id || `edge_${e.source}_${e.type}_${e.target}_${idx}`);
      if (seenEdgeIds.has(edgeId)) edgeId = `${edgeId}_${idx}`;
      seenEdgeIds.add(edgeId);

      const isCaseLink = e.type === 'INVOLVES';
      const callCount = Number(e.properties?.call_count || 0);
      const txCount = Number(e.properties?.tx_count || 0);

      let fullEdgeLabel = e.type || '';
      if (e.properties?.summary) {
        fullEdgeLabel = String(e.properties.summary);
      } else if (callCount > 1) {
        fullEdgeLabel = `${callCount} calls`;
      } else if (txCount > 1) {
        fullEdgeLabel = `${txCount} txns`;
      }
      if (isCaseLink) fullEdgeLabel = '';

      localEdgeLabelMap[edgeId] = fullEdgeLabel;

      const displayEdgeLabel = showEdgeLabels ? fullEdgeLabel : '';

      let edgeTitle = `${e.type || 'LINK'} (${e.source} → ${e.target})`;
      if (callCount > 1) {
        edgeTitle += `\n📞 Aggregated Calls: ${callCount} times`;
        if (e.properties?.total_duration) edgeTitle += `\n⏱ Total Duration: ${e.properties.total_duration}`;
      } else if (txCount > 1) {
        edgeTitle += `\n💳 Aggregated Transactions: ${txCount} times`;
        if (e.properties?.total_amount) edgeTitle += `\n💰 Total Transferred: ₹${Math.round(Number(e.properties.total_amount)).toLocaleString()}`;
      }

      // Thin but visible edges: 1.4px to 2.4px
      let edgeWidth = 1.4;
      const count = Math.max(callCount, txCount);
      if (count > 1) {
        edgeWidth = Math.min(1.4 + Math.log2(count) * 0.35, 2.4);
      }

      // Straight edges by default; curved edges only when necessary for parallel relationships or intra-tier connections
      const pairKey = [e.source, e.target].sort().join('___');
      const isParallel = (pairEdgeCount[pairKey] || 0) > 1;

      let smoothConfig: any = false;
      if (isStructured) {
        const sTier = structuredPositions[e.source]?.tier;
        const tTier = structuredPositions[e.target]?.tier;
        const isIntraTier = sTier !== undefined && tTier !== undefined && sTier === tTier;

        if (isParallel) {
          smoothConfig = { enabled: true, type: 'curvedCW', roundness: 0.22 };
        } else if (isIntraTier) {
          // Arches cleanly over Tier 0 & 1, or under Tier 2
          const curveType = sTier === 2 ? 'curvedCCW' : 'curvedCW';
          smoothConfig = { enabled: true, type: curveType, roundness: 0.24 };
        } else {
          // Clean straight edges between different tiers
          smoothConfig = false;
        }
      } else {
        smoothConfig = isParallel
          ? { enabled: true, type: 'curvedCW', roundness: 0.18 }
          : false;
      }

      // Small direction arrows only where direction matters
      const isDirected = [
        'CALLED', 'TRANSFERRED_TO', 'DEPOSITED_TO', 'TRANSACTION',
        'OWNS', 'USES', 'USES_PHONE', 'OWNS_VEHICLE', 'REGISTERED_OWNER_OF', 'REPORTED_USER_OF',
        'LOCATED_AT', 'SIGHTED_AT', 'OBSERVED_AT_CELL', 'RESIDES_AT',
        'INVESTIGATING_OFFICER_OF', 'COMPLAINANT_IN', 'SUSPECT_NAMED_IN', 'WITNESS_IN',
        'HAS_EVIDENCE', 'CONTAINS', 'EXTRACTED_FROM', 'USED_DEVICE'
      ].includes(e.type || '');

      edges.push({
        id: edgeId,
        from: e.source,
        to: e.target,
        label: displayEdgeLabel,
        title: edgeTitle,
        width: edgeWidth,
        selectionWidth: 2.6,
        hoverWidth: 2.6,
        physics: !isStructured && !isCaseLink,
        arrows: {
          to: {
            enabled: isDirected,
            scaleFactor: 0.50
          }
        },
        color: {
          color: edgeColor,
          highlight: '#F59E0B',
          hover: isLight ? '#0F172A' : '#38BDF8'
        },
        font: {
          color: isLight ? '#334155' : '#E2E8F0',
          size: 10.5,
          face: 'Inter, system-ui, sans-serif',
          strokeWidth: isLight ? 2 : 2,
          strokeColor: isLight ? '#FFFFFF' : '#0F172A',
          background: isLight ? 'rgba(255,255,255,0.94)' : 'rgba(15,23,42,0.92)',
          align: 'horizontal'
        },
        smooth: smoothConfig
      });
    });

    edgeLabelMap.current = localEdgeLabelMap;

    rawNodesRef.current = nodes;
    rawEdgesRef.current = edges;

    const DataSet = (vis as any).DataSet;
    const nodesDataSet = new DataSet(nodes);
    const edgesDataSet = new DataSet(edges);
    nodesDataSetRef.current = nodesDataSet;
    edgesDataSetRef.current = edgesDataSet;

    const seed = getDeterministicSeed(caseFilter || 'all');

    // TUNED FORCE-DIRECTED PHYSICS ENGINE:
    // - Preferred connected-node center distance: 80–120 px (springLength: 95)
    // - Moderate repulsion prevents overlap without blowing nodes apart (gravitationalConstant: -70)
    // - Stronger link attraction prevents long edges (springConstant: 0.09)
    // - Moderate centering keeps the network together (centralGravity: 0.015)
    // - Strict collision gap (avoidOverlap: 1.0)
    const net = new vis.Network(containerRef.current, { nodes: nodesDataSet, edges: edgesDataSet }, {
      layout: {
        randomSeed: seed,
        improvedLayout: true
      },
      physics: {
        enabled: !isStructured && physicsEnabled,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -70,
          centralGravity: 0.015,
          springLength: 95,
          springConstant: 0.09,
          damping: 0.50,
          avoidOverlap: 1.0
        },
        stabilization: {
          enabled: !isStructured,
          iterations: !isStructured ? 150 : 0,
          updateInterval: 25,
          fit: false
        }
      },
      nodes: { borderWidth: 2.0 },
      edges: { width: 1.6, selectionWidth: 2.5, hoverWidth: 2.5 },
      interaction: {
        hover: true,
        tooltipDelay: 80,
        navigationButtons: false,
        keyboard: true,
        zoomView: true,
        dragView: true,
        dragNodes: true
      }
    });

    // In Structured View: draw horizontal lane divider guidelines and tier badges in canvas background
    if (isStructured) {
      net.on('beforeDrawing', (ctx: CanvasRenderingContext2D) => {
        const isLightMode = theme !== 'dark';
        ctx.save();

        let minX = -450;
        let maxX = 450;
        Object.values(structuredPositions).forEach(p => {
          if (p.x - 140 < minX) minX = p.x - 140;
          if (p.x + 140 > maxX) maxX = p.x + 140;
        });

        const dividerY1 = -95;
        const dividerY2 = 95;

        // Draw dashed horizontal lane dividers
        ctx.strokeStyle = isLightMode ? 'rgba(100, 116, 139, 0.20)' : 'rgba(148, 163, 184, 0.14)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([6, 6]);

        ctx.beginPath();
        ctx.moveTo(minX - 80, dividerY1);
        ctx.lineTo(maxX + 80, dividerY1);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(minX - 80, dividerY2);
        ctx.lineTo(maxX + 80, dividerY2);
        ctx.stroke();

        ctx.setLineDash([]); // Reset dash

        // Tier Lane Badges on left side
        const badges = [
          { text: 'TIER 1 · ACTORS & COMMAND', y: -190, color: isLightMode ? '#059669' : '#10B981' },
          { text: 'TIER 2 · OPERATIONS & ASSETS', y: 0, color: isLightMode ? '#EA580C' : '#F97316' },
          { text: 'TIER 3 · TECHNICAL & FORENSICS', y: 190, color: isLightMode ? '#2563EB' : '#3B82F6' },
        ];

        ctx.font = '700 10px Inter, system-ui, -apple-system, sans-serif';
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'left';

        badges.forEach(b => {
          const textW = ctx.measureText(b.text).width;
          const badgeW = textW + 24;
          const badgeH = 22;
          const badgeX = minX - badgeW - 30;
          const badgeY = b.y - badgeH / 2;

          ctx.fillStyle = isLightMode ? 'rgba(248, 250, 252, 0.95)' : 'rgba(15, 23, 42, 0.92)';
          ctx.strokeStyle = isLightMode ? 'rgba(203, 213, 225, 0.8)' : 'rgba(71, 85, 105, 0.6)';
          ctx.lineWidth = 1.2;

          ctx.beginPath();
          if (typeof (ctx as any).roundRect === 'function') {
            (ctx as any).roundRect(badgeX, badgeY, badgeW, badgeH, 5);
          } else {
            ctx.rect(badgeX, badgeY, badgeW, badgeH);
          }
          ctx.fill();
          ctx.stroke();

          // Small colored indicator circle
          ctx.fillStyle = b.color;
          ctx.beginPath();
          ctx.arc(badgeX + 11, b.y, 3.5, 0, Math.PI * 2);
          ctx.fill();

          // Badge title
          ctx.fillStyle = isLightMode ? '#334155' : '#CBD5E1';
          ctx.fillText(b.text, badgeX + 20, b.y + 0.5);
        });

        ctx.restore();
      });
    }

    // Custom Canvas Renderer: Draw crisp rounded pill label containers below every node matching reference Image 1
    net.on('afterDrawing', (ctx: CanvasRenderingContext2D) => {
      const isLightMode = theme !== 'dark';
      const positions = net.getPositions();
      const rawNodes = rawNodesRef.current;
      const selNode = selectedNodeRef.current;
      const selNodeId = selNode?.id || null;
      const focusedId = focusedNodeIdRef.current || selNodeId;
      const neighborIds = focusedNeighborIdsRef.current;
      const hasFocus = Boolean(focusedId);

      ctx.save();
      for (let i = 0; i < rawNodes.length; i++) {
        const n = rawNodes[i];
        const pos = positions[n.id];
        if (!pos) continue;

        const labelText = nodeLabelMap.current[n.id];
        if (!labelText) continue;

        const isSelected = n.id === selNodeId;
        const isMatched = matchingNodeIdsRef.current.has(n.id);
        const isNeighbor = neighborIds.has(n.id);
        const isKey = keyNodeIdsRef.current.has(n.id);
        const currentScale = net.getScale();

        // Controlled label display: In structured mode, show for all nodes; in investigation, selective or toggled
        const shouldShowLabel =
          isStructured ||
          showAllLabels ||
          isSelected ||
          (hasFocus && isNeighbor) ||
          isKey ||
          isMatched ||
          currentScale >= 1.15;

        if (!shouldShowLabel) continue;

        const isDimmed = hasFocus && !isNeighbor;
        const nodeRadius = n.size || 16;
        const gap = 7;
        const pillY = pos.y + nodeRadius + gap;

        ctx.font = '600 11.5px Inter, system-ui, -apple-system, sans-serif';
        const textWidth = ctx.measureText(labelText).width;
        const pillPaddingX = 9;
        const pillWidth = Math.max(textWidth + pillPaddingX * 2, 42);
        const pillHeight = 22;
        const pillX = pos.x - pillWidth / 2;

        ctx.save();
        ctx.globalAlpha = isDimmed ? 0.15 : 1.0;

        // Draw pill rounded background
        ctx.beginPath();
        if (typeof (ctx as any).roundRect === 'function') {
          (ctx as any).roundRect(pillX, pillY, pillWidth, pillHeight, 6);
        } else {
          const r = 6;
          ctx.moveTo(pillX + r, pillY);
          ctx.lineTo(pillX + pillWidth - r, pillY);
          ctx.arcTo(pillX + pillWidth, pillY, pillX + pillWidth, pillY + r, r);
          ctx.lineTo(pillX + pillWidth, pillY + pillHeight - r);
          ctx.arcTo(pillX + pillWidth, pillY, pillX + pillWidth - r, pillY + pillHeight, r);
          ctx.lineTo(pillX + r, pillY + pillHeight);
          ctx.arcTo(pillX, pillY + pillHeight, pillX, pillY + pillHeight - r, r);
          ctx.lineTo(pillX, pillY + r);
          ctx.arcTo(pillX, pillY, pillX + r, pillY, r);
          ctx.closePath();
        }

        ctx.fillStyle = isLightMode ? 'rgba(248, 250, 252, 0.96)' : 'rgba(30, 41, 59, 0.94)';
        ctx.fill();

        // Pill border
        ctx.strokeStyle = isSelected
          ? '#F59E0B'
          : isMatched
          ? '#F59E0B'
          : (isLightMode ? '#CBD5E1' : '#475569');
        ctx.lineWidth = isSelected || isMatched ? 1.8 : 1.1;
        ctx.stroke();

        // Centered label text
        ctx.fillStyle = isSelected
          ? (isLightMode ? '#0F172A' : '#FFFFFF')
          : (isLightMode ? '#0F172A' : '#F8FAFC');
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, pos.x, pillY + pillHeight / 2 + 0.5);

        ctx.restore();
      }
      ctx.restore();
    });

    // Hover Edge: temporarily show edge label and darker highlight styling
    net.on('hoverEdge', (params: any) => {
      const edgeId = params.edge;
      if (!showEdgeLabels && selectedRelationshipRef.current?.id !== edgeId) {
        const lbl = edgeLabelMap.current[edgeId];
        if (lbl) {
          edgesDataSet.update({
            id: edgeId,
            label: lbl,
            width: 2.6,
            color: { color: isLight ? '#0F172A' : '#38BDF8' }
          });
        }
      }
    });

    // Blur Edge: re-hide edge label
    net.on('blurEdge', (params: any) => {
      const edgeId = params.edge;
      if (!showEdgeLabels && selectedRelationshipRef.current?.id !== edgeId) {
        const raw = rawEdgesRef.current.find(e => e.id === edgeId);
        edgesDataSet.update({
          id: edgeId,
          label: '',
          width: raw?.width || 1.4,
          color: raw?.color || { color: edgeColor }
        });
      }
    });

    // Click: Node focus or Edge focus or Canvas background reset
    net.on('click', (p: any) => {
      if (p.nodes && p.nodes.length) {
        const targetId = p.nodes[0];
        const nObj = graphNodes.find(n => n.id === targetId);
        setSelectedNode(nObj || null);
        setSelectedRelationship(null);
        applyNeighborhoodHighlight(targetId);
      } else if (p.edges && p.edges.length) {
        const edge = graphEdges.find((e, index) => (e.id || `edge_${e.source}_${e.type}_${e.target}_${index}`) === p.edges[0]);
        setSelectedRelationship(edge || null);
        setSelectedNode(null);
        if (edge) {
          const endpoints = new Set<string>([edge.source, edge.target]);
          const targetEdgeId = p.edges[0];
          const isLightMode = theme !== 'dark';
          focusedNeighborIdsRef.current = endpoints;
          focusedNodeIdRef.current = null;
          nodesDataSet.update(rawNodesRef.current.map(n => ({
            id: n.id,
            opacity: endpoints.has(n.id) ? 1.0 : 0.15,
            label: nodeLabelMap.current[n.id] || n.label
          })));
          edgesDataSet.update(rawEdgesRef.current.map(e => ({
            id: e.id,
            width: e.id === targetEdgeId ? 3.2 : 1.0,
            label: e.id === targetEdgeId ? (edgeLabelMap.current[e.id] || e.label || '') : (showEdgeLabels ? (edgeLabelMap.current[e.id] || e.label || '') : ''),
            color: e.id === targetEdgeId ? { color: '#F59E0B' } : { color: isLightMode ? 'rgba(148, 163, 184, 0.08)' : 'rgba(100, 116, 139, 0.08)' }
          })));
          net.redraw();
        }
      } else {
        // Blank canvas clicked - clear selection & dimming
        setSelectedNode(null);
        setSelectedRelationship(null);
        applyNeighborhoodHighlight(null);
      }
    });

    // INITIAL VIEWPORT SEQUENCE:
    if (isStructured) {
      // In Structured View: immediately fit the structured lanes into the visible viewport with padding
      requestAnimationFrame(() => {
        if (net && containerRef.current) {
          (net as any).fit({
            animation: false
          });
          const sc = net.getScale();
          if (sc > 1.25) {
            net.moveTo({ scale: 1.15, animation: false });
          }
        }
      });
    } else {
      // Investigation View:
      // 1. Freeze physics when settled to prevent drifting
      // 2. Identify primary connected component / hub
      // 3. Center primary component at comfortable, readable initial zoom (scale: 1.25)
      // 4. Do not auto-fit or compress into viewport
      net.once('stabilizationIterationsDone', () => {
        net.setOptions({ physics: { enabled: false } });

        if (!hasInitializedViewportRef.current) {
          hasInitializedViewportRef.current = true;

          // Find primary hub node (key suspect or highest degree)
          const keyNodes = nodes.filter(n => n.size > 17);
          const primaryHub = keyNodes.length > 0 ? keyNodes[0] : (nodes[0] || null);

          if (primaryHub) {
            try {
              // Find 1-hop connected nodes to compute component center
              const neighborIds = [primaryHub.id];
              edges.forEach(e => {
                if (e.from === primaryHub.id) neighborIds.push(e.to);
                else if (e.to === primaryHub.id) neighborIds.push(e.from);
              });
              const positions = net.getPositions(neighborIds);
              let sumX = 0, sumY = 0, count = 0;
              Object.values(positions).forEach((p: any) => {
                if (p && typeof p.x === 'number') {
                  sumX += p.x;
                  sumY += p.y;
                  count++;
                }
              });
              const centerX = count > 0 ? sumX / count : 0;
              const centerY = count > 0 ? sumY / count : 0;
              primaryComponentCenterRef.current = { x: centerX, y: centerY };

              net.moveTo({
                position: { x: centerX, y: centerY },
                scale: 1.25, // Comfortable, readable initial zoom
                animation: false
              });
            } catch {
              net.focus(primaryHub.id, { scale: 1.25, animation: false });
            }
          } else {
            net.moveTo({
              position: { x: 0, y: 0 },
              scale: 1.25,
              animation: false
            });
          }
        }
      });
    }

    networkRef.current = net;

    return () => {
      if (net) net.destroy();
      networkRef.current = null;
      nodesDataSetRef.current = null;
      edgesDataSetRef.current = null;
    };
  }, [graphNodes, graphEdges, graphType, hiddenTypes, showCaseNodes, showAllLabels, showEdgeLabels, physicsEnabled, presentationMode, theme, caseFilter, matchingNodes, applyNeighborhoodHighlight]);

  const handleAiQuerySubmit = async (e?: React.FormEvent | null, promptOverride: string | null = null) => {
    if (e && e.preventDefault) e.preventDefault();
    const q = promptOverride || aiInput.trim();
    if (!q) return;

    if (!promptOverride) setAiInput('');
    setAiChatLog(prev => [...prev, { sender: 'user', content: q }]);
    setAiQuerying(true);

    const qLower = q.toLowerCase();
    let clientDetected: string | null = null;
    if (qLower.includes('cdr') || qLower.includes('call') || qLower.includes('phone graph') || qLower.includes('telecom')) {
      clientDetected = 'cdr';
    } else if (qLower.includes('person') || qLower.includes('suspect') || qLower.includes('people') || qLower.includes('connecting person')) {
      clientDetected = 'person';
    } else if (qLower.includes('financial') || qLower.includes('money') || qLower.includes('bank') || qLower.includes('transfer')) {
      clientDetected = 'financial';
    } else if (qLower.includes('all') || qLower.includes('full graph') || qLower.includes('reset') || qLower.includes('entire graph')) {
      clientDetected = 'all';
    }

    if (clientDetected && clientDetected !== graphType) {
      setGraphType(clientDetected);
      addToast(
        clientDetected === 'cdr' ? 'AI Extractor: Filtered view to People & Calls' :
        clientDetected === 'person' ? 'AI Extractor: Filtered view to Person Syndicate' :
        clientDetected === 'financial' ? 'AI Extractor: Filtered view to Financial Flows' :
        'AI Extractor: Restored full ecosystem graph',
        'ok'
      );
    }

    try {
      const res = await API.post<{ ai_model?: string; answer?: string; extracted_graph_type?: string }>('/api/graph/ai-query', {
        question: q,
        case_id: caseFilter || null,
        nodes_count: graphNodes?.length || null,
        edges_count: graphEdges?.length || null,
        selected_node_id: selectedNode?.id || null
      });

      if (res.extracted_graph_type && res.extracted_graph_type !== graphType && res.extracted_graph_type !== clientDetected) {
        setGraphType(res.extracted_graph_type);
      }

      setAiChatLog(prev => [...prev, {
        sender: 'bot',
        model: res.ai_model || 'Atlas AI Graph Extractor',
        content: res.answer || 'No specific inference generated.',
        chips: [
          'Who is the main suspect?',
          'Show financial transfer trail'
        ]
      }]);
    } catch (err: any) {
      setAiChatLog(prev => [...prev, {
        sender: 'bot',
        error: true,
        content: `Inference query error: ${err.message}`
      }]);
    } finally {
      setAiQuerying(false);
    }
  };

  const nodeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    (graphNodes || []).forEach(n => {
      const l = n.labels?.[0] || 'Entity';
      counts[l] = (counts[l] || 0) + 1;
    });
    return counts;
  }, [graphNodes]);

  const entityNodes = graphNodes.filter(node => !node.labels?.some(label => ['Case', 'SourceRecord'].includes(label)));
  const sourceCount = graphNodes.filter(node => node.labels?.includes('SourceRecord')).length;
  const connectedEntities = entityNodes.map(node => ({
    node,
    connections: graphEdges.filter(edge => edge.source === node.id || edge.target === node.id).length
  })).filter(item => item.connections > 0).sort((a,b) => b.connections - a.connections).slice(0, 5);

  const metric = (value: number) => graphLoaded ? value : loading ? '…' : '—';

  return (
    <div className={`graph-workspace graph-first-workspace investigation-map-layout ${expanded ? 'is-expanded' : ''}`}>
      {/* Floating Panel Toggle Button when sidebar is collapsed */}
      {sidebarCollapsed && !expanded && (
        <button
          className="graph-panel-toggle-btn"
          onClick={() => setSidebarCollapsed(false)}
          title="Open Controls Panel"
          aria-label="Open Controls Panel"
        >
          <GraphControlIcon kind="sliders" />
          <span>Show Controls</span>
        </button>
      )}

      {/* Collapsible Left Panel */}
      <aside className={`network-information ${sidebarCollapsed ? 'is-collapsed' : ''}`} aria-label="Network information">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-faint)' }}>
            Investigation Console
          </span>
          <button
            className="neu-btn ghost"
            style={{ padding: '3px 8px', fontSize: '10.5px' }}
            onClick={() => setSidebarCollapsed(true)}
            title="Collapse panel to maximize canvas"
          >
            <GraphControlIcon kind="chevron_left" />
            <span>Collapse</span>
          </button>
        </div>

        <div className="network-stat-grid">
          {[
            ['Entities', entityNodes.length],
            ['Relationships', graphEdges.length],
            ['Source records', sourceCount],
            ['Entity types', Object.keys(nodeCounts).filter(type => !['Case', 'SourceRecord'].includes(type)).length]
          ].map(([label, value]) => (
            <section className="network-stat-card" key={label}>
              <h2>{label}</h2>
              <strong>{metric(Number(value))}</strong>
            </section>
          ))}
        </div>

        <section className="network-information-card">
          <h2>Investigation scope</h2>
          <label htmlFor="graph-case-filter">Case</label>
          <select id="graph-case-filter" className="control" value={caseFilter} onChange={e => { setCaseFilter(e.target.value); setSelectedCase(e.target.value || null); }}>
            <option value="">All visible cases</option>
            {cases.map(c => <option key={c.case_id} value={c.case_id}>{c.case_name || c.case_id}</option>)}
          </select>

          <div style={{ marginTop: '10px' }}>
            <label style={{ marginBottom: '5px', display: 'block', fontSize: '11px', fontWeight: 600 }}>Graph Mode</label>
            <div className="graph-mode-pill-toggle" style={{ width: '100%', display: 'flex', borderRadius: '8px' }}>
              <button
                type="button"
                className={`neu-btn ${presentationMode === 'structured' ? 'primary is-active' : 'ghost'}`}
                style={{ flex: 1, justifyContent: 'center', borderRadius: '6px', padding: '5px 8px' }}
                onClick={() => setPresentationMode('structured')}
                title="Structured View: Clean aligned hierarchical tiers"
              >
                Structured
              </button>
              <button
                type="button"
                className={`neu-btn ${presentationMode === 'investigation' ? 'primary is-active' : 'ghost'}`}
                style={{ flex: 1, justifyContent: 'center', borderRadius: '6px', padding: '5px 8px' }}
                onClick={() => setPresentationMode('investigation')}
                title="Investigation View: Free-form physics exploration"
              >
                Investigation
              </button>
            </div>
          </div>

          <label htmlFor="graph-view-mode" style={{ marginTop: '10px' }}>Network Filter</label>
          <select id="graph-view-mode" className="control" value={graphType} onChange={e => setGraphType(e.target.value)}>
            <option value="focused">Focused View (Default)</option>
            <option value="all">Full Network View</option>
            <option value="cdr">People & Calls View</option>
            <option value="vehicle">Vehicle & Location View</option>
            <option value="financial">Financial View</option>
            <option value="case_context">Case Context View</option>
          </select>

          <label htmlFor="graph-search" style={{ marginTop: '10px' }}>Find in Network</label>
          <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '4px', margin: '4px 0 0 0' }}>
            <input
              id="graph-search"
              type="text"
              className="control"
              placeholder="Name, phone, plate, ID…"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setSearchIndex(0); }}
              style={{ flex: 1, fontSize: '11px', padding: '6px 8px' }}
            />
            <button type="submit" className="neu-btn ghost" style={{ padding: '4px 8px', fontSize: '11px' }} title="Find / Next match">
              Find
            </button>
          </form>
          {matchingNodes.length > 0 && (
            <p className="workspace-muted" style={{ margin: '4px 0 0 0', fontSize: '10.5px' }}>
              {matchingNodes.length} match{matchingNodes.length > 1 ? 'es' : ''} (click Find to cycle)
            </p>
          )}

          {/* Core Visual Toggles */}
          <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-faint)', fontWeight: 700 }}>
              Display Toggles
            </span>
            <label htmlFor="toggle-all-labels" style={{ margin: 0, fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                id="toggle-all-labels"
                type="checkbox"
                checked={showAllLabels}
                onChange={e => setShowAllLabels(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <span>Show all node labels</span>
            </label>

            <label htmlFor="toggle-edge-labels" style={{ margin: 0, fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                id="toggle-edge-labels"
                type="checkbox"
                checked={showEdgeLabels}
                onChange={e => setShowEdgeLabels(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <span>Show edge labels</span>
            </label>

            <label htmlFor="toggle-case-nodes" style={{ margin: 0, fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                id="toggle-case-nodes"
                type="checkbox"
                checked={showCaseNodes}
                onChange={e => setShowCaseNodes(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <span>Show case & evidence nodes</span>
            </label>

            <label htmlFor="toggle-isolated" style={{ margin: 0, fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                id="toggle-isolated"
                type="checkbox"
                checked={showIsolated}
                onChange={e => setShowIsolated(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <span>Show isolated nodes ({totalIsolatedCount})</span>
            </label>
          </div>


          <div className="network-scope-footer" style={{ marginTop: '10px' }}>
            <span>Clean, compact layout</span>
            <button className="neu-btn ghost" disabled={loading} onClick={fetchGraph}>{loading ? 'Loading…' : 'Refresh'}</button>
          </div>
          {graphError && graphLoaded && <p className="workspace-muted">Previously loaded counts may be outdated.</p>}
        </section>

        {/* Record Types with Clickable Filters */}
        <section className="network-information-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <h2 style={{ margin: 0 }}>Record types</h2>
            {hiddenTypes.size > 0 && (
              <button
                className="neu-btn ghost"
                style={{ padding: '2px 6px', fontSize: '10px' }}
                onClick={() => setHiddenTypes(new Set())}
              >
                Reset filters
              </button>
            )}
          </div>
          {!graphLoaded ? (
            <p className="workspace-muted">{loading ? 'Loading network…' : 'Network unavailable.'}</p>
          ) : Object.keys(nodeCounts).length ? (
            <div className="network-type-list">
              {Object.entries(nodeCounts).map(([type, count]) => {
                const isHidden = hiddenTypes.has(type);
                const category = getEntityCategory([type]);
                const palette = getNodePalette(category, theme !== 'dark');
                return (
                  <div
                    key={type}
                    onClick={() => {
                      setHiddenTypes(prev => {
                        const next = new Set(prev);
                        if (next.has(type)) next.delete(type);
                        else next.add(type);
                        return next;
                      });
                    }}
                    style={{
                      cursor: 'pointer',
                      opacity: isHidden ? 0.35 : 1.0,
                      textDecoration: isHidden ? 'line-through' : 'none',
                      padding: '4px 6px',
                      borderRadius: '6px',
                      background: isHidden ? 'transparent' : 'rgba(255,255,255,0.03)',
                      transition: 'all 0.15s ease'
                    }}
                    title={isHidden ? `Click to reveal ${type} entities` : `Click to filter out ${type} entities`}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                      <span
                        style={{
                          width: '18px',
                          height: '18px',
                          borderRadius: '50%',
                          background: palette.bg,
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0
                        }}
                      >
                        <EntityIcon category={category} size={11} color="#FFFFFF" />
                      </span>
                      {type}
                    </span>
                    <strong>
                      {count}
                      {isHidden && <span style={{ fontSize: '9px', marginLeft: '4px', opacity: 0.7 }}>(hidden)</span>}
                    </strong>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="workspace-muted">No entity types returned.</p>
          )}
        </section>

        {/* Key Connected Entities */}
        <section className="network-information-card">
          <h2>Key connected entities</h2>
          <p className="network-card-caption">Core hubs in this network; click to focus and inspect sources.</p>
          {!graphLoaded ? (
            <p className="workspace-muted">{loading ? 'Loading connections…' : 'Connections unavailable.'}</p>
          ) : connectedEntities.length ? (
            connectedEntities.map(({ node, connections }) => (
              <button className="network-entity-row" key={node.id} onClick={() => focusNode(node)}>
                <span>{node.name || node.id}</span>
                <strong>{connections}<span className="sr-only"> connections</span></strong>
              </button>
            ))
          ) : (
            <p className="workspace-muted">No connected entities returned.</p>
          )}
        </section>
      </aside>

      {/* Full-Bleed Edge-to-Edge Graph Canvas Card */}
      <div className="graph-explorer-card">
        <div id="graph" ref={graphStageRef}>
          {graphError && (
            <div className="workspace-error-panel graph-status-notice" role="alert">
              <div>
                <strong>{graphError}</strong>
                {graphLoaded && <p>Previously loaded network may be outdated.</p>}
              </div>
              <button className="neu-btn ghost" onClick={fetchGraph}>Retry</button>
            </div>
          )}

          {/* Action Toolbar: Mode Switcher, Focus, Fit, Reset View, Expand Canvas */}
          <div className="graph-canvas-actions" aria-label="Canvas controls">
            {/* Segmented Mode Toggle: Structured View vs Investigation View */}
            <div className="graph-mode-pill-toggle" role="group" aria-label="Graph display mode">
              <button
                type="button"
                className={`neu-btn ${presentationMode === 'structured' ? 'primary is-active' : 'ghost'} graph-icon-action`}
                onClick={() => setPresentationMode('structured')}
                title="Structured View: Clean aligned hierarchical lanes"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <line x1="3" y1="12" x2="21" y2="12" />
                  <line x1="3" y1="18" x2="21" y2="18" />
                </svg>
                <span>Structured View</span>
              </button>
              <button
                type="button"
                className={`neu-btn ${presentationMode === 'investigation' ? 'primary is-active' : 'ghost'} graph-icon-action`}
                onClick={() => setPresentationMode('investigation')}
                title="Investigation View: Free-form physics and network exploration"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="3" />
                  <circle cx="19" cy="5" r="2" />
                  <circle cx="5" cy="19" r="2" />
                  <line x1="14" y1="10" x2="17.5" y2="6.5" />
                  <line x1="10" y1="14" x2="6.5" y2="17.5" />
                </svg>
                <span>Investigation View</span>
              </button>
            </div>

            {selectedNode && (
              <>
                <button
                  className="neu-btn ghost graph-icon-action"
                  aria-label="Focus Selection"
                  onClick={handleFocusSelection}
                  title="Focus on selected node"
                >
                  <GraphControlIcon kind="focus" />
                  <span>Focus Selection</span>
                </button>
                <button
                  className="neu-btn primary graph-icon-action"
                  aria-label="Expand Neighbors"
                  disabled={expanding}
                  onClick={handleExpandNeighbors}
                  title={`Expand 1-hop connected neighbors of ${selectedNode.name || selectedNode.id}`}
                  style={{ fontWeight: 600 }}
                >
                  <GraphControlIcon kind="plus_circle" />
                  <span>{expanding ? 'Expanding…' : '+ Expand Neighbors'}</span>
                </button>
              </>
            )}

            {presentationMode === 'structured' ? (
              <button
                className="neu-btn ghost graph-icon-action"
                aria-label="Fit Structured Graph"
                title="Fit aligned structured tiers neatly in viewport"
                onClick={handleFitStructured}
              >
                <GraphControlIcon kind="fit" />
                <span>Fit Structured</span>
              </button>
            ) : (
              <button
                className="neu-btn ghost graph-icon-action"
                aria-label="Fit All"
                title="Fit all nodes into view"
                onClick={handleFitNetwork}
              >
                <GraphControlIcon kind="fit" />
                <span>Fit All</span>
              </button>
            )}

            <button
              className="neu-btn ghost graph-icon-action"
              aria-label="Reset Layout"
              title={presentationMode === 'structured' ? "Reset structured layout to center" : "Center primary network at comfortable zoom"}
              onClick={handleResetView}
            >
              <GraphControlIcon kind="reset" />
              <span>Reset Layout</span>
            </button>

            <button
              className={`neu-btn ${showAllLabels ? 'primary' : 'ghost'} graph-icon-action`}
              aria-label="Toggle Labels"
              aria-pressed={showAllLabels}
              title={showAllLabels ? 'Hide non-essential labels' : 'Show all node labels on canvas'}
              onClick={() => setShowAllLabels(v => !v)}
            >
              <GraphControlIcon kind="labels" />
              <span>{showAllLabels ? 'Labels: All' : 'Labels'}</span>
            </button>

            <button
              className="neu-btn ghost graph-icon-action"
              aria-label={aiPanelCollapsed ? 'Open Copilot' : 'Hide Copilot'}
              aria-expanded={!aiPanelCollapsed}
              aria-controls="graph-copilot"
              onClick={() => setAiPanelCollapsed(value => !value)}
            >
              <GraphControlIcon kind="copilot" />
              <span>{aiPanelCollapsed ? 'Open Copilot' : 'Hide Copilot'}</span>
            </button>

            {/* Whole Page Expanded Canvas Button */}
            <button
              className={`neu-btn ${expanded ? 'primary' : 'ghost'} graph-icon-action`}
              aria-label={expanded ? 'Exit full screen' : 'Expand to full screen'}
              aria-pressed={expanded}
              title={expanded ? 'Exit full screen (ESC)' : 'Open graph on whole page (Fullscreen)'}
              onClick={() => setExpanded(value => !value)}
            >
              <GraphControlIcon kind={expanded ? 'compress' : 'expand'} />
              <span>{expanded ? 'Exit Fullscreen' : 'Expand Canvas'}</span>
            </button>

            {/* Quick Canvas Legend Toggle */}
            <button
              className={`neu-btn ${showCanvasLegend ? 'primary' : 'ghost'} graph-icon-action`}
              aria-label="Toggle Legend"
              aria-pressed={showCanvasLegend}
              title="Toggle floating legend on canvas"
              onClick={() => setShowCanvasLegend(v => !v)}
            >
              <GraphControlIcon kind="legend" />
              <span>Legend</span>
            </button>
          </div>

          {/* Floating Canvas Legend Overlay */}
          {showCanvasLegend && (
            <div
              style={{
                position: 'absolute',
                bottom: '16px',
                left: '16px',
                zIndex: 15,
                background: theme !== 'dark' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(15, 23, 42, 0.95)',
                backdropFilter: 'blur(8px)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                padding: '10px 12px',
                boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
                width: '260px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text)' }}>
                  Entity Legend
                </span>
                <button
                  type="button"
                  onClick={() => setShowCanvasLegend(false)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', fontSize: '12px', padding: '0 4px' }}
                >
                  ✕
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                {ENTITY_LEGEND_CONFIG.map(item => (
                  <div key={item.type} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10.5px' }}>
                    <span
                      style={{
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        background: item.color,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0
                      }}
                    >
                      <EntityIcon category={item.category} size={11} color="#FFFFFF" />
                    </span>
                    <span style={{ color: 'var(--text)' }}>{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pan & Zoom Navigation Controls */}
          <nav className="graph-map-controls" aria-label="Network pan and zoom">
            <div className="graph-pan-controls">
              {(['up', 'left', 'right', 'down'] as const).map(direction => (
                <button
                  key={direction}
                  className={`graph-pan-${direction}`}
                  aria-label={`Pan ${direction}`}
                  title={`Pan ${direction}`}
                  disabled={!graphLoaded || loading}
                  onClick={() => {
                    const network = networkRef.current;
                    if (!network) return;
                    const position = network.getViewPosition();
                    const step = 80 / network.getScale();
                    network.moveTo({
                      position: {
                        x: position.x + (direction === 'left' ? -step : direction === 'right' ? step : 0),
                        y: position.y + (direction === 'up' ? -step : direction === 'down' ? step : 0)
                      },
                      animation: false
                    });
                  }}
                >
                  <GraphControlIcon kind={direction} />
                </button>
              ))}
            </div>
            <div className="graph-zoom-controls">
              {([['plus', 'Zoom in', 1.2], ['minus', 'Zoom out', 1 / 1.2]] as const).map(([kind, label, factor]) => (
                <button
                  key={kind}
                  aria-label={label}
                  title={label}
                  disabled={!graphLoaded || loading}
                  onClick={() => {
                    const network = networkRef.current;
                    if (network) network.moveTo({ scale: Math.max(0.1, Math.min(5, network.getScale() * factor)), animation: false });
                  }}
                >
                  <GraphControlIcon kind={kind} />
                </button>
              ))}
            </div>
          </nav>

          {!loading && !graphLoaded && graphError && (
            <div className="graph-canvas-message" role="status">Network unavailable. Use Retry to load your records.</div>
          )}
          {!loading && graphLoaded && !graphNodes.length && !graphError && (
            <div className="graph-canvas-message" role="status">No network records returned for the selected scope.</div>
          )}
          {loading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3.5 z-10" style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '11px', color: 'var(--text-dim)', background: 'var(--graph-bg)', zIndex: 10 }}>
              <div className="status-dot" style={{ width: '14px', height: '14px', background: 'var(--accent)', animation: 'pulse 1s infinite' }}></div>
              <div style={{ fontSize: '11px' }}>Stabilizing compact network layout…</div>
            </div>
          )}
          <div id="graphCanvas" ref={containerRef}></div>

          {/* AI Copilot Side Structure */}
          <div id="graph-copilot" className={`graph-ai-box ${aiPanelCollapsed ? 'collapsed' : ''}`}>
            <div className="graph-ai-header flex items-center justify-between">
              <div className="flex items-center gap-1.5" style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" /></svg>
                <span className="font-bold text-xs" style={{ fontWeight: 700, fontSize: '11px', color: 'var(--text)' }}>AI Copilot</span>
                <span className="tag open" style={{ padding: '1px 6px', fontSize: '9.5px', textTransform: 'uppercase' }}>AI Inference</span>
              </div>
              <button className="neu-btn ghost transition" style={{ padding: '2px 7px', fontSize: '11px' }} aria-label="Close AI Copilot" onClick={() => setAiPanelCollapsed(true)}>✕</button>
            </div>

            <div className="graph-ai-body" ref={aiBodyRef}>
              {aiChatLog.map((msg, idx) => (
                <div key={idx} className={`ai-msg ${msg.sender === 'user' ? 'user' : 'bot'}`} style={msg.error ? { borderColor: 'rgba(48,58,54,0.4)' } : {}}>
                  <div className="ai-msg-hdr flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" /></svg>
                    <span>{msg.sender === 'user' ? 'Investigator Query' : (msg.model || 'AI Copilot')}</span>
                  </div>
                  {msg.sender === 'user' ? (
                    <div style={{ color: 'var(--text)' }}>{msg.content}</div>
                  ) : (
                    <FormattedAiMessage content={msg.content} />
                  )}
                  {msg.chips && (
                    <div className="ai-quick-chips flex flex-wrap gap-1.5 mt-2">
                      {msg.chips.map((c, cIdx) => (
                        <button key={cIdx} type="button" className="ai-chip transition" onClick={() => handleAiQuerySubmit(null, c.replace(/^[^a-zA-Z0-9]+/, ''))}>
                          {c}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {aiQuerying && (
                <div className="ai-msg bot">
                  <div className="ai-msg-hdr flex items-center gap-1.5">
                    <div className="status-dot" style={{ width: '8px', height: '8px', background: 'var(--accent)', animation: 'pulse 1s infinite' }}></div>
                    <span>AI is analyzing topology…</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-faint)' }}>Correlating nodes, transactions, and hidden links</div>
                </div>
              )}
            </div>

            <div className="graph-ai-footer">
              <form onSubmit={handleAiQuerySubmit} className="flex gap-1.5 w-full m-0" style={{ display: 'flex', gap: '6px', width: '100%', margin: 0 }}>
                <input type="text" className="control" style={{ fontSize: '11px', padding: '7px 10px', flex: 1 }} placeholder="Ask about this network…" value={aiInput} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAiInput(e.target.value)} />
                <button type="submit" className="neu-btn primary transition" disabled={aiQuerying} style={{ padding: '0 10px', fontSize: '11px' }}>{aiQuerying ? '…' : 'Ask'}</button>
              </form>
            </div>
          </div>
        </div>
      </div>

      {selectedNode && (
        <WorkspaceDetails
          title={selectedNode.name || 'Entity details'}
          record={selectedNode as unknown as Record<string, unknown>}
          allowedCaseIds={cases.map(c => c.case_id)}
          activeCaseId={caseFilter || selectedCase || (cases[0]?.case_id ?? '')}
          onClose={() => {
            setSelectedNode(null);
            applyNeighborhoodHighlight(null);
          }}
          onFindingAdded={(msg) => addToast(msg, 'ok')}
        />
      )}
      {selectedRelationship && (
        <WorkspaceDetails
          title={`Relationship: ${selectedRelationship.type || 'Connection'}`}
          record={{
            ...selectedRelationship.properties,
            from: selectedRelationship.source,
            to: selectedRelationship.target,
            relationship_type: selectedRelationship.type
          }}
          allowedCaseIds={cases.map(c => c.case_id)}
          activeCaseId={caseFilter || selectedCase || (cases[0]?.case_id ?? '')}
          onClose={() => {
            setSelectedRelationship(null);
            applyNeighborhoodHighlight(null);
          }}
          onFindingAdded={(msg) => addToast(msg, 'ok')}
        />
      )}
    </div>
  );
}
