import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Settings, X, Users, Shield, Activity, Database, Check, AlertCircle, BookOpen, FileDown, UploadCloud, Zap, Bot } from 'lucide-react';
import { PromptsAdmin } from './PromptsAdmin';
import { Button } from '@/components/ui/button';

interface AdminModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminModal: React.FC<AdminModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'rbac' | 'users' | 'logs' | 'knowledge' | 'subscriptions' | 'schema' | 'dropzone' | 'prompts'>('rbac');
  const [sessions, setSessions] = useState<any[]>([]);
  const [sqlLogs, setSqlLogs] = useState<any[]>([]);
  const [kbDocs, setKbDocs] = useState<any[]>([]);
  const [subs, setSubs] = useState<any[]>([]);
  const [dbSchema, setDbSchema] = useState<string>('');
  const [dropzoneFiles, setDropzoneFiles] = useState<any[]>([]);
  const [semanticRules, setSemanticRules] = useState<any[]>([]);

  useEffect(() => {
    if (isOpen) {
      if (activeTab === 'users') {
        fetch('http://localhost:8000/api/v1/sessions')
          .then(res => res.json())
          .then(data => setSessions(data.sessions || []))
          .catch(err => console.error(err));
      } else if (activeTab === 'logs') {
        fetch('http://localhost:8000/api/v1/sql-logs')
          .then(res => res.json())
          .then(data => setSqlLogs(data.logs || []))
          .catch(err => console.error(err));
      } else if (activeTab === 'knowledge') {
        fetch('http://localhost:8000/api/v1/knowledge')
          .then(res => res.json())
          .then(data => setKbDocs(data.documents || []))
          .catch(err => console.error(err));
      } else if (activeTab === 'subscriptions') {
        fetch('http://localhost:8000/api/v1/subscriptions')
          .then(res => res.json())
          .then(data => setSubs(data.subscriptions || []))
          .catch(err => console.error(err));
      } else if (activeTab === 'schema') {
        fetch('http://localhost:8000/api/v1/schema')
          .then(res => res.json())
          .then(data => setDbSchema(data.schema || ''))
          .catch(err => console.error(err));
        fetch('http://localhost:8000/api/v1/semantic-rules')
          .then(res => res.json())
          .then(data => setSemanticRules(data.rules || []))
          .catch(err => console.error(err));
      } else if (activeTab === 'dropzone') {
        fetch('http://localhost:8000/api/v1/dropzone')
          .then(res => res.json())
          .then(data => setDropzoneFiles(data.files || []))
          .catch(err => console.error(err));
      }
    }
  }, [isOpen, activeTab]);

  const handleUploadDropzone = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      await fetch('http://localhost:8000/api/v1/upload_data', {
        method: 'POST',
        body: formData
      });
      // Refresh list
      fetch('http://localhost:8000/api/v1/dropzone')
        .then(res => res.json())
        .then(data => setDropzoneFiles(data.files || []));
    } catch (err) {
      console.error(err);
    }
  };

  const handleTriggerWatcher = async () => {
    try {
      await fetch('http://localhost:8000/api/v1/trigger_watcher', { method: 'POST' });
      alert('Проактивное сканирование запущено.');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="bg-slate-900/90 border border-slate-700/50 rounded-2xl w-full max-w-6xl overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col h-[85vh] glass-panel"
          >
            <div className="p-6 border-b border-slate-800/50 flex items-center justify-between bg-slate-950/40">
              <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400 flex items-center gap-3">
                <div className="p-2 bg-primary/10 rounded-lg">
                  <Settings className="w-5 h-5 text-primary" />
                </div>
                Системный Центр Управления
              </h2>
              <Button variant="ghost" size="icon" onClick={onClose} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </Button>
            </div>
            
            <div className="flex flex-1 overflow-hidden">
              {/* Sidebar Tabs */}
              <div className="w-64 bg-slate-800/30 border-r border-slate-800 p-4 space-y-2">
                <Button 
                  variant={activeTab === 'rbac' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'rbac' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('rbac')}
                >
                  <Shield className="w-4 h-4 mr-3" /> Управление RBAC
                </Button>
                <Button 
                  variant={activeTab === 'users' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'users' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('users')}
                >
                  <Users className="w-4 h-4 mr-3" /> Пользователи
                </Button>
                <Button 
                  variant={activeTab === 'logs' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'logs' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('logs')}
                >
                  <Activity className="w-4 h-4 mr-3" /> Журнал SQL
                </Button>
                <Button 
                  variant={activeTab === 'knowledge' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'knowledge' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('knowledge')}
                >
                  <Database className="w-4 h-4 mr-3" /> База Знаний (RAG)
                </Button>
                <Button 
                  variant={activeTab === 'subscriptions' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'subscriptions' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('subscriptions')}
                >
                  <Activity className="w-4 h-4 mr-3" /> Подписки
                </Button>
                <Button 
                  variant={activeTab === 'schema' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'schema' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('schema')}
                >
                  <BookOpen className="w-4 h-4 mr-3" /> Схема и WrenAI
                </Button>
                <Button 
                  variant={activeTab === 'dropzone' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'dropzone' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('dropzone')}
                >
                  <FileDown className="w-4 h-4 mr-3" /> ETL Dropzone
                </Button>
                <Button 
                  variant={activeTab === 'prompts' ? 'secondary' : 'ghost'} 
                  className={`w-full justify-start ${activeTab === 'prompts' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white'}`}
                  onClick={() => setActiveTab('prompts')}
                >
                  <Bot className="w-4 h-4 mr-3" /> Промпты агентов
                </Button>
              </div>


              {/* Content Area */}
              <div className="flex-1 overflow-y-auto p-6 bg-slate-900/50">
                {activeTab === 'prompts' && <PromptsAdmin />}
                {activeTab === 'rbac' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2"><Database className="w-4 h-4" /> Политики доступа (RLS)</h3>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 hover:border-slate-600 transition-colors">
                          <div className="flex-1 mr-4">
                            <p className="font-medium text-white text-base">FederalAnalyst</p>
                            <p className="text-sm text-slate-400 mt-1">Полный доступ ко всем регионам и ИНН</p>
                            <div className="mt-3 p-2 bg-slate-950/50 rounded-lg border border-slate-800 font-mono text-xs text-slate-300">
                              <span className="text-emerald-400">1 = 1</span> /* Без ограничений */
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-3">
                            <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 text-xs font-semibold">Active</span>
                            <Button size="sm" variant="outline" className="border-primary text-primary hover:bg-primary/10">Изменить RLS</Button>
                          </div>
                        </div>
                        <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 hover:border-slate-600 transition-colors">
                          <div className="flex-1 mr-4">
                            <p className="font-medium text-white text-base">RegionManager (Minsk)</p>
                            <p className="text-sm text-slate-400 mt-1">Доступ только к данным своего региона</p>
                            <div className="mt-3 p-2 bg-slate-950/50 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 flex items-center justify-between">
                              <span><span className="text-accent">WHERE</span> region = <span className="text-emerald-400">'г. Минск'</span></span>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-3">
                            <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 text-xs font-semibold">Active</span>
                            <Button size="sm" variant="outline" className="border-primary text-primary hover:bg-primary/10">Изменить RLS</Button>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Анонимизация данных (PII)</h3>
                      <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 flex items-center justify-between">
                        <div>
                          <p className="font-medium text-white">Маскировать ИНН и имена при отправке в LLM</p>
                          <p className="text-sm text-slate-400">Используется Faker для подмены</p>
                        </div>
                        <div className="w-12 h-6 bg-primary rounded-full relative cursor-pointer shadow-inner">
                          <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow-md"></div>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'users' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Активные сессии</h3>
                      <Button size="sm" className="bg-primary hover:bg-primary/90 text-white">Добавить пользователя</Button>
                    </div>
                    <table className="w-full text-sm text-left">
                      <thead className="text-xs text-slate-400 uppercase bg-slate-800/50 rounded-t-xl">
                        <tr>
                          <th className="px-4 py-3 rounded-tl-xl">Имя / ID</th>
                          <th className="px-4 py-3">Роль</th>
                          <th className="px-4 py-3">Статус</th>
                          <th className="px-4 py-3 rounded-tr-xl">Действие</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sessions.length === 0 && (
                          <tr><td colSpan={4} className="px-4 py-3 text-slate-500">Сессий не найдено</td></tr>
                        )}
                        {sessions.map((s, idx) => (
                          <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                            <td className="px-4 py-3 font-medium text-white">{s.session_id.substring(0, 8)}...</td>
                            <td className="px-4 py-3 text-slate-300">{s.message_count} сообщений</td>
                            <td className="px-4 py-3"><span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-400"></span>Активна</span></td>
                            <td className="px-4 py-3"><Button variant="ghost" size="sm" className="text-slate-400">View</Button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </motion.div>
                )}

                {activeTab === 'logs' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Последние SQL транзакции (Eval Validated)</h3>
                    <div className="space-y-2">
                      {sqlLogs.length === 0 && <div className="text-slate-500 text-sm">Загрузка логов...</div>}
                      {sqlLogs.map((log, idx) => (
                        <div key={idx} className="p-3 rounded-xl bg-slate-900 border border-slate-700/50 text-xs font-mono text-slate-300 mb-2">
                          <div className="flex justify-between text-slate-500 mb-1">
                            <span>{log.user || 'system'} • {log.duration_ms} ms</span>
                            <span className="flex items-center">
                              {log.status === 'Validated' ? <Check className="w-3 h-3 text-emerald-400 mr-1" /> : <AlertCircle className="w-3 h-3 text-rose-400 mr-1" />}
                              {log.status}
                            </span>
                          </div>
                          {log.query}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === 'knowledge' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Документы RAG</h3>
                      <Button size="sm" className="bg-primary hover:bg-primary/90 text-white">Добавить документ</Button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {kbDocs.length === 0 && <div className="col-span-2 text-slate-500 text-sm">База знаний пуста</div>}
                      {kbDocs.map((doc, idx) => (
                        <div key={idx} className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 flex flex-col gap-2">
                          <p className="font-medium text-white truncate" title={doc.source}>{doc.source}</p>
                          <p className="text-sm text-slate-400">Чанков: {doc.chunks}</p>
                          <Button size="sm" variant="destructive" className="mt-2" onClick={() => {
                            fetch(`http://localhost:8000/api/v1/knowledge?source=${btoa(doc.source)}`, { method: 'DELETE' })
                              .then(() => setKbDocs(kbDocs.filter(d => d.source !== doc.source)));
                          }}>Удалить</Button>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === 'subscriptions' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                    <div className="flex justify-between items-center mb-6">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Email Подписки и Отчеты</h3>
                        <p className="text-xs text-slate-500 mt-1">Управление рассылками и фоновыми агентами</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Button size="sm" onClick={handleTriggerWatcher} className="bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border border-indigo-500/20 shadow-[0_0_15px_rgba(99,102,241,0.1)]">
                          <Zap className="w-4 h-4 mr-2" /> Запустить Watcher
                        </Button>
                        <Button size="sm" className="bg-gradient-to-r from-primary to-indigo-500 hover:from-primary/90 hover:to-indigo-500/90 text-white shadow-lg shadow-primary/20 border-0">
                          Создать подписку
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {subs.length === 0 && <div className="text-slate-500 text-sm">Нет активных подписок</div>}
                      {subs.map((sub, idx) => (
                        <div key={idx} className="flex items-center justify-between p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                          <div>
                            <p className="font-medium text-white">{sub.email}</p>
                            <p className="text-sm text-slate-400">Отчет: {sub.report_type} • Расписание: {sub.schedule}</p>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={`px-2 py-1 rounded text-xs font-semibold ${sub.active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                              {sub.active ? 'Active' : 'Paused'}
                            </span>
                            <Button size="sm" variant="outline" className="border-rose-500 text-rose-500 hover:bg-rose-500/10" onClick={() => {
                              fetch(`http://localhost:8000/api/v1/subscriptions/${sub.id}`, { method: 'DELETE' })
                                .then(() => setSubs(subs.filter(s => s.id !== sub.id)));
                            }}>Удалить</Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === 'schema' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2"><Database className="w-4 h-4" /> ClickHouse Schema</h3>
                      <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800/50 text-xs font-mono text-slate-300 max-h-64 overflow-y-auto whitespace-pre-wrap">
                        {dbSchema || 'Загрузка схемы...'}
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-4">
                        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2"><BookOpen className="w-4 h-4" /> WrenAI Semantic Context</h3>
                        <Button size="sm" className="bg-gradient-to-r from-primary to-indigo-500 hover:from-primary/90 hover:to-indigo-500/90 text-white shadow-lg shadow-primary/20 border-0">Добавить правило</Button>
                      </div>
                      <div className="space-y-2">
                        {semanticRules.length === 0 && <div className="text-slate-500 text-sm">Нет семантических правил</div>}
                        {semanticRules.map((rule, idx) => (
                          <div key={idx} className="p-3 rounded bg-slate-800/50 border border-slate-700/50 flex flex-col gap-1">
                            <div className="flex justify-between">
                              <span className="font-semibold text-white">{rule.name}</span>
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${rule.active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                                {rule.active ? 'ACTIVE' : 'INACTIVE'}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400">{rule.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'dropzone' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                    <div className="flex justify-between items-center mb-6">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Файлы в очереди ETL</h3>
                        <p className="text-xs text-slate-500 mt-1">Ожидают загрузки в DWH (ClickHouse)</p>
                      </div>
                      <div className="relative">
                        <input 
                          type="file" 
                          accept=".csv"
                          onChange={handleUploadDropzone}
                          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        />
                        <Button size="sm" className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white shadow-lg shadow-emerald-500/20 border-0 pointer-events-none">
                          <UploadCloud className="w-4 h-4 mr-2" /> Загрузить CSV
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {dropzoneFiles.length === 0 && <div className="text-slate-500 text-sm">Очередь загрузки пуста</div>}
                      {dropzoneFiles.map((f, idx) => (
                        <div key={idx} className="flex items-center justify-between p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                          <div>
                            <p className="font-medium text-white">{f.name}</p>
                            <p className="text-sm text-slate-400">{(f.size / 1024).toFixed(1)} KB • {new Date(f.modified * 1000).toLocaleString()}</p>
                          </div>
                          <Button size="sm" variant="destructive" onClick={() => {
                            fetch(`http://localhost:8000/api/v1/dropzone/${f.name}`, { method: 'DELETE' })
                              .then(() => setDropzoneFiles(dropzoneFiles.filter(file => file.name !== f.name)));
                          }}>Удалить</Button>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
