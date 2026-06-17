import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, UploadCloud, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2, Database } from 'lucide-react';
import { Button } from "@/components/ui/button";

interface WorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const WorkspaceModal: React.FC<WorkspaceModalProps> = ({ isOpen, onClose }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setStatus('idle');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setStatus('idle');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      // Determine endpoint based on file type
      const endpoint = file.name.toLowerCase().endsWith('.pdf') 
        ? 'http://localhost:8000/api/v1/upload-pdf' 
        : 'http://localhost:8000/api/v1/workspace/upload';
        
      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
        // Assuming user context is handled via interceptor/headers or backend mock
      });
      
      const data = await res.json();
      if (res.ok) {
        setStatus('success');
        setMessage(data.message || 'Файл успешно загружен в ваше рабочее пространство.');
      } else {
        setStatus('error');
        setMessage(data.detail || 'Ошибка загрузки файла.');
      }
    } catch (e: any) {
      setStatus('error');
      setMessage('Сетевая ошибка при загрузке.');
    } finally {
      setIsUploading(false);
      setFile(null);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md"
          >
            <div className="bg-slate-900 border border-slate-700/50 rounded-2xl shadow-2xl overflow-hidden glass-panel">
              <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
                <h2 className="text-xl font-semibold text-white flex items-center gap-2">
                  <Database className="w-5 h-5 text-primary" /> 
                  Workspace Data
                </h2>
                <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 space-y-6">
                <p className="text-sm text-slate-300 leading-relaxed">
                  Загрузите ваши собственные файлы (Excel, CSV, PDF). Система автоматически создаст таблицу в ClickHouse или добавит PDF в RAG-базу для поиска и генерации презентаций.
                </p>
                
                <div className="border-2 border-dashed border-slate-700 hover:border-primary/50 transition-colors rounded-xl p-8 text-center bg-slate-800/20 relative group cursor-pointer">
                  <input 
                    type="file" 
                    accept=".csv,.xlsx,.xls,.pdf" 
                    onChange={handleFileChange}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                      <UploadCloud className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white mb-1">
                        {file ? file.name : "Нажмите или перетащите файл"}
                      </p>
                      <p className="text-xs text-slate-400">
                        CSV, XLSX, PDF (до 50MB)
                      </p>
                    </div>
                  </div>
                </div>

                {status === 'success' && (
                  <div className="flex items-start gap-3 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
                    <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
                    <p className="text-sm">{message}</p>
                  </div>
                )}
                
                {status === 'error' && (
                  <div className="flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400">
                    <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                    <p className="text-sm">{message}</p>
                  </div>
                )}
                
                <Button 
                  onClick={handleUpload} 
                  disabled={!file || isUploading}
                  className="w-full h-12 bg-primary hover:bg-primary/90 text-white font-medium rounded-xl shadow-lg shadow-primary/20 transition-all disabled:opacity-50"
                >
                  {isUploading ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Загрузка...</>
                  ) : (
                    <><FileSpreadsheet className="w-4 h-4 mr-2" /> Загрузить данные</>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
