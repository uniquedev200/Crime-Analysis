import React, { memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  useInternalNode,
  useReactFlow
} from '@xyflow/react';

export interface ManualEdgeData {
  label?: string;
  style?: 'solid' | 'dashed';
  is_directional?: boolean;
  notes?: string;
  [key: string]: unknown;
}

export const ManualEdge = memo(({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  selected,
  markerEnd
}: EdgeProps) => {
  const edgeData = data as unknown as ManualEdgeData;
  const label = edgeData?.label || '';
  const isDashed = edgeData?.style === 'dashed';

  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const { setEdges, setNodes } = useReactFlow();

  let sx = sourceX;
  let sy = sourceY;
  let tx = targetX;
  let ty = targetY;

  // Calculate clean circle-to-circle perimeter coordinates
  if (sourceNode && targetNode) {
    const isSourceCircle = sourceNode.type === 'manualEntity';
    const isTargetCircle = targetNode.type === 'manualEntity';

    const sourcePos = sourceNode.internals?.positionAbsolute || sourceNode.position || { x: sourceX, y: sourceY };
    const targetPos = targetNode.internals?.positionAbsolute || targetNode.position || { x: targetX, y: targetY };

    const sourceWidth = sourceNode.measured?.width ?? 28;
    const targetWidth = targetNode.measured?.width ?? 28;

    // Center of 28px circle is at x = width / 2, y = 14
    const sourceCenterX = isSourceCircle ? sourcePos.x + sourceWidth / 2 : sourceX;
    const sourceCenterY = isSourceCircle ? sourcePos.y + 14 : sourceY;

    const targetCenterX = isTargetCircle ? targetPos.x + targetWidth / 2 : targetX;
    const targetCenterY = isTargetCircle ? targetPos.y + 14 : targetY;

    const dx = targetCenterX - sourceCenterX;
    const dy = targetCenterY - sourceCenterY;
    const dist = Math.hypot(dx, dy);

    if (dist > 0) {
      const sourceRadius = isSourceCircle ? 14 : 0;
      const targetRadius = isTargetCircle ? 14 : 0;

      if (dist > sourceRadius + targetRadius) {
        sx = sourceCenterX + (dx / dist) * sourceRadius;
        sy = sourceCenterY + (dy / dist) * sourceRadius;
        tx = targetCenterX - (dx / dist) * targetRadius;
        ty = targetCenterY - (dy / dist) * targetRadius;
      }
    }
  }

  const edgePath = `M ${sx} ${sy} L ${tx} ${ty}`;
  const midX = (sx + tx) / 2;
  const midY = (sy + ty) / 2;

  // Angle along the line so label rotates parallel to the edge (matching Image 2)
  const dx = tx - sx;
  const dy = ty - sy;
  let angle = Math.atan2(dy, dx) * (180 / Math.PI);
  if (angle > 90 || angle < -90) {
    angle += 180;
  }

  const onLabelClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNodes((nds) => nds.map((n) => ({ ...n, selected: false })));
    setEdges((eds) => eds.map((edge) => ({ ...edge, selected: edge.id === id })));
  };

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: selected ? '#2563EB' : '#475569',
          strokeWidth: selected ? 2.2 : 1.6,
          strokeDasharray: isDashed ? '5,4' : undefined,
          transition: 'stroke 0.15s ease, stroke-width 0.15s ease'
        }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(${midX}px, ${midY}px) translate(-50%, -50%) rotate(${angle}deg)`,
              pointerEvents: 'all'
            }}
            className={`manual-board-edge-label ${selected ? 'is-selected' : ''}`}
            title={label}
            onClick={onLabelClick}
          >
            <span>{label}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
