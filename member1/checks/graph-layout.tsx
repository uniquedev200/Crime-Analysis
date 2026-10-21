// Isolated layout fixture. Does not create an officer session or fabricate case records.
import React from 'react';
import {createRoot} from 'react-dom/client';
import {GraphExplorerModule} from '../src/components/GraphExplorerModule';
import {Sidebar, TopHeader} from '../src/components/Sidebar';
import '../src/index.css';
import '../src/workspace.css';
import '../src/workspace-layout.css';
import '../src/investigation-workspace.css';
import '../src/investigate.css';
import '../src/palette.css';
import '../src/compact.css';
const noop = () => {};
createRoot(document.getElementById('root')!).render(<div className="app-shell investigate-shell"><TopHeader view="graph" health={null} officerSession={null} changeView={noop}/><div className="app-layout"><Sidebar view="graph" changeView={noop}/><div className="app-content"><div className="view-banner"><h1>Graph Explorer</h1></div><main className="main"><GraphExplorerModule cases={[]} selectedCase={null} setSelectedCase={noop} openEntityModal={noop} addToast={noop} theme="light"/></main></div></div></div>);
