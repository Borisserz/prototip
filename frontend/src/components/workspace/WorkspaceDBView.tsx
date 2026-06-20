import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, Brain, Database, ChevronLeft, Trash2, Search,
  Plus, Save, RefreshCw, Edit3, Check, X, ChevronRight,
  Table, Layers, BookOpen, Network, AlertCircle,
  CheckCircle, Loader2, ArrowUpDown, Copy, Hash, ToggleLeft, UploadCloud,
  ChevronUp, ChevronDown, Download, ClipboardCopy
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const BASE = 'http://localhost:8000';

interface WorkspaceDBViewProps {
  onBackToChat: () => void;
  token: string | null;
}

const tabs = [
  { id: 'knowledge', label: 'База знаний', icon: BookOpen, color: 'violet' },
  { id: 'semantic', label: 'Семантика', icon: Brain, color: 'cyan' },
  { id: 'database', label: 'База данных', icon: Database, color: 'emerald' },
];

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge Tab — IMPROVED
// ─────────────────────────────────────────────────────────────────────────────
const KnowledgeTab: React.FC<{ token: string | null }> = ({ token }) => {
  const [docs, setDocs] = useState<{ source: string; chunks: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [chunks, setChunks] = useState<{ id: string; content: string }[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('list');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newDocName, setNewDocName] = useState('');
  const [newDocContent, setNewDocContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [copiedChunk, setCopiedChunk] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/v1/knowledge`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      setDocs(data.documents || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const openDoc = async (source: string) => {
    setSelected(source);
    setChunksLoading(true);
    try {
      const res = await fetch(`${BASE}/api/v1/knowledge/chunks?source=${encodeURIComponent(source)}&limit=15`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      setChunks(data.chunks || []);
    } catch (e) { console.error(e); } finally { setChunksLoading(false); }
  };

  const deleteDoc = async (source: string) => {
    setDeleting(source);
    try {
      const encoded = btoa(source);
      await fetch(`${BASE}/api/v1/knowledge?source=${encoded}`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${token}` }
      });
      if (selected === source) setSelected(null);
      fetchDocs();
    } catch (e) { console.error(e); } finally { setDeleting(null); }
  };

  const addDocument = async () => {
    if (!newDocContent.trim()) return;
    setSaving(true);
    try {
      await fetch(`${BASE}/api/v1/knowledge/upload-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: newDocContent, source: newDocName || 'manual_doc.md' })
      });
      setShowAddModal(false); setNewDocContent(''); setNewDocName('');
      fetchDocs();
    } catch (e) { console.error(e); } finally { setSaving(false); }
  };

  const copyChunk = async (content: string, id: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedChunk(id);
    setTimeout(() => setCopiedChunk(null), 2000);
  };

  const filteredDocs = docs.filter(d => d.source.toLowerCase().includes(searchTerm.toLowerCase()));

  // Improved graph: place nodes in a circle, fill the SVG properly
  const W = 400, H = 400;
  const cx = W / 2, cy = H / 2;
  const radius = Math.min(filteredDocs.length <= 1 ? 0 : 130, 130);

  const graphNodes = filteredDocs.map((doc, i) => {
    const angle = (i / filteredDocs.length) * 2 * Math.PI - Math.PI / 2;
    return {
      ...doc,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });

  const getDocDisplayName = (source: string) => source.split('/').pop() ?? source;

  return (
    <div className="flex h-full gap-4 overflow-hidden">
      {/* Left panel */}
      <div className="w-72 shrink-0 flex flex-col gap-3 overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Поиск документов..."
              className="w-full bg-slate-900/60 border border-slate-700/50 rounded-lg h-9 pl-8 pr-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-violet-500/50"
            />
          </div>
          <div className="flex border border-slate-700/50 rounded-lg overflow-hidden shrink-0">
            {(['list', 'graph'] as const).map(m => (
              <button key={m} onClick={() => setViewMode(m)}
                className={`px-2.5 py-1.5 text-xs transition-colors ${viewMode === m ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                {m === 'list' ? 'Список' : 'Граф'}
              </button>
            ))}
          </div>
          <button onClick={() => setShowAddModal(true)}
            className="p-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition-all hover:scale-105 active:scale-95 shrink-0" title="Добавить">
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-3 px-3 py-2 bg-slate-800/40 border border-slate-700/30 rounded-xl text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-violet-400" />
            {docs.length} документов
          </span>
          <span className="text-slate-600">·</span>
          <span>{docs.reduce((s, d) => s + d.chunks, 0)} чанков</span>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
              <p className="text-xs text-slate-500">Загрузка...</p>
            </div>
          </div>
        ) : viewMode === 'list' ? (
          <div className="flex-1 overflow-y-auto space-y-1.5 pr-1 custom-scrollbar">
            {filteredDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
                <div className="w-16 h-16 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                  <Network className="w-8 h-8 text-violet-500/50" />
                </div>
                <div>
                  <p className="text-slate-400 text-sm font-medium">База знаний пуста</p>
                  <p className="text-slate-600 text-xs mt-1">Добавьте первый документ</p>
                </div>
                <button onClick={() => setShowAddModal(true)}
                  className="text-xs bg-violet-600 hover:bg-violet-500 text-white px-3 py-1.5 rounded-lg transition-colors">
                  + Добавить документ
                </button>
              </div>
            ) : filteredDocs.map((doc, i) => (
              <motion.div key={doc.source}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className={`group p-3 rounded-xl border cursor-pointer transition-all ${
                  selected === doc.source
                    ? 'bg-violet-500/20 border-violet-500/50 shadow-lg shadow-violet-500/10'
                    : 'bg-slate-800/40 border-slate-700/40 hover:border-violet-500/30 hover:bg-slate-800'
                }`}
                onClick={() => openDoc(doc.source)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5 min-w-0">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      selected === doc.source ? 'bg-violet-500/30' : 'bg-slate-700/50'
                    }`}>
                      <FileText className="w-4 h-4 text-violet-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm text-slate-200 font-medium truncate">{getDocDisplayName(doc.source)}</p>
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{doc.source.includes('/') ? doc.source.split('/').slice(-2, -1)[0] : 'root'}</p>
                      <div className="flex items-center gap-1.5 mt-1.5">
                        <span className="text-xs bg-slate-700/60 text-slate-400 px-1.5 py-0.5 rounded-md">{doc.chunks} чанков</span>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); deleteDoc(doc.source); }}
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-all"
                  >
                    {deleting === doc.source
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        ) : (
          /* Graph view — proper SVG */
          <div className="flex-1 bg-slate-900/50 border border-slate-700/30 rounded-2xl overflow-hidden relative">
            {filteredDocs.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-slate-600 text-sm">Нет документов</p>
              </div>
            ) : (
              <svg
                ref={svgRef}
                viewBox={`0 0 ${W} ${H}`}
                className="w-full h-full"
                style={{ display: 'block' }}
              >
                <defs>
                  <radialGradient id="center-grad" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#4c1d95" stopOpacity="0.4" />
                  </radialGradient>
                  <radialGradient id="node-grad" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#6d28d9" />
                    <stop offset="100%" stopColor="#1e1b4b" />
                  </radialGradient>
                  <radialGradient id="node-sel-grad" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#8b5cf6" />
                    <stop offset="100%" stopColor="#5b21b6" />
                  </radialGradient>
                  <filter id="glow">
                    <feGaussianBlur stdDeviation="3" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                {/* Edges from center */}
                {graphNodes.map(node => {
                  const isHovered = hoveredNode === node.source;
                  const isSelected = selected === node.source;
                  const isActive = hoveredNode ? isHovered : true;
                  return (
                  <line
                    key={`e-${node.source}`}
                    x1={cx} y1={cy}
                    x2={node.x} y2={node.y}
                    stroke={isHovered ? '#a855f7' : (isSelected ? '#7c3aed' : (hoveredNode ? '#1e1b4b' : '#312e81'))}
                    strokeWidth={isHovered || isSelected ? 1.5 : 0.8}
                    strokeOpacity={isActive ? "0.8" : "0.2"}
                    strokeDasharray={isSelected ? '' : '4 2'}
                    style={{ transition: 'all 0.3s' }}
                  />
                )})}

                {/* Center node */}
                <circle cx={cx} cy={cy} r={16} fill="url(#center-grad)" />
                <circle cx={cx} cy={cy} r={16} fill="none" stroke="#7c3aed" strokeWidth="1" strokeOpacity="0.5" />
                <text x={cx} y={cy - 22} textAnchor="middle" fontSize="11" fill="#a78bfa" fontWeight="500">База знаний</text>
                <text x={cx} y={cy + 4} textAnchor="middle" fontSize="10" fill="#c4b5fd">{docs.length}</text>

                {/* Doc nodes */}
                {graphNodes.map(node => {
                  const name = getDocDisplayName(node.source);
                  const isSelected = selected === node.source;
                  const isHovered = hoveredNode === node.source;
                  const r = 14;
                  return (
                    <g key={node.source}
                      onClick={() => openDoc(node.source)}
                      onMouseEnter={() => setHoveredNode(node.source)}
                      onMouseLeave={() => setHoveredNode(null)}
                      style={{ cursor: 'pointer' }}
                    >
                      {(isHovered || isSelected) && (
                        <circle cx={node.x} cy={node.y} r={r + 6} fill="#7c3aed" fillOpacity={isHovered ? "0.25" : "0.15"} style={{ transition: 'all 0.3s' }} />
                      )}
                      <circle
                        cx={node.x} cy={node.y} r={r}
                        fill={isSelected ? "url(#node-sel-grad)" : "url(#node-grad)"}
                        stroke={isSelected ? '#8b5cf6' : (isHovered ? '#a855f7' : '#3730a3')}
                        strokeWidth={isSelected || isHovered ? 1.5 : 1}
                        style={{ transition: 'all 0.3s', opacity: hoveredNode && !isHovered && !isSelected ? 0.3 : 1 }}
                      />
                      {/* Doc icon - simplified */}
                      <text x={node.x} y={node.y + 4} textAnchor="middle" fontSize="10" fill="white" fontFamily="sans-serif">DOC</text>
                      {/* Label below */}
                      <text
                        x={node.x} y={node.y + r + 14}
                        textAnchor="middle" fontSize="9.5" fill={isSelected ? '#c4b5fd' : '#94a3b8'}
                        fontWeight={isSelected ? '600' : '400'}
                      >
                        {name.length > 14 ? name.substring(0, 13) + '…' : name}
                      </text>
                      <text x={node.x} y={node.y + r + 26} textAnchor="middle" fontSize="8" fill="#64748b">
                        {node.chunks} чанк.
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
        )}
      </div>

      {/* Right: document viewer */}
      <div className="flex-1 overflow-hidden">
        {selected ? (
          <motion.div
            key={selected}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full flex flex-col bg-slate-800/40 border border-slate-700/30 rounded-2xl overflow-hidden"
          >
            {/* Doc header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-700/40 bg-slate-800/60">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center">
                  <FileText className="w-4 h-4 text-violet-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{getDocDisplayName(selected)}</p>
                  <p className="text-xs text-slate-500 font-mono mt-0.5 truncate max-w-xs">{selected}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 bg-slate-700/60 px-2 py-1 rounded-md">{chunks.length} чанков загружено</span>
                <button onClick={() => setSelected(null)} className="p-1.5 text-slate-500 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Chunks */}
            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar space-y-3">
              {chunksLoading ? (
                <div className="flex flex-col items-center justify-center py-20 gap-3">
                  <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
                  <p className="text-slate-500 text-sm">Загрузка содержимого...</p>
                </div>
              ) : chunks.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20">
                  <p className="text-slate-500 text-sm">Нет содержимого</p>
                </div>
              ) : chunks.map((chunk, i) => (
                <motion.div
                  key={chunk.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="group bg-slate-900/60 border border-slate-700/40 rounded-xl overflow-hidden hover:border-violet-500/30 transition-colors"
                >
                  <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700/40 bg-slate-800/40">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-violet-400 font-mono font-semibold">#{i + 1}</span>
                      <span className="text-xs text-slate-600">{chunk.content.length} символов</span>
                    </div>
                    <button
                      onClick={() => copyChunk(chunk.content, chunk.id)}
                      className="opacity-0 group-hover:opacity-100 flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-all"
                    >
                      {copiedChunk === chunk.id ? (
                        <><CheckCircle className="w-3.5 h-3.5 text-emerald-400" /> Скопировано</>
                      ) : (
                        <><Copy className="w-3.5 h-3.5" /> Копировать</>
                      )}
                    </button>
                  </div>
                  <pre className="text-slate-300 text-sm whitespace-pre-wrap font-sans leading-relaxed p-4">{chunk.content}</pre>
                </motion.div>
              ))}
            </div>
          </motion.div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center border border-dashed border-slate-700/40 rounded-2xl gap-4">
            <div className="w-20 h-20 rounded-3xl bg-slate-800/60 border border-slate-700/40 flex items-center justify-center">
              <Network className="w-10 h-10 text-slate-600" />
            </div>
            <div>
              <p className="text-slate-400 text-base font-medium">Выберите документ</p>
              <p className="text-slate-600 text-sm mt-1">Кликните на карточку слева чтобы просмотреть содержимое</p>
            </div>
          </div>
        )}
      </div>

      {/* Add Document Modal */}
      <AnimatePresence>
        {showAddModal && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md"
            onClick={() => setShowAddModal(false)}
          >
            <motion.div
              initial={{ scale: 0.93, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.93, opacity: 0, y: 20 }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-2xl bg-slate-800 border border-slate-700/60 rounded-2xl shadow-2xl mx-4"
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/40">
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-violet-500/20 flex items-center justify-center">
                    <Plus className="w-4 h-4 text-violet-400" />
                  </div>
                  Добавить документ в базу знаний
                </h3>
                <button onClick={() => setShowAddModal(false)} className="text-slate-500 hover:text-white p-1 rounded transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="text-sm text-slate-400 mb-1.5 block font-medium">Имя документа</label>
                  <input
                    value={newDocName}
                    onChange={e => setNewDocName(e.target.value)}
                    placeholder="my-document.md"
                    className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl h-10 px-4 text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500/50"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1.5 block font-medium">Содержимое</label>
                  <textarea
                    value={newDocContent}
                    onChange={e => setNewDocContent(e.target.value)}
                    placeholder="# Заголовок&#10;&#10;Введите текст документа, который будет добавлен в базу знаний ИИ..."
                    className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl p-4 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500/50 min-h-[220px] resize-y"
                    autoFocus
                  />
                  <p className="text-xs text-slate-600 mt-1.5">{newDocContent.length} символов · примерно {Math.ceil(newDocContent.length / 800)} чанков</p>
                </div>
              </div>
              <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-700/40">
                <Button variant="ghost" onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-white">Отмена</Button>
                <Button
                  onClick={addDocument}
                  disabled={saving || !newDocContent.trim()}
                  className="bg-violet-600 hover:bg-violet-500 text-white gap-2"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {saving ? 'Индексируется...' : 'Добавить и индексировать'}
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Semantic Tab — IMPROVED
// ─────────────────────────────────────────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  'UInt32': 'blue', 'UInt64': 'blue', 'Int32': 'blue', 'Int64': 'blue',
  'Float32': 'amber', 'Float64': 'amber',
  'String': 'emerald',
  'Date': 'rose', 'DateTime': 'rose',
};

const TypeBadge: React.FC<{ type: string }> = ({ type }) => {
  const base = Object.keys(TYPE_COLORS).find(k => type.startsWith(k)) ?? 'String';
  const color = TYPE_COLORS[base] ?? 'slate';
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    amber: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
    emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
    rose: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
    slate: 'bg-slate-500/15 text-slate-400 border-slate-500/20',
  };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono border ${colorClasses[color]}`}>
      {type}
    </span>
  );
};

const SemanticTab: React.FC<{ token: string | null }> = ({ token }) => {
  const [schema, setSchema] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [editingCol, setEditingCol] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [showAddMetric, setShowAddMetric] = useState(false);
  const [newMetric, setNewMetric] = useState({ name: '', business_term: '', calculation: '', description: '' });
  const [colSearch, setColSearch] = useState('');

  const fetchSchema = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/v1/semantic-schema`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      setSchema(data.schema);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchSchema(); }, [fetchSchema]);

  const saveSchema = async () => {
    setSaving(true);
    try {
      await fetch(`${BASE}/api/v1/semantic-schema`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(schema)
      });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (e) { console.error(e); } finally { setSaving(false); }
  };

  const startEdit = (colName: string, col: any) => {
    setEditingCol(colName);
    setEditValues({ business_term: col.business_term || '', description: col.description || '' });
  };

  const saveEdit = (colName: string) => {
    setSchema((prev: any) => ({
      ...prev,
      columns: prev.columns.map((c: any) => c.name === colName ? { ...c, ...editValues } : c)
    }));
    setEditingCol(null);
  };

  const addMetric = () => {
    if (!newMetric.name) return;
    setSchema((prev: any) => ({ ...prev, metrics: [...(prev.metrics || []), { ...newMetric }] }));
    setNewMetric({ name: '', business_term: '', calculation: '', description: '' });
    setShowAddMetric(false);
  };

  const removeMetric = (name: string) => {
    setSchema((prev: any) => ({ ...prev, metrics: prev.metrics.filter((m: any) => m.name !== name) }));
  };

  if (loading) return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-2">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-slate-500 text-sm">Загрузка схемы...</p>
      </div>
    </div>
  );

  if (!schema) return (
    <div className="flex-1 flex items-center justify-center">
      <p className="text-slate-500">Семантическая схема не найдена</p>
    </div>
  );

  const filteredCols = (schema.columns || []).filter((c: any) =>
    !colSearch || c.name.includes(colSearch) || (c.business_term || '').toLowerCase().includes(colSearch.toLowerCase())
  );

  return (
    <div className="h-full overflow-y-auto custom-scrollbar pr-1 space-y-5">
      {/* Sticky header */}
      <div className="sticky top-0 z-20 bg-slate-900/90 backdrop-blur-md pb-3 pt-1">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-white font-bold text-lg flex items-center gap-2">
                <Layers className="w-5 h-5 text-cyan-400" />
                {schema.table_name}
              </h3>
              <TypeBadge type="Table" />
            </div>
            <p className="text-xs text-slate-500 mt-1 line-clamp-1">{schema.description}</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <AnimatePresence>
              {saved && (
                <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
                  className="flex items-center gap-1.5 text-emerald-400 text-sm">
                  <CheckCircle className="w-4 h-4" /> Сохранено!
                </motion.div>
              )}
            </AnimatePresence>
            <Button onClick={saveSchema} disabled={saving}
              className="bg-cyan-600 hover:bg-cyan-500 text-white h-9 px-4 text-sm gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Сохранить
            </Button>
          </div>
        </div>

        {/* Live indicator */}
        <div className="flex items-center gap-2 mt-3 px-3 py-2 bg-emerald-500/8 border border-emerald-500/20 rounded-xl">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <p className="text-xs text-emerald-400 font-medium">Live: ИИ-агент использует эту схему при каждом запросе</p>
        </div>
      </div>

      {/* Column search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
        <input
          value={colSearch}
          onChange={e => setColSearch(e.target.value)}
          placeholder="Поиск по колонкам..."
          className="w-full bg-slate-800/40 border border-slate-700/40 rounded-xl h-9 pl-8 pr-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
        />
      </div>

      {/* Columns */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Hash className="w-4 h-4 text-slate-500" />
          <h4 className="text-sm font-semibold text-slate-300">
            Колонки <span className="text-slate-600 font-normal">({filteredCols.length})</span>
          </h4>
        </div>
        <div className="space-y-2">
          {filteredCols.map((col: any, i: number) => (
            <motion.div key={col.name}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.03 }}
              className="group bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden hover:border-cyan-500/30 transition-all"
            >
              {editingCol === col.name ? (
                <div className="p-4 space-y-3 bg-slate-800/80">
                  <div className="flex items-center gap-2 pb-2 border-b border-slate-700/40">
                    <span className="font-mono text-cyan-300 text-sm font-semibold">{col.name}</span>
                    <TypeBadge type={col.type} />
                    <span className="text-xs text-slate-500">— редактирование</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block font-medium">Бизнес-термин</label>
                      <input
                        autoFocus
                        value={editValues.business_term}
                        onChange={e => setEditValues(v => ({ ...v, business_term: e.target.value }))}
                        className="w-full bg-slate-900/60 border border-cyan-500/30 rounded-lg h-9 px-3 text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block font-medium">Описание для ИИ</label>
                      <input
                        value={editValues.description}
                        onChange={e => setEditValues(v => ({ ...v, description: e.target.value }))}
                        className="w-full bg-slate-900/60 border border-cyan-500/30 rounded-lg h-9 px-3 text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setEditingCol(null)} className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white text-sm transition-colors">
                      Отмена
                    </button>
                    <button onClick={() => saveEdit(col.name)}
                      className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm transition-colors flex items-center gap-1.5">
                      <Check className="w-3.5 h-3.5" /> Применить
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center px-4 py-3 gap-4">
                  <div className="w-28 shrink-0">
                    <p className="font-mono text-cyan-300 text-sm font-semibold truncate">{col.name}</p>
                  </div>
                  <div className="w-28 shrink-0">
                    <TypeBadge type={col.type} />
                  </div>
                  <div className="w-36 shrink-0">
                    <p className="text-white text-sm font-medium">{col.business_term || <span className="text-slate-600 italic text-xs">не задан</span>}</p>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-400 text-sm truncate">{col.description || '—'}</p>
                  </div>
                  <button
                    onClick={() => startEdit(col.name, col)}
                    className="ml-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-700 transition-all shrink-0"
                    title="Редактировать"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-slate-500" />
            <h4 className="text-sm font-semibold text-slate-300">
              Метрики <span className="text-slate-600 font-normal">({schema.metrics?.length ?? 0})</span>
            </h4>
          </div>
          <button onClick={() => setShowAddMetric(!showAddMetric)}
            className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 transition-colors px-2 py-1 rounded-lg hover:bg-cyan-500/10">
            <Plus className="w-3.5 h-3.5" /> Добавить метрику
          </button>
        </div>

        <AnimatePresence>
          {showAddMetric && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              className="bg-slate-800/60 border border-cyan-500/20 rounded-xl p-4 mb-3 overflow-hidden"
            >
              <div className="grid grid-cols-2 gap-3">
                {[
                  { key: 'name', label: 'Код метрики', placeholder: 'collection_rate' },
                  { key: 'business_term', label: 'Бизнес-термин', placeholder: 'Уровень сборов' },
                  { key: 'calculation', label: 'SQL-формула', placeholder: 'sum(paid) / sum(accrued) * 100' },
                  { key: 'description', label: 'Описание', placeholder: 'Процент собранных налогов' },
                ].map(f => (
                  <div key={f.key}>
                    <label className="text-xs text-slate-400 mb-1 block">{f.label}</label>
                    <input
                      value={(newMetric as any)[f.key]}
                      onChange={e => setNewMetric(v => ({ ...v, [f.key]: e.target.value }))}
                      placeholder={f.placeholder}
                      className="w-full bg-slate-900/60 border border-slate-600/50 rounded-lg h-9 px-3 text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50 placeholder:text-slate-600 font-mono"
                    />
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2 mt-3">
                <button onClick={() => setShowAddMetric(false)} className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors">Отмена</button>
                <button onClick={addMetric} className="px-3 py-1.5 text-sm bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors">Добавить</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="space-y-2">
          {(schema.metrics || []).map((m: any) => (
            <div key={m.name} className="group bg-slate-800/40 border border-slate-700/40 rounded-xl px-4 py-3 flex items-center gap-4 hover:border-cyan-500/30 transition-all">
              <div className="w-32 shrink-0">
                <p className="text-cyan-300 text-sm font-mono font-semibold">{m.name}</p>
                <p className="text-xs text-slate-500 mt-0.5">{m.business_term || '—'}</p>
              </div>
              <div className="flex-1 min-w-0 flex items-center gap-2">
                <code className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded font-mono">
                  {m.calculation || m.expression}
                </code>
                <button onClick={() => navigator.clipboard.writeText(m.calculation || m.expression)} className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-500 hover:text-amber-400 transition-colors" title="Копировать SQL">
                  <ClipboardCopy className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 min-w-0 hidden sm:block">
                <p className="text-slate-400 text-sm truncate">{m.description || '—'}</p>
              </div>
              <button onClick={() => removeMetric(m.name)}
                className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Database Tab — IMPROVED
// ─────────────────────────────────────────────────────────────────────────────
const TABLES = ['tax_data', 'knowledge_base', 'dashboard_knowledge'];

const TABLE_META: Record<string, { icon: React.ReactNode; color: string; desc: string }> = {
  tax_data: { icon: <Database className="w-4 h-4" />, color: 'emerald', desc: 'Налоговые данные' },
  knowledge_base: { icon: <BookOpen className="w-4 h-4" />, color: 'violet', desc: 'База знаний (RAG)' },
  dashboard_knowledge: { icon: <Layers className="w-4 h-4" />, color: 'blue', desc: 'Сохранённые дашборды' },
};

const formatNumber = (val: any): string => {
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toLocaleString('ru-RU');
    return val.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
  }
  return String(val ?? '');
};

const isNumericCol = (col: string): boolean =>
  ['accrued', 'paid', 'debt', 'penalties', 'taxpayers', 'penalty'].some(k => col.includes(k));

const DatabaseTab: React.FC<{ token: string | null }> = ({ token }) => {
  const [selectedTable, setSelectedTable] = useState('tax_data');
  const [data, setData] = useState<{ columns: string[]; rows: any[]; total: number; pages: number }>({ columns: [], rows: [], total: 0, pages: 1 });
  const [stats, setStats] = useState<Record<string, { total_rows: number; size_on_disk: string }>>({});
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  // New states for uploading and editing
  const [uploading, setUploading] = useState(false);
  const [editingRow, setEditingRow] = useState<number | null>(null);
  const [editData, setEditData] = useState<Record<string, any>>({});
  const [savingRow, setSavingRow] = useState(false);

  const handleWorkspaceUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    setUploading(true);
    try {
      const res = await fetch(`${BASE}/api/v1/workspace/upload`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData
      });
      const dataJson = await res.json();
      if(res.ok) {
        if (!TABLES.includes(dataJson.table_name)) TABLES.push(dataJson.table_name);
        alert("Успешно загружено! Таблица: " + dataJson.table_name);
        fetchData(dataJson.table_name, 1, "");
        setSelectedTable(dataJson.table_name);
      } else {
        alert("Ошибка: " + dataJson.detail);
      }
    } catch (err) {
      alert("Ошибка сети");
    } finally {
      setUploading(false);
    }
  }

  const startEditRow = (ri: number, row: any) => {
    setEditingRow(ri);
    setEditData({ ...row });
  };

  const saveRow = async (ri: number, originalRow: any) => {
    setSavingRow(true);
    try {
      const res = await fetch(`${BASE}/api/v1/db/tables/${selectedTable}/row`, {
        method: "PUT",
        headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ old_row: originalRow, new_row: editData })
      });
      if (res.ok) {
        const newRows = [...data.rows];
        newRows[ri] = { ...editData };
        setData({ ...data, rows: newRows });
        setEditingRow(null);
      } else {
        const err = await res.json();
        alert("Ошибка: " + err.detail);
      }
    } catch (e) {
      alert("Ошибка сети");
    } finally {
      setSavingRow(false);
    }
  };

  const fetchData = useCallback(async (table: string, p: number, s: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/v1/db/tables/${table}/data?page=${p}&limit=50&search=${encodeURIComponent(s)}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const json = await res.json();
      setData({ columns: json.columns || [], rows: json.rows || [], total: json.total || 0, pages: json.pages || 1 });
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [token]);

  const fetchStats = useCallback(async (table: string) => {
    try {
      const res = await fetch(`${BASE}/api/v1/db/tables/${table}/stats`, { headers: { Authorization: `Bearer ${token}` } });
      const json = await res.json();
      setStats(prev => ({ ...prev, [table]: { total_rows: json.total_rows, size_on_disk: json.size_on_disk } }));
    } catch (e) { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchData(selectedTable, page, search);
    TABLES.forEach(fetchStats);
  }, [selectedTable, page, search, fetchData, fetchStats]);

  const changeTable = (t: string) => {
    setSelectedTable(t); setPage(1); setSearch(''); setSearchInput(''); setSortCol(null);
  };

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); setSearch(searchInput); setPage(1); };

  const handleSort = (col: string) => {
    if (sortCol === col) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(true); }
  };

  const exportCSV = () => {
    if (!data.rows || data.rows.length === 0) return;
    const header = data.columns.join(',');
    const csvRows = data.rows.map(row => data.columns.map(col => {
      const val = row[col];
      return typeof val === 'string' ? `"${val.replace(/"/g, '""')}"` : val;
    }).join(','));
    const csvStr = [header, ...csvRows].join('\n');
    const blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedTable}_export.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const sortedRows = sortCol
    ? [...data.rows].sort((a, b) => {
        const va = a[sortCol] ?? '';
        const vb = b[sortCol] ?? '';
        const cmp = typeof va === 'number'
          ? va - vb
          : String(va).localeCompare(String(vb), 'ru');
        return sortAsc ? cmp : -cmp;
      })
    : data.rows;

  const meta = TABLE_META[selectedTable] ?? { icon: <Table className="w-4 h-4" />, color: 'slate', desc: '' };

  return (
    <div className="flex h-full gap-4 overflow-hidden">
      {/* Left: table list */}
      <div className="w-52 shrink-0 flex flex-col gap-2">
        <p className="text-xs text-slate-500 uppercase tracking-wider font-semibold px-1 mb-1">Таблицы</p>
        {TABLES.map(table => {
          const m = TABLE_META[table] ?? { icon: <Table className="w-4 h-4" />, color: 'slate', desc: '' };
          const st = stats[table];
          const isActive = selectedTable === table;
          return (
            <motion.button
              key={table}
              onClick={() => changeTable(table)}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className={`w-full text-left p-3 rounded-xl border transition-all ${
                isActive
                  ? `bg-${m.color}-500/15 border-${m.color}-500/40 shadow-sm`
                  : 'bg-slate-800/40 border-slate-700/40 hover:border-slate-600 hover:bg-slate-800/60'
              }`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-base">{m.icon}</span>
                <span className={`text-sm font-medium font-mono ${isActive ? `text-${m.color}-300` : 'text-slate-200'}`}>
                  {table}
                </span>
              </div>
              <p className="text-xs text-slate-500 mb-1.5">{m.desc}</p>
              {st ? (
                <div className={`text-xs font-medium ${isActive ? `text-${m.color}-400` : 'text-slate-500'}`}>
                  {st.total_rows.toLocaleString('ru-RU')} строк · {st.size_on_disk}
                </div>
              ) : (
                <div className="text-xs text-slate-600 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> загрузка...
                </div>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Right: data browser */}
      <div className="flex-1 flex flex-col overflow-hidden bg-slate-800/40 border border-slate-700/30 rounded-2xl">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/40 shrink-0 bg-slate-800/60">
          <div className="relative overflow-hidden group">
             <Button className="h-9 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition-all font-medium pl-3 pr-4 shadow-sm shadow-emerald-900/20">
               {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UploadCloud className="w-4 h-4 mr-2" />}
               Загрузить датасет
             </Button>
             <input type="file" accept=".csv, .xlsx" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onChange={handleWorkspaceUpload} disabled={uploading} />
          </div>
          <Button variant="outline" onClick={exportCSV} className="h-9 border-slate-600 hover:bg-slate-700/50 hover:text-white text-slate-300 text-sm rounded-lg px-3 shadow-sm bg-slate-800">
            <Download className="w-4 h-4 mr-2" />
            Экспорт CSV
          </Button>
          <div className="w-px h-6 bg-slate-700/50 mx-1"></div>
          <form onSubmit={handleSearch} className="flex-1 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder={`Поиск в ${selectedTable}...`}
                className="w-full bg-slate-900/60 border border-slate-700/50 rounded-lg h-9 pl-8 pr-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
              />
            </div>
            <button type="submit" className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition-colors font-medium">
              Найти
            </button>
          </form>
          {search && (
            <button onClick={() => { setSearch(''); setSearchInput(''); }}
              className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition-colors">
              <X className="w-3.5 h-3.5" /> Сброс
            </button>
          )}
          <div className="text-xs text-slate-500 shrink-0 font-medium">
            {data.total.toLocaleString('ru-RU')} записей
          </div>
          <button onClick={() => fetchData(selectedTable, page, search)}
            className={`p-1.5 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-white/5`}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto custom-scrollbar">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Loader2 className="w-8 h-8 text-emerald-400 animate-spin" />
              <p className="text-slate-500 text-sm">Загрузка данных...</p>
            </div>
          ) : data.rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <AlertCircle className="w-10 h-10 text-slate-700" />
              <div className="text-center">
                <p className="text-slate-400 font-medium">Данных нет</p>
                {search && <p className="text-slate-600 text-sm mt-1">По запросу «{search}»</p>}
              </div>
            </div>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead className="sticky top-0 z-10">
                <tr>
                  {data.columns.map(col => (
                    <th
                      key={col}
                      onClick={() => handleSort(col)}
                      className="text-left px-4 py-2.5 text-xs text-slate-400 font-semibold border-b border-slate-700/60 whitespace-nowrap cursor-pointer hover:text-white transition-colors group bg-slate-900/95 backdrop-blur"
                    >
                      <span className="flex items-center gap-1.5">
                        {col}
                        {sortCol === col ? (
                          sortAsc ? <ChevronUp className="w-3.5 h-3.5 text-emerald-400" /> : <ChevronDown className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <ArrowUpDown className="w-3.5 h-3.5 opacity-0 group-hover:opacity-40 transition-opacity" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row, ri) => {
                  const isEditing = editingRow === ri;
                  return (
                  <motion.tr
                    key={ri}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(ri * 0.01, 0.3) }}
                    className={`transition-colors border-b border-slate-800/60 group relative ${isEditing ? 'bg-slate-800/80 ring-1 ring-emerald-500/50 z-10' : 'hover:bg-emerald-500/5'}`}
                    onDoubleClick={() => !isEditing && startEditRow(ri, row)}
                  >
                    {data.columns.map((col, ci) => {
                      const val = row[col];
                      const isNum = isNumericCol(col) && typeof val === 'number';
                      
                      return (
                        <td key={col} className={`px-4 py-2.5 max-w-[220px] truncate relative ${
                          isNum && !isEditing ? 'text-right font-mono text-emerald-300/80 tabular-nums' : 'text-slate-300'
                        }`}>
                          {isEditing ? (
                            <input 
                              className="w-full bg-slate-900/80 border border-emerald-500/30 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/80"
                              value={editData[col] ?? ''}
                              onChange={e => setEditData({ ...editData, [col]: e.target.value })}
                            />
                          ) : (
                            isNum ? formatNumber(val) : String(val ?? '')
                          )}
                          
                          {/* Edit Actions - Only on last column */}
                          {!isEditing && ci === data.columns.length - 1 && (
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 bg-slate-800/90 rounded-md p-1 shadow-lg border border-slate-700/50">
                              <button onClick={() => startEditRow(ri, row)} className="p-1 text-slate-400 hover:text-emerald-400 rounded transition-colors" title="Редактировать">
                                <Edit3 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          )}
                          {isEditing && ci === data.columns.length - 1 && (
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 bg-slate-800/90 rounded-md p-1 shadow-lg border border-emerald-500/30 z-20">
                              <button onClick={() => setEditingRow(null)} className="p-1 text-slate-400 hover:text-white rounded transition-colors" title="Отмена">
                                <X className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => saveRow(ri, row)} disabled={savingRow} className="p-1 text-emerald-400 hover:text-emerald-300 rounded transition-colors" title="Сохранить">
                                {savingRow ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </motion.tr>
                )})}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-700/40 shrink-0 bg-slate-800/40">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-2 py-1 rounded-lg hover:bg-white/5"
            >
              <ChevronLeft className="w-4 h-4" /> Назад
            </button>
            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(data.pages, 7) }, (_, i) => {
                const pg = data.pages <= 7 ? i + 1 : (page <= 4 ? i + 1 : page - 3 + i);
                if (pg < 1 || pg > data.pages) return null;
                return (
                  <button key={pg} onClick={() => setPage(pg)}
                    className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                      pg === page ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`}>
                    {pg}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setPage(p => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-2 py-1 rounded-lg hover:bg-white/5"
            >
              Вперёд <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Main WorkspaceDBView
// ─────────────────────────────────────────────────────────────────────────────
export const WorkspaceDBView: React.FC<WorkspaceDBViewProps> = ({ onBackToChat, token }) => {
  const [activeTab, setActiveTab] = useState('knowledge');

  const tabColorMap: Record<string, string> = {
    knowledge: 'from-violet-500/20 to-transparent',
    semantic: 'from-cyan-500/20 to-transparent',
    database: 'from-emerald-500/20 to-transparent',
  };

  return (
    <div className="h-full flex flex-col p-5 gap-4">
      {/* Header */}
      <div className="flex items-center gap-4 shrink-0">
        <Button variant="ghost" size="icon" onClick={onBackToChat}
          className="text-slate-400 hover:text-white hover:bg-white/10 rounded-xl">
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
              <Database className="w-4 h-4 text-emerald-400" />
            </div>
            Workspace БД
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 ml-10">Управление данными, знаниями и семантическим слоем ИИ</p>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 bg-slate-800/60 border border-slate-700/40 rounded-2xl p-1 w-fit shrink-0">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-medium transition-all ${
              activeTab === tab.id ? 'text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId="tab-indicator"
                className={`absolute inset-0 rounded-xl bg-gradient-to-r ${tabColorMap[tab.id]} border border-${tab.color}-500/30`}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
            <tab.icon className={`w-4 h-4 relative z-10 ${activeTab === tab.id ? `text-${tab.color}-400` : ''}`} />
            <span className="relative z-10">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="h-full"
          >
            {activeTab === 'knowledge' && <KnowledgeTab token={token} />}
            {activeTab === 'semantic' && <SemanticTab token={token} />}
            {activeTab === 'database' && <DatabaseTab token={token} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
};
