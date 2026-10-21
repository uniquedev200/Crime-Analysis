import React, { memo } from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

export interface ManualEntityData {
  label: string;
  category: 'Person' | 'Phone' | 'Device' | 'Vehicle' | 'Bank Account' | 'Location' | 'Organization' | 'Other';
  description?: string;
  notes?: string;
  [key: string]: unknown;
}

export const CATEGORY_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  Person: { bg: '#10B981', border: '#059669', label: 'Person' },
  Phone: { bg: '#F97316', border: '#EA580C', label: 'Phone' },
  Device: { bg: '#3B82F6', border: '#2563EB', label: 'Device / IMEI' },
  Vehicle: { bg: '#8B5CF6', border: '#7C3AED', label: 'Vehicle' },
  'Bank Account': { bg: '#14B8A6', border: '#0D9488', label: 'Bank Account' },
  Location: { bg: '#64748B', border: '#475569', label: 'Location' },
  Organization: { bg: '#F59E0B', border: '#D97706', label: 'Organization' },
  Other: { bg: '#6B7280', border: '#4B5563', label: 'Other' }
};

export function renderNodeIcon(category: string) {
  switch (category) {
    case 'Person':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
        </svg>
      );
    case 'Phone':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z" />
        </svg>
      );
    case 'Device':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path fillRule="evenodd" d="M7 2a2 2 0 00-2 2v12a2 2 0 002 2h6a2 2 0 002-2V4a2 2 0 00-2-2H7zm3 14a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
        </svg>
      );
    case 'Vehicle':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 text-white">
          <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.5 2.8C2.1 10.9 2 11.2 2 11.5V16c0 .6.4 1 1 1h2" />
          <circle cx="7" cy="17" r="2" />
          <path d="M9 17h6" />
          <circle cx="17" cy="17" r="2" />
        </svg>
      );
    case 'Bank Account':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" />
          <path fillRule="evenodd" d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z" clipRule="evenodd" />
        </svg>
      );
    case 'Location':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
        </svg>
      );
    case 'Organization':
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a1 1 0 110 2h-3a1 1 0 01-1-1v-2a1 1 0 00-1-1H9a1 1 0 00-1 1v2a1 1 0 01-1 1H4a1 1 0 110-2V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9z" clipRule="evenodd" />
        </svg>
      );
    case 'Other':
    default:
      return (
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
        </svg>
      );
  }
}

export const ManualEntityNode = memo(({ data, selected }: NodeProps) => {
  const nodeData = data as unknown as ManualEntityData;
  const category = nodeData?.category || 'Other';
  const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.Other;
  const label = nodeData?.label || 'Entity';

  // Compact label display
  const displayLabel = label.length > 14 ? `${label.slice(0, 13)}…` : label;

  return (
    <div className={`manual-board-node-wrapper ${selected ? 'is-selected' : ''}`} title={`${label} (${category})`}>
      {/* 28px Circle with Handles attached directly to the circle */}
      <div
        className="manual-board-circle"
        style={{
          backgroundColor: color.bg,
          borderColor: color.border
        }}
      >
        <Handle type="target" position={Position.Top} id="top" className="board-circle-handle top" />
        <Handle type="source" position={Position.Right} id="right" className="board-circle-handle right" />
        <Handle type="source" position={Position.Bottom} id="bottom" className="board-circle-handle bottom" />
        <Handle type="target" position={Position.Left} id="left" className="board-circle-handle left" />

        {renderNodeIcon(category)}
      </div>

      {/* Compact Label pill underneath */}
      <div className="manual-board-label-pill">
        <span className="manual-board-label-text">{displayLabel}</span>
      </div>
    </div>
  );
});
