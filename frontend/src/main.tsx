import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { CacheInspector } from './components/CacheInspector';
import './styles.css';
import './evidence.css';
import './decision.css';
import './setup.css';

const root = document.getElementById('root');
if (!root) {
  throw new Error('Missing #root element');
}

const content = window.location.pathname === '/settings/cache' ? <CacheInspector /> : <App />;

createRoot(root).render(<StrictMode>{content}</StrictMode>);
