import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  Node,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
  Viewport,
  ConnectionMode
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './board/board.css';

import { ManualEntityNode, ManualEntityData, CATEGORY_COLORS, renderNodeIcon } from './board/ManualEntityNode';
import { StickyNoteNode, StickyNoteData } from './board/StickyNoteNode';
import { ManualEdge, ManualEdgeData } from './board/ManualEdge';
import { API, Case, OfficerSession } from '../services/api';

// Pre-register node and edge types outside component to prevent re-mount loops
const nodeTypes = {
  manualEntity: ManualEntityNode,
  stickyNote: StickyNoteNode,
};

const edgeTypes = {
  manualEdge: ManualEdge,
};

export interface InvestigationBoardRecord {
  board_id: string;
  case_id: string;
  title: string;
  creator_id?: string;
  creator_name?: string;
  creator_badge?: string;
  nodes: Node[];
  edges: Edge[];
  notes?: Record<string, unknown>[];
  viewport?: Viewport;
  created_at?: string;
  updated_at?: string;
}

interface InvestigationBoardModuleProps {
  cases: Case[];
  selectedCase?: string | null;
  onSelectCase?: (caseId: string) => void;
  officerSession?: OfficerSession | null;
  addToast: (msg: string, type?: string) => void;
  changeView?: (id: string) => void;
}

interface HistorySnapshot {
  nodes: Node[];
  edges: Edge[];
}

function InvestigationBoardInner({
  cases,
  selectedCase,
  onSelectCase,
  officerSession,
  addToast,
}: InvestigationBoardModuleProps) {
  const { zoomIn, zoomOut, fitView, screenToFlowPosition, getViewport, setViewport } = useReactFlow();

  // Active case ID
  const activeCaseId = selectedCase || (cases.length > 0 ? cases[0].case_id : 'case_01');

  // Board list & current active board
  const [boards, setBoards] = useState<InvestigationBoardRecord[]>([]);
  const [activeBoardId, setActiveBoardId] = useState<string | null>(null);
  const [boardTitle, setBoardTitle] = useState<string>('Primary Investigation Board');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [lastSavedTime, setLastSavedTime] = useState<string | null>(null);

  // Nodes & Edges state
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Selection state
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);

  // Modals
  const [showAddNodeModal, setShowAddNodeModal] = useState<boolean>(false);
  const [showAddConnectionModal, setShowAddConnectionModal] = useState<boolean>(false);
  const [showNewBoardModal, setShowNewBoardModal] = useState<boolean>(false);

  // New Node Form State
  const [newNodeLabel, setNewNodeLabel] = useState<string>('');
  const [newNodeCategory, setNewNodeCategory] = useState<ManualEntityData['category']>('Person');
  const [newNodeDesc, setNewNodeDesc] = useState<string>('');

  // New Connection Form State
  const [connSource, setConnSource] = useState<string>('');
  const [connTarget, setConnTarget] = useState<string>('');
  const [connLabel, setConnLabel] = useState<string>('Suspected Associate');
  const [connStyle, setConnStyle] = useState<'solid' | 'dashed'>('solid');
  const [connDirectional, setConnDirectional] = useState<boolean>(true);

  // New Board Form State
  const [newBoardTitle, setNewBoardTitle] = useState<string>('');

  // Undo / Redo history stacks
  const historyPast = useRef<HistorySnapshot[]>([]);
  const historyFuture = useRef<HistorySnapshot[]>([]);
  const isHistoryAction = useRef<boolean>(false);

  // Push snapshot to undo stack
  const pushHistorySnapshot = useCallback(() => {
    if (isHistoryAction.current) return;
    historyPast.current.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    });
    // Keep max 25 history states
    if (historyPast.current.length > 25) {
      historyPast.current.shift();
    }
    historyFuture.current = [];
  }, [nodes, edges]);

  const undo = useCallback(() => {
    if (historyPast.current.length === 0) return;
    isHistoryAction.current = true;
    const previous = historyPast.current.pop()!;
    historyFuture.current.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    });
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setSelectedNode(null);
    setSelectedEdge(null);
    setTimeout(() => {
      isHistoryAction.current = false;
    }, 50);
  }, [nodes, edges, setNodes, setEdges]);

  const redo = useCallback(() => {
    if (historyFuture.current.length === 0) return;
    isHistoryAction.current = true;
    const next = historyFuture.current.pop()!;
    historyPast.current.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    });
    setNodes(next.nodes);
    setEdges(next.edges);
    setSelectedNode(null);
    setSelectedEdge(null);
    setTimeout(() => {
      isHistoryAction.current = false;
    }, 50);
  }, [nodes, edges, setNodes, setEdges]);

  // Load Boards for Case
  const loadBoardsForCase = useCallback(async (caseId: string) => {
    setIsLoading(true);
    try {
      const res = await API.get<{ total: number; boards: InvestigationBoardRecord[] }>(
        `/api/boards?case_id=${encodeURIComponent(caseId)}`
      );
      if (res && res.boards) {
        setBoards(res.boards);
        if (res.boards.length > 0) {
          const current = res.boards[0];
          setActiveBoardId(current.board_id);
          setBoardTitle(current.title || 'Manual Investigation Board');
          // Fetch full board detail from backend to ensure nodes and edges are 100% loaded
          try {
            const detail = await API.get<InvestigationBoardRecord>(`/api/boards/${current.board_id}`);
            if (detail && Array.isArray(detail.edges)) {
              setNodes(detail.nodes || []);
              setEdges(detail.edges || []);
            } else {
              setNodes(current.nodes || []);
              setEdges(current.edges || []);
            }

            // Restore officer's saved viewport (pan and zoom level)
            let targetVp = detail?.viewport || current?.viewport;
            const savedVp = localStorage.getItem(`atlas_board_vp_${current.board_id}`);
            if (savedVp) {
              try {
                const parsed = JSON.parse(savedVp);
                if (parsed && typeof parsed.zoom === 'number') targetVp = parsed;
              } catch {}
            }
            if (targetVp && typeof targetVp.zoom === 'number' && targetVp.zoom > 0) {
              setTimeout(() => {
                setViewport(targetVp, { duration: 0 });
              }, 60);
            } else {
              setTimeout(() => fitView({ padding: 0.2 }), 80);
            }
          } catch {
            setNodes(current.nodes || []);
            setEdges(current.edges || []);
            setTimeout(() => fitView({ padding: 0.2 }), 80);
          }
          historyPast.current = [];
          historyFuture.current = [];
        } else {
          // Auto create initial default board for this case
          const created = await API.post<InvestigationBoardRecord>('/api/boards', {
            case_id: caseId,
            title: `Investigation Board — ${caseId.toUpperCase()}`,
            creator_name: officerSession?.officerName || 'Investigating Officer',
            creator_badge: officerSession?.badgeNumber || 'IND-LE-8402',
            initial_nodes: [
              {
                id: 'node-seed-1',
                type: 'manualEntity',
                position: { x: 300, y: 220 },
                width: 44,
                height: 44,
                data: {
                  label: 'Primary Subject',
                  category: 'Person',
                  description: 'Manual initial hypothesis subject'
                }
              },
              {
                id: 'note-seed-1',
                type: 'stickyNote',
                position: { x: 550, y: 180 },
                width: 140,
                height: 100,
                data: {
                  text: 'Officer Workspace:\nAdd leads, trace bank transfers, or connect burner devices freely without modifying Neo4j graph.',
                  color: 'yellow'
                }
              }
            ],
            initial_edges: []
          });
          setBoards([created]);
          setActiveBoardId(created.board_id);
          setBoardTitle(created.title);
          setNodes(created.nodes || []);
          setEdges(created.edges || []);
          historyPast.current = [];
          historyFuture.current = [];
        }
      }
    } catch (err) {
      console.error('Failed to load investigation boards', err);
      addToast('Unable to load manual boards', 'err');
    } finally {
      setIsLoading(false);
    }
  }, [addToast, officerSession, setNodes, setEdges, setViewport, fitView]);

  useEffect(() => {
    if (activeCaseId) {
      loadBoardsForCase(activeCaseId);
    }
  }, [activeCaseId, loadBoardsForCase]);

  // Switch Active Board
  const handleSelectBoard = useCallback(async (boardId: string) => {
    const found = boards.find(b => b.board_id === boardId);
    if (!found) return;
    setActiveBoardId(found.board_id);
    setBoardTitle(found.title);
    try {
      const detail = await API.get<InvestigationBoardRecord>(`/api/boards/${boardId}`);
      if (detail && Array.isArray(detail.edges)) {
        setNodes(detail.nodes || []);
        setEdges(detail.edges || []);
      } else {
        setNodes(found.nodes || []);
        setEdges(found.edges || []);
      }

      // Restore saved zoom level and pan coordinates
      let targetVp = detail?.viewport || found?.viewport;
      const savedVp = localStorage.getItem(`atlas_board_vp_${boardId}`);
      if (savedVp) {
        try {
          const parsed = JSON.parse(savedVp);
          if (parsed && typeof parsed.zoom === 'number') targetVp = parsed;
        } catch {}
      }
      if (targetVp && typeof targetVp.zoom === 'number' && targetVp.zoom > 0) {
        setTimeout(() => {
          setViewport(targetVp, { duration: 120 });
        }, 50);
      } else {
        setTimeout(() => fitView({ padding: 0.2 }), 80);
      }
    } catch {
      setNodes(found.nodes || []);
      setEdges(found.edges || []);
      setTimeout(() => fitView({ padding: 0.2 }), 80);
    }
    setSelectedNode(null);
    setSelectedEdge(null);
    historyPast.current = [];
    historyFuture.current = [];
  }, [boards, fitView, setNodes, setEdges, setViewport]);

  // Save Current Board
  const handleSaveBoard = useCallback(async () => {
    if (!activeBoardId) return;
    setIsSaving(true);
    try {
      const currentViewport = getViewport();
      // Cache locally immediately so tab switches restore exact state
      localStorage.setItem(`atlas_board_vp_${activeBoardId}`, JSON.stringify(currentViewport));

      const payload = {
        title: boardTitle,
        nodes: nodes,
        edges: edges,
        viewport: currentViewport,
        officer_name: officerSession?.officerName || 'Investigating Officer',
        officer_badge: officerSession?.badgeNumber || 'IND-LE-8402'
      };
      const updated = await API.put<InvestigationBoardRecord>(`/api/boards/${activeBoardId}`, payload);
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      setLastSavedTime(timeStr);
      addToast(`Investigation board saved (${nodes.length} entities, ${edges.length} connections)`, 'success');

      // Update in boards list with saved data
      const savedNodes = (updated && updated.nodes) || nodes;
      const savedEdges = (updated && updated.edges) || edges;
      setBoards(prev => prev.map(b => b.board_id === activeBoardId ? { ...b, title: boardTitle, nodes: savedNodes, edges: savedEdges, viewport: currentViewport } : b));
    } catch (err) {
      console.error('Failed to save board', err);
      addToast('Failed to save investigation board', 'err');
    } finally {
      setIsSaving(false);
    }
  }, [activeBoardId, boardTitle, nodes, edges, officerSession, addToast, getViewport]);

  // Connect handler (drawing line between two handles)
  const onConnect = useCallback((connection: Connection) => {
    pushHistorySnapshot();
    const newEdge: Edge = {
      ...connection,
      id: `edge-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      type: 'manualEdge',
      data: {
        label: 'Connected',
        style: 'solid',
        is_directional: true
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: '#475569'
      }
    };
    setEdges((eds) => addEdge(newEdge, eds));
  }, [pushHistorySnapshot, setEdges]);

  // Add Manual Entity Node
  const handleAddEntityNode = useCallback(() => {
    if (!newNodeLabel.trim()) return;
    pushHistorySnapshot();

    // Spawn at center or reasonable offset
    const id = `node-${Date.now()}`;
    const x = 320 + Math.floor(Math.random() * 80) - 40;
    const y = 200 + Math.floor(Math.random() * 80) - 40;

    const newNode: Node = {
      id,
      type: 'manualEntity',
      position: { x, y },
      width: 44,
      height: 44,
      initialWidth: 44,
      initialHeight: 44,
      data: {
        label: newNodeLabel.trim(),
        category: newNodeCategory,
        description: newNodeDesc.trim(),
        notes: ''
      }
    };

    setNodes((nds) => [...nds, newNode]);
    setShowAddNodeModal(false);
    setNewNodeLabel('');
    setNewNodeDesc('');
    addToast(`Added ${newNodeCategory} node: "${newNode.data.label}"`, 'info');
  }, [newNodeLabel, newNodeCategory, newNodeDesc, pushHistorySnapshot, setNodes, addToast]);

  // Add Sticky Note
  const handleAddStickyNote = useCallback(() => {
    pushHistorySnapshot();
    const id = `note-${Date.now()}`;
    const x = 400 + Math.floor(Math.random() * 60);
    const y = 220 + Math.floor(Math.random() * 60);

    const newNote: Node = {
      id,
      type: 'stickyNote',
      position: { x, y },
      width: 140,
      height: 100,
      initialWidth: 140,
      initialHeight: 100,
      data: {
        text: 'New investigative hypothesis or witness lead...',
        color: 'yellow',
        author: officerSession?.officerName || 'Officer'
      }
    };

    setNodes((nds) => [...nds, newNote]);
    addToast('Added sticky note to canvas', 'info');
  }, [pushHistorySnapshot, setNodes, officerSession, addToast]);

  // Add Connection via Modal
  const handleAddConnectionSubmit = useCallback(() => {
    if (!connSource || !connTarget || connSource === connTarget) {
      addToast('Select two different entities to connect', 'warn');
      return;
    }
    pushHistorySnapshot();
    const newEdge: Edge = {
      id: `edge-${Date.now()}`,
      source: connSource,
      target: connTarget,
      type: 'manualEdge',
      data: {
        label: connLabel.trim(),
        style: connStyle,
        is_directional: connDirectional
      },
      markerEnd: connDirectional ? {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: '#475569'
      } : undefined
    };

    setEdges((eds) => addEdge(newEdge, eds));
    setShowAddConnectionModal(false);
    setConnSource('');
    setConnTarget('');
    addToast('Connection established between entities', 'info');
  }, [connSource, connTarget, connLabel, connStyle, connDirectional, pushHistorySnapshot, setEdges, addToast]);

  // Create New Board
  const handleCreateNewBoard = useCallback(async () => {
    if (!newBoardTitle.trim()) return;
    try {
      const created = await API.post<InvestigationBoardRecord>('/api/boards', {
        case_id: activeCaseId,
        title: newBoardTitle.trim(),
        creator_name: officerSession?.officerName || 'Investigating Officer',
        creator_badge: officerSession?.badgeNumber || 'IND-LE-8402',
        initial_nodes: [],
        initial_edges: []
      });
      setBoards(prev => [created, ...prev]);
      setActiveBoardId(created.board_id);
      setBoardTitle(created.title);
      setNodes([]);
      setEdges([]);
      setShowNewBoardModal(false);
      setNewBoardTitle('');
      addToast(`Created board "${created.title}"`, 'success');
    } catch (err) {
      console.error('Failed to create board', err);
      addToast('Failed to create new board', 'err');
    }
  }, [newBoardTitle, activeCaseId, officerSession, setNodes, setEdges, addToast]);

  // Delete Active Board
  const handleDeleteActiveBoard = useCallback(async () => {
    if (!activeBoardId) return;
    if (boards.length <= 1) {
      addToast('Cannot delete the only board for this case', 'warn');
      return;
    }
    if (!window.confirm(`Delete investigation board "${boardTitle}"? This action is stored in the audit log.`)) {
      return;
    }
    try {
      await API.delete(`/api/boards/${activeBoardId}?officer_name=${encodeURIComponent(officerSession?.officerName || 'Officer')}&officer_badge=${encodeURIComponent(officerSession?.badgeNumber || 'IND-LE-8402')}`);
      addToast(`Board deleted`, 'info');
      const remaining = boards.filter(b => b.board_id !== activeBoardId);
      setBoards(remaining);
      if (remaining.length > 0) {
        handleSelectBoard(remaining[0].board_id);
      }
    } catch (err) {
      console.error('Failed to delete board', err);
      addToast('Failed to delete board', 'err');
    }
  }, [activeBoardId, boards, boardTitle, officerSession, addToast, handleSelectBoard]);

  // Delete Selected Element
  const handleDeleteSelected = useCallback(() => {
    if (selectedNode) {
      pushHistorySnapshot();
      const nodeId = selectedNode.id;
      setNodes(nds => nds.filter(n => n.id !== nodeId));
      setEdges(eds => eds.filter(e => e.source !== nodeId && e.target !== nodeId));
      setSelectedNode(null);
      addToast('Removed element from board', 'info');
    } else if (selectedEdge) {
      pushHistorySnapshot();
      const edgeId = selectedEdge.id;
      setEdges(eds => eds.filter(e => e.id !== edgeId));
      setSelectedEdge(null);
      addToast('Removed connection from board', 'info');
    }
  }, [selectedNode, selectedEdge, pushHistorySnapshot, setNodes, setEdges, addToast]);

  // Update Selected Node properties
  const updateSelectedNodeData = useCallback((updates: Partial<ManualEntityData>) => {
    if (!selectedNode) return;
    pushHistorySnapshot();
    setNodes(nds =>
      nds.map(n => {
        if (n.id === selectedNode.id) {
          const updated = {
            ...n,
            data: {
              ...n.data,
              ...updates
            }
          };
          setSelectedNode(updated);
          return updated;
        }
        return n;
      })
    );
  }, [selectedNode, pushHistorySnapshot, setNodes]);

  // Update Selected Sticky Note properties
  const updateSelectedNoteData = useCallback((updates: Partial<StickyNoteData>) => {
    if (!selectedNode) return;
    pushHistorySnapshot();
    setNodes(nds =>
      nds.map(n => {
        if (n.id === selectedNode.id) {
          const updated = {
            ...n,
            data: {
              ...n.data,
              ...updates
            }
          };
          setSelectedNode(updated);
          return updated;
        }
        return n;
      })
    );
  }, [selectedNode, pushHistorySnapshot, setNodes]);

  // Update Selected Edge properties
  const updateSelectedEdgeData = useCallback((updates: Partial<ManualEdgeData>) => {
    if (!selectedEdge) return;
    pushHistorySnapshot();
    setEdges(eds =>
      eds.map(e => {
        if (e.id === selectedEdge.id) {
          const isDirectional = updates.is_directional !== undefined ? updates.is_directional : (e.data?.is_directional ?? true);
          const updated: Edge = {
            ...e,
            data: {
              ...e.data,
              ...updates
            },
            markerEnd: isDirectional ? {
              type: MarkerType.ArrowClosed,
              width: 14,
              height: 14,
              color: '#475569'
            } : undefined
          };
          setSelectedEdge(updated);
          return updated;
        }
        return e;
      })
    );
  }, [selectedEdge, pushHistorySnapshot, setEdges]);

  // Keyboard Shortcuts (Ctrl+S, Ctrl+Z, Ctrl+Y, Delete/Backspace)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in input or textarea
      const target = e.target as HTMLElement;
      const isInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSaveBoard();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
        if (!isInput) {
          e.preventDefault();
          if (e.shiftKey) {
            redo();
          } else {
            undo();
          }
        }
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y')) {
        if (!isInput) {
          e.preventDefault();
          redo();
        }
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && !isInput) {
        if (selectedNode || selectedEdge) {
          e.preventDefault();
          handleDeleteSelected();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSaveBoard, undo, redo, handleDeleteSelected, selectedNode, selectedEdge]);

  // Selection handlers
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
    setSelectedEdge(null);
  }, []);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  // Filter entity nodes for Add Connection dropdown
  const entityNodes = useMemo(() => {
    return nodes.filter(n => n.type === 'manualEntity');
  }, [nodes]);

  return (
    <div className="investigation-board-shell">
      {/* Top Toolbar Box */}
      <div className="board-toolbar">
        {/* Row 1: Title, Case, New Board & Entities Count Pill */}
        <div className="board-toolbar-row">
          <div className="board-toolbar-group">
            {/* Board Title Input */}
            <input
              type="text"
              className="board-title-input"
              value={boardTitle}
              onChange={(e) => setBoardTitle(e.target.value)}
              title="Click to rename board"
              placeholder="Board Title..."
            />

            {/* Case Selector Dropdown */}
            <select
              className="board-case-select"
              value={activeCaseId}
              onChange={(e) => {
                if (onSelectCase) onSelectCase(e.target.value);
              }}
              title="Switch case scope"
            >
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id.toUpperCase()}{c.case_name ? ` — ${c.case_name}` : ''}
                </option>
              ))}
            </select>

            {/* Boards Switcher */}
            {boards.length > 1 && (
              <select
                className="board-case-select"
                value={activeBoardId || ''}
                onChange={(e) => handleSelectBoard(e.target.value)}
                title="Select saved board"
              >
                {boards.map(b => (
                  <option key={b.board_id} value={b.board_id}>
                    {b.title}
                  </option>
                ))}
              </select>
            )}

            <button
              type="button"
              className="board-tool-btn"
              onClick={() => setShowNewBoardModal(true)}
              title="Create a new board for this case"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
              </svg>
              <span>New Board</span>
            </button>
          </div>

          {/* Entities Count Pill at the top in the same box */}
          <div className="board-counts-pill" title="Current Board Elements">
            <span className="count-item"><strong>{entityNodes.length}</strong> Entities</span>
            <span className="count-divider">•</span>
            <span className="count-item"><strong>{edges.length}</strong> Connections</span>
            <span className="count-divider">•</span>
            <span className="count-item"><strong>{nodes.filter(n => n.type === 'stickyNote').length}</strong> Notes</span>
            {lastSavedTime && (
              <>
                <span className="count-divider">•</span>
                <span className="text-emerald-700 font-semibold text-[10px]">Saved {lastSavedTime}</span>
              </>
            )}
          </div>
        </div>

        {/* Row 2: Action Buttons */}
        <div className="board-toolbar-row">
          <div className="board-toolbar-group">
            <button
              type="button"
              className="board-tool-btn primary"
              onClick={() => setShowAddNodeModal(true)}
              title="Create a manual entity node"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
              <span>Add Node</span>
            </button>

            <button
              type="button"
              className="board-tool-btn"
              onClick={() => setShowAddConnectionModal(true)}
              disabled={entityNodes.length < 2}
              title={entityNodes.length < 2 ? "Add at least 2 nodes first" : "Connect two existing nodes"}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              <span>Add Connection</span>
            </button>

            <button
              type="button"
              className="board-tool-btn"
              onClick={handleAddStickyNote}
              title="Add sticky hypothesis note card"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Add Note</span>
            </button>

            <div className="board-divider" />

            {/* Undo / Redo */}
            <button
              type="button"
              className="board-tool-btn"
              onClick={undo}
              disabled={historyPast.current.length === 0}
              title="Undo (Ctrl+Z)"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h10a5 5 0 015 5v2M3 10l6-6m-6 6l6 6" />
              </svg>
              <span>Undo</span>
            </button>

            <button
              type="button"
              className="board-tool-btn"
              onClick={redo}
              disabled={historyFuture.current.length === 0}
              title="Redo (Ctrl+Y)"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 10h-10a5 5 0 00-5 5v2m15-7l-6-6m6 6l-6 6" />
              </svg>
              <span>Redo</span>
            </button>

            <div className="board-divider" />

            {/* Save Button */}
            <button
              type="button"
              className="board-tool-btn primary"
              onClick={handleSaveBoard}
              disabled={isSaving}
              title="Save to database (Ctrl+S)"
            >
              {isSaving ? (
                <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
              )}
              <span>{isSaving ? 'Saving...' : 'Save'}</span>
            </button>

            <div className="board-divider" />

            {/* Zoom & Fit View */}
            <button type="button" className="board-tool-btn" onClick={() => zoomIn()} title="Zoom In">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
            </button>
            <button type="button" className="board-tool-btn" onClick={() => zoomOut()} title="Zoom Out">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 12H6" />
              </svg>
            </button>
            <button type="button" className="board-tool-btn" onClick={() => fitView({ padding: 0.2 })} title="Fit View">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0 0l-5-5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
              <span>Fit View</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Interactive Canvas Area */}
      <div className="board-canvas-area">
        {isLoading ? (
          <div className="h-full flex items-center justify-center flex-col gap-3 text-slate-500">
            <svg className="animate-spin w-8 h-8 text-blue-600" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <p className="text-sm font-semibold">Loading manual investigation board...</p>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            onMoveEnd={(_, vp) => {
              if (activeBoardId) {
                localStorage.setItem(`atlas_board_vp_${activeBoardId}`, JSON.stringify(vp));
              }
            }}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            connectionMode={ConnectionMode.Loose}
            minZoom={0.2}
            maxZoom={2.5}
            defaultViewport={{ x: 0, y: 0, zoom: 1 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#CBD5E1" gap={16} size={1} />
            <MiniMap
              nodeColor={(n) => {
                if (n.type === 'stickyNote') return '#FDE047';
                const cat = (n.data as unknown as ManualEntityData)?.category;
                return CATEGORY_COLORS[cat]?.bg || '#0284C7';
              }}
              nodeStrokeColor={(n) => {
                if (n.type === 'stickyNote') return '#EAB308';
                const cat = (n.data as unknown as ManualEntityData)?.category;
                return CATEGORY_COLORS[cat]?.border || '#0369A1';
              }}
              nodeStrokeWidth={2}
              nodeBorderRadius={20}
              zoomable
              pannable
              position="bottom-right"
              className="board-minimap"
              maskColor="rgba(241, 245, 249, 0.45)"
              maskStrokeColor="#0284C7"
              maskStrokeWidth={1.5}
            />
          </ReactFlow>
        )}

        {/* Properties Panel (Right Drawer) */}
        {selectedNode && selectedNode.type === 'manualEntity' && (
          <div className="board-properties-panel">
            <div className="panel-header">
              <h3 className="panel-title">
                {renderNodeIcon((selectedNode.data as unknown as ManualEntityData).category)}
                <span>Entity Properties</span>
              </h3>
              <button
                type="button"
                className="text-slate-400 hover:text-slate-600 p-1"
                onClick={() => setSelectedNode(null)}
              >
                ✕
              </button>
            </div>
            <div className="panel-body">
              <div className="panel-field-group">
                <label className="panel-label">Label / Name</label>
                <input
                  type="text"
                  className="panel-input"
                  value={(selectedNode.data as unknown as ManualEntityData).label || ''}
                  onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                  placeholder="e.g. John Doe"
                />
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Entity Category</label>
                <select
                  className="panel-input"
                  value={(selectedNode.data as unknown as ManualEntityData).category || 'Other'}
                  onChange={(e) => updateSelectedNodeData({ category: e.target.value as ManualEntityData['category'] })}
                >
                  <option value="Person">Person</option>
                  <option value="Phone">Phone</option>
                  <option value="Device">Device / IMEI</option>
                  <option value="Vehicle">Vehicle</option>
                  <option value="Bank Account">Bank Account</option>
                  <option value="Location">Location</option>
                  <option value="Organization">Organization</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Role / Subtitle</label>
                <input
                  type="text"
                  className="panel-input"
                  value={(selectedNode.data as unknown as ManualEntityData).description || ''}
                  onChange={(e) => updateSelectedNodeData({ description: e.target.value })}
                  placeholder="e.g. Suspected Courier / Account Holder"
                />
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Investigator Notes</label>
                <textarea
                  className="panel-textarea"
                  value={(selectedNode.data as unknown as ManualEntityData).notes || ''}
                  onChange={(e) => updateSelectedNodeData({ notes: e.target.value })}
                  placeholder="Add officer hypotheses, lead dates, or verification records..."
                />
              </div>

            </div>
            <div className="panel-footer">
              <button
                type="button"
                className="panel-btn-delete"
                onClick={handleDeleteSelected}
                title="Remove entity from canvas"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                <span>Delete Node</span>
              </button>
              <button
                type="button"
                className="panel-btn-done"
                onClick={() => setSelectedNode(null)}
                title="Done editing entity"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                <span>Done</span>
              </button>
            </div>
          </div>
        )}

        {/* Properties Panel for Sticky Note */}
        {selectedNode && selectedNode.type === 'stickyNote' && (
          <div className="board-properties-panel">
            <div className="panel-header">
              <h3 className="panel-title">
                <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
                <span>Note Card</span>
              </h3>
              <button
                type="button"
                className="text-slate-400 hover:text-slate-600 p-1"
                onClick={() => setSelectedNode(null)}
              >
                ✕
              </button>
            </div>
            <div className="panel-body">
              <div className="panel-field-group">
                <label className="panel-label">Note Content</label>
                <textarea
                  className="panel-textarea"
                  style={{ minHeight: '110px' }}
                  value={(selectedNode.data as unknown as StickyNoteData).text || ''}
                  onChange={(e) => updateSelectedNoteData({ text: e.target.value })}
                  placeholder="Type note or case lead..."
                />
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Card Color</label>
                <div className="flex gap-2 mt-1">
                  {(['yellow', 'blue', 'pink', 'neutral'] as const).map(color => (
                    <button
                      key={color}
                      type="button"
                      className={`w-7 h-7 rounded-full border-2 transition-transform ${
                        (selectedNode.data as unknown as StickyNoteData).color === color ? 'scale-110 border-blue-600' : 'border-transparent'
                      }`}
                      style={{
                        backgroundColor: color === 'yellow' ? '#FEF3C7' : color === 'blue' ? '#E0F2FE' : color === 'pink' ? '#FCE7F3' : '#F1F5F8'
                      }}
                      onClick={() => updateSelectedNoteData({ color })}
                      title={`${color} note`}
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="panel-footer">
              <button
                type="button"
                className="panel-btn-delete"
                onClick={handleDeleteSelected}
                title="Remove sticky note"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                <span>Delete Note</span>
              </button>
              <button
                type="button"
                className="panel-btn-done"
                onClick={() => setSelectedNode(null)}
                title="Done editing note"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                <span>Done</span>
              </button>
            </div>
          </div>
        )}

        {/* Properties Panel for Edge */}
        {selectedEdge && (
          <div className="board-properties-panel">
            <div className="panel-header">
              <h3 className="panel-title">
                <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
                <span>Connection Properties</span>
              </h3>
              <button
                type="button"
                className="text-slate-400 hover:text-slate-600 p-1"
                onClick={() => setSelectedEdge(null)}
              >
                ✕
              </button>
            </div>
            <div className="panel-body">
              <div className="panel-field-group">
                <label className="panel-label">Relationship Label</label>
                <input
                  type="text"
                  className="panel-input"
                  value={(selectedEdge.data as unknown as ManualEdgeData)?.label || ''}
                  onChange={(e) => updateSelectedEdgeData({ label: e.target.value })}
                  placeholder="e.g. Suspected Associate"
                />
                <div className="quick-chips-grid">
                  {['Suspected Associate', 'Calls', 'Transfers Funds', 'Seen Together', 'Vehicle User', 'Family', 'Employer'].map(chip => (
                    <button
                      key={chip}
                      type="button"
                      className="quick-chip-btn"
                      onClick={() => updateSelectedEdgeData({ label: chip })}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Edge Line Style</label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <button
                    type="button"
                    className={`py-1.5 px-2 rounded-lg text-xs font-semibold border flex items-center justify-center gap-1.5 ${
                      (selectedEdge.data as unknown as ManualEdgeData)?.style !== 'dashed'
                        ? 'bg-blue-50 text-blue-700 border-blue-300'
                        : 'bg-white text-slate-700 border-slate-200'
                    }`}
                    onClick={() => updateSelectedEdgeData({ style: 'solid' })}
                  >
                    <span className="w-4 h-0.5 bg-current inline-block" />
                    <span>Solid (Documented)</span>
                  </button>
                  <button
                    type="button"
                    className={`py-1.5 px-2 rounded-lg text-xs font-semibold border flex items-center justify-center gap-1.5 ${
                      (selectedEdge.data as unknown as ManualEdgeData)?.style === 'dashed'
                        ? 'bg-blue-50 text-blue-700 border-blue-300'
                        : 'bg-white text-slate-700 border-slate-200'
                    }`}
                    onClick={() => updateSelectedEdgeData({ style: 'dashed' })}
                  >
                    <span className="w-4 h-0.5 border-b border-dashed border-current inline-block" />
                    <span>Dashed (Tentative)</span>
                  </button>
                </div>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Directional Arrow</label>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="checkbox"
                    id="edge-dir-check"
                    checked={(selectedEdge.data as unknown as ManualEdgeData)?.is_directional ?? true}
                    onChange={(e) => updateSelectedEdgeData({ is_directional: e.target.checked })}
                    className="rounded text-blue-600 focus:ring-blue-500"
                  />
                  <label htmlFor="edge-dir-check" className="text-xs text-slate-700 font-medium cursor-pointer">
                    Show directional arrow pointing to target
                  </label>
                </div>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Notes</label>
                <textarea
                  className="panel-textarea"
                  value={(selectedEdge.data as unknown as ManualEdgeData)?.notes || ''}
                  onChange={(e) => updateSelectedEdgeData({ notes: e.target.value })}
                  placeholder="Add notes about this relationship link..."
                />
              </div>
            </div>
            <div className="panel-footer">
              <button
                type="button"
                className="panel-btn-delete"
                onClick={handleDeleteSelected}
                title="Remove connection link"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                <span>Delete Link</span>
              </button>
              <button
                type="button"
                className="panel-btn-done"
                onClick={() => setSelectedEdge(null)}
                title="Done editing connection"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                <span>Done</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: Add Node */}
      {showAddNodeModal && (
        <div className="board-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowAddNodeModal(false); }}>
          <div className="board-modal-box">
            <div className="panel-header">
              <h3 className="panel-title">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                <span>Add Manual Entity Node</span>
              </h3>
              <button type="button" className="text-slate-400 hover:text-slate-600" onClick={() => setShowAddNodeModal(false)}>✕</button>
            </div>
            <div className="panel-body">
              <div className="panel-field-group">
                <label className="panel-label">Category</label>
                <div className="grid grid-cols-4 gap-2 mt-1">
                  {(Object.keys(CATEGORY_COLORS) as Array<ManualEntityData['category']>).map(cat => {
                    const c = CATEGORY_COLORS[cat];
                    const active = newNodeCategory === cat;
                    return (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setNewNodeCategory(cat)}
                        className={`flex flex-col items-center gap-1 p-2 rounded-lg border text-center transition-all ${
                          active ? 'border-blue-600 bg-blue-50/70 shadow-sm' : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <div
                          className="w-7 h-7 rounded-full flex items-center justify-center text-white"
                          style={{ backgroundColor: c.bg }}
                        >
                          {renderNodeIcon(cat)}
                        </div>
                        <span className="text-[10px] font-semibold text-slate-700">{cat}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Entity Label / Name</label>
                <input
                  type="text"
                  className="panel-input"
                  value={newNodeLabel}
                  onChange={(e) => setNewNodeLabel(e.target.value)}
                  placeholder="e.g. Suresh Kumar or +91 98402 11928"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleAddEntityNode(); }}
                />
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Role / Notes (Optional)</label>
                <input
                  type="text"
                  className="panel-input"
                  value={newNodeDesc}
                  onChange={(e) => setNewNodeDesc(e.target.value)}
                  placeholder="e.g. Registered owner of Hyundai Creta"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  className="board-tool-btn"
                  onClick={() => setShowAddNodeModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="board-tool-btn primary"
                  disabled={!newNodeLabel.trim()}
                  onClick={handleAddEntityNode}
                >
                  Add to Canvas
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Add Connection */}
      {showAddConnectionModal && (
        <div className="board-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowAddConnectionModal(false); }}>
          <div className="board-modal-box">
            <div className="panel-header">
              <h3 className="panel-title">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
                <span>Add Connection</span>
              </h3>
              <button type="button" className="text-slate-400 hover:text-slate-600" onClick={() => setShowAddConnectionModal(false)}>✕</button>
            </div>
            <div className="panel-body">
              <p className="text-xs text-slate-600 mb-1">
                Tip: You can also drag directly from any circle dot handle to another circle node!
              </p>

              <div className="grid grid-cols-2 gap-3">
                <div className="panel-field-group">
                  <label className="panel-label">Source Node</label>
                  <select
                    className="panel-input"
                    value={connSource}
                    onChange={(e) => setConnSource(e.target.value)}
                  >
                    <option value="">Select source...</option>
                    {entityNodes.map(n => (
                      <option key={n.id} value={n.id}>
                        {(n.data as unknown as ManualEntityData).label} ({(n.data as unknown as ManualEntityData).category})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="panel-field-group">
                  <label className="panel-label">Target Node</label>
                  <select
                    className="panel-input"
                    value={connTarget}
                    onChange={(e) => setConnTarget(e.target.value)}
                  >
                    <option value="">Select target...</option>
                    {entityNodes.map(n => (
                      <option key={n.id} value={n.id}>
                        {(n.data as unknown as ManualEntityData).label} ({(n.data as unknown as ManualEntityData).category})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Relationship Type</label>
                <input
                  type="text"
                  className="panel-input"
                  value={connLabel}
                  onChange={(e) => setConnLabel(e.target.value)}
                  placeholder="e.g. Suspected Associate"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="panel-field-group">
                  <label className="panel-label">Style</label>
                  <select
                    className="panel-input"
                    value={connStyle}
                    onChange={(e) => setConnStyle(e.target.value as 'solid' | 'dashed')}
                  >
                    <option value="solid">Solid (Documented)</option>
                    <option value="dashed">Dashed (Tentative)</option>
                  </select>
                </div>

                <div className="panel-field-group">
                  <label className="panel-label">Direction</label>
                  <select
                    className="panel-input"
                    value={connDirectional ? 'yes' : 'no'}
                    onChange={(e) => setConnDirectional(e.target.value === 'yes')}
                  >
                    <option value="yes">Directional Arrow</option>
                    <option value="no">Undirected</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  className="board-tool-btn"
                  onClick={() => setShowAddConnectionModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="board-tool-btn primary"
                  disabled={!connSource || !connTarget || connSource === connTarget}
                  onClick={handleAddConnectionSubmit}
                >
                  Connect Nodes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: New Board */}
      {showNewBoardModal && (
        <div className="board-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowNewBoardModal(false); }}>
          <div className="board-modal-box">
            <div className="panel-header">
              <h3 className="panel-title">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                </svg>
                <span>Create New Investigation Board</span>
              </h3>
              <button type="button" className="text-slate-400 hover:text-slate-600" onClick={() => setShowNewBoardModal(false)}>✕</button>
            </div>
            <div className="panel-body">
              <div className="panel-field-group">
                <label className="panel-label">Board Title</label>
                <input
                  type="text"
                  className="panel-input"
                  value={newBoardTitle}
                  onChange={(e) => setNewBoardTitle(e.target.value)}
                  placeholder="e.g. Syndicate Hawala Trail"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateNewBoard(); }}
                />
              </div>

              <div className="panel-field-group">
                <label className="panel-label">Associated Case</label>
                <input
                  type="text"
                  className="panel-input bg-slate-100"
                  readOnly
                  value={activeCaseId.toUpperCase()}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  className="board-tool-btn"
                  onClick={() => setShowNewBoardModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="board-tool-btn primary"
                  disabled={!newBoardTitle.trim()}
                  onClick={handleCreateNewBoard}
                >
                  Create Board
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function InvestigationBoardModule(props: InvestigationBoardModuleProps) {
  return (
    <ReactFlowProvider>
      <InvestigationBoardInner {...props} />
    </ReactFlowProvider>
  );
}

export default InvestigationBoardModule;
