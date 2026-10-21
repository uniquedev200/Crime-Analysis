import React, { memo } from 'react';
import { NodeProps } from '@xyflow/react';

export interface StickyNoteData {
  text: string;
  color?: string; // 'yellow' | 'blue' | 'pink' | 'neutral'
  author?: string;
  createdAt?: string;
  [key: string]: unknown;
}

export const StickyNoteNode = memo(({ data, selected }: NodeProps) => {
  const noteData = data as unknown as StickyNoteData;
  const text = noteData?.text || 'Type your investigative note or hypothesis here...';
  const color = noteData?.color || 'yellow';

  const colorStyles: Record<string, { bg: string; border: string; header: string }> = {
    yellow: { bg: '#FEF3C7', border: '#F59E0B', header: '#D97706' },
    blue: { bg: '#E0F2FE', border: '#0284C7', header: '#0369A1' },
    pink: { bg: '#FCE7F3', border: '#DB2777', header: '#BE185D' },
    neutral: { bg: '#F1F5F8', border: '#94A3B8', header: '#475569' }
  };

  const currentTheme = colorStyles[color] || colorStyles.yellow;

  return (
    <div
      className={`manual-sticky-note-card ${selected ? 'is-selected' : ''}`}
      style={{
        backgroundColor: currentTheme.bg,
        borderColor: currentTheme.border
      }}
    >
      <div className="sticky-note-header" style={{ color: currentTheme.header }}>
        <span className="flex items-center gap-1 font-bold text-[10px] uppercase tracking-wider">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
          Note / Hypothesis
        </span>
      </div>
      <div className="sticky-note-body">
        <p className="text-xs text-slate-800 leading-snug whitespace-pre-wrap select-none font-medium">
          {text}
        </p>
      </div>
    </div>
  );
});
