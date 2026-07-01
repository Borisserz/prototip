
import React, { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { LayoutDashboard, FolderOpen, MessageSquare, X, UploadCloud, Sparkles, AlertTriangle, CheckCircle2, ShieldAlert, Presentation, Database, LayoutGrid, Settings, LogOut } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

import { useChatStore } from "./store/useChatStore"
import { useChatSocket } from "./hooks/useChatSocket"

import { Header } from "./components/layout/Header"
import { ChatContainer } from "./components/chat/ChatContainer"
import { ChatInput } from "./components/chat/ChatInput"
import { DashboardGrid } from "./components/dashboard/DashboardGrid";
import { DashboardView } from "./components/dashboard/DashboardView";
import { AdminModal } from "./components/admin/AdminModal"
import { DashboardGeneratorModal } from "./components/dashboard/DashboardGeneratorModal"
import { PresentationGeneratorModal } from "./components/presentation/PresentationGeneratorModal"
import { PresentationView } from "./components/presentation/PresentationView"
import { UserProfile } from "./components/profile/UserProfile"
import { SubscriptionsView } from "./components/subscriptions/SubscriptionsView"
import { WorkspaceDBView } from "./components/workspace/WorkspaceDBView"
import { PDFGenerationHub } from "./components/pdf/PDFGenerationHub"
import { AdminConsole } from "./components/admin/AdminConsole"
import { adminApi, isAdminToken } from "./lib/adminApi"
import { Building2, KeyRound, User as UserIcon } from "lucide-react"
import { API_BASE } from "@/lib/config";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const LoginScreen = ({
  onLogin,
  onClientLogin,
}: {
  onLogin: (u: string, p: string) => Promise<void>
  onClientLogin: (apiKey: string) => Promise<void>
}) => {
  const [mode, setMode] = useState<"staff" | "client">("staff")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    if (mode === "staff") await onLogin(username, password)
    else await onClientLogin(apiKey)
    setLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-background">
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-primary/20 blur-[120px]" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-accent/20 blur-[120px]" />

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
      >
        <Card className="w-[400px] glass-panel border-white/10 p-2">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto w-16 h-16 bg-gradient-to-br from-primary to-accent rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-primary/20 animate-pulse-glow">
              <Sparkles className="w-8 h-8 text-white" />
            </div>
            <CardTitle className="text-2xl font-bold text-white tracking-tight">Prototip BI</CardTitle>
            <CardDescription className="text-slate-400 mt-2">Enterprise Analytics Platform</CardDescription>
          </CardHeader>
          <CardContent>
            {/* Переключатель режима входа */}
            <div className="mb-5 flex gap-1 rounded-lg border border-slate-700/50 bg-slate-900/50 p-1">
              <button type="button" onClick={() => setMode("staff")}
                className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium transition-colors",
                  mode === "staff" ? "bg-primary/20 text-primary" : "text-slate-400 hover:text-white")}>
                <UserIcon className="h-4 w-4" /> Сотрудник
              </button>
              <button type="button" onClick={() => setMode("client")}
                className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium transition-colors",
                  mode === "client" ? "bg-primary/20 text-primary" : "text-slate-400 hover:text-white")}>
                <Building2 className="h-4 w-4" /> Заказчик
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {mode === "staff" ? (
                <>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Username</label>
                    <Input value={username} onChange={e => setUsername(e.target.value)}
                      className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-600 h-11 focus-visible:ring-primary"
                      placeholder="admin / FederalAnalyst" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Password</label>
                    <Input type="password" value={password} onChange={e => setPassword(e.target.value)}
                      className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-600 h-11 focus-visible:ring-primary"
                      placeholder="••••••••" />
                  </div>
                </>
              ) : (
                <div className="space-y-1">
                  <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    <KeyRound className="h-3.5 w-3.5" /> API-ключ клиента
                  </label>
                  <Input value={apiKey} onChange={e => setApiKey(e.target.value)}
                    className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-600 h-11 focus-visible:ring-primary"
                    placeholder="Вставьте API-ключ заказчика" />
                  <p className="pt-1 text-[11px] text-slate-600">Ключ выдаётся администратором при создании блока.</p>
                </div>
              )}
              <Button type="submit" className="w-full h-11 bg-gradient-to-r from-primary to-accent hover:opacity-90 text-white font-medium text-lg rounded-xl shadow-lg shadow-primary/20" disabled={loading}>
                {loading ? "Вход…" : mode === "staff" ? "Войти" : "Войти как заказчик"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

const SessionGroup = ({ title, sessions, currentSessionId, setCurrentSessionId, setMessages }: any) => {
  const [isOpen, setIsOpen] = useState(true)
  if (!sessions || sessions.length === 0) return null
  return (
    <div className="mb-4">
      <div 
        className="flex items-center justify-between cursor-pointer mb-2 px-1"
        onClick={() => setIsOpen(!isOpen)}
      >
        <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</h4>
        <span className="text-slate-500 text-xs">{isOpen ? '▼' : '▶'}</span>
      </div>
      {isOpen && (
        <div className="flex flex-col gap-2">
          {sessions.map((s: any) => (
             <div 
               key={s.session_id} 
               className={cn("p-3 rounded-xl border cursor-pointer transition-all", currentSessionId === s.session_id ? "bg-primary/20 border-primary shadow-[0_0_15px_rgba(56,189,248,0.1)]" : "bg-slate-800/30 border-slate-700/50 hover:bg-slate-800")}
               onClick={() => {
                 setCurrentSessionId(s.session_id);
                 fetch(`${API_BASE}/api/v1/sessions/${s.session_id}`, {
                   headers: {
                     'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
                   }
                 })
                   .then(res => res.json())
                   .then(data => {
                     if (data && data.messages) {
                       setMessages(data.messages.map((m: any) => ({
                         role: (m.role === 'system' || m.role === 'bot') ? 'assistant' : m.role,
                         content: m.text || m.content || '',
                         sql: m.sql,
                         pptx_path: m.pptx_path,
                         excel_path: m.excel_path,
                         debates: m.debates
                       })));
                     }
                   });
               }}
             >
               <div className="flex items-center justify-between mb-1">
                 <span className="text-xs text-slate-400 font-mono">#{s.session_id.slice(0,8)}</span>
                 <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded-md text-slate-300">{s.message_count} msgs</span>
               </div>
               <p className="text-xs text-slate-200 line-clamp-2">{s.preview || "No preview available"}</p>
             </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("jwt_token"))
  const [username, setUsername] = useState(localStorage.getItem("username") || "")
  const [isAdmin, setIsAdmin] = useState<boolean>(isAdminToken(localStorage.getItem("jwt_token")))
  
  const messages = useChatStore(state => state.messages)
  const setMessages = useChatStore(state => state.setMessages)
  const inputMessage = useChatStore(state => state.input)
  const setInputMessage = useChatStore(state => state.setInput)
  const dashboardHistory = useChatStore((state) => state.dashboardHistory);
  const activeDashboardId = useChatStore((state) => state.activeDashboardId);
  const setActiveDashboard = useChatStore((state) => state.setActiveDashboard);
  const presentationHistory = useChatStore((state) => state.presentationHistory);
  const activePresentationId = useChatStore((state) => state.activePresentationId);
  const setActivePresentation = useChatStore((state) => state.setActivePresentation);
  const loading = useChatStore(state => state.isLoading)
  const setLoading = useChatStore(state => state.setIsLoading)
  const wsConnected = useChatStore(state => state.socketConnected)
  const pinnedCharts = useChatStore(state => state.pinnedCharts)
  const layouts = useChatStore(state => state.layout)
  const setLayouts = useChatStore(state => state.setLayout)

  const { sendMessage } = useChatSocket()

  // sidebar / вспомогательный UI-стейт
  const [isSidebarOpen, setSidebarOpen] = useState(true)
  const [isAdminOpen, setAdminOpen] = useState(false)
  const [activeSidebarTab, setActiveSidebarTab] = useState<'dashboard'|'generation'|'workspace_db'|'history'|'pdf'>('generation');
  const [mainView, setMainView] = useState<'chat' | 'dashboard' | 'presentation' | 'profile' | 'subscriptions' | 'workspace_db' | 'admin'>('chat');
  const [adminView, setAdminView] = useState<'console' | 'workspace'>('console');
  const [sessions, setSessions] = useState<any[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isDashboardLoaded, setIsDashboardLoaded] = useState(false)
  

  const [isDashModalOpen, setDashModalOpen] = useState(false)
  const [isPresModalOpen, setPresModalOpen] = useState(false)

  // синхронизируем активную вкладку из store с mainView
  const storeActiveTab = useChatStore((s) => s.activeTab);
  useEffect(() => {
    if (storeActiveTab === 'presentation') setMainView('presentation');
    if (storeActiveTab === 'dashboard') setMainView('dashboard');
  }, [storeActiveTab]);

  const [isScanning, setIsScanning] = useState(false)
  const [alerts, setAlerts] = useState<any[]>([
    { id: 1, title: 'Аномалия сбора', description: 'Резкое падение налоговых сборов в регионе "г. Гродно"', severity: 'high', date: '2ч назад' },
    { id: 2, title: 'Подозрительная активность', description: 'Многочисленные попытки запроса данных с нарушениями RLS.', severity: 'medium', date: '5ч назад' }
  ])

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{ role: "assistant", content: "Приветствую! Я ваш аналитик. Готов предоставить данные, построить графики или ответить на бизнес-вопросы." }])
    }
  }, [])

  useEffect(() => {
    const fetchSessions = () => {
      fetch(`${API_BASE}/api/v1/sessions`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
        .then(res => res.json())
        .then(data => {
          setSessions(data.sessions || []);
        })
        .catch(e => console.error(e));
    }

    if (token) {
      fetchSessions();
    }
  }, [token, messages.length])

  useEffect(() => {
    fetch(`${API_BASE}/api/user/dashboard`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(r => r.json())
      .then(data => {
        if (data && data.pinned_charts) {
          useChatStore.setState({ pinnedCharts: data.pinned_charts })
        }
        setIsDashboardLoaded(true);
      })
      .catch(e => {
        console.error("Failed to load dashboard:", e);
        setIsDashboardLoaded(true);
      });
  }, []);

  useEffect(() => {
    if (!isDashboardLoaded) return;
    fetch(`${API_BASE}/api/user/dashboard`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned_charts: pinnedCharts })
    }).catch(e => console.error("Failed to save dashboard:", e));
  }, [pinnedCharts, isDashboardLoaded]);

  const groupedSessions = React.useMemo(() => {
    const groups = {
      today: [] as any[],
      yesterday: [] as any[],
      week: [] as any[],
      older: [] as any[]
    };
    const now = Date.now() / 1000;
    sessions.forEach(s => {
      const ts = s.timestamp || now;
      const diff = now - ts;
      if (diff < 86400) groups.today.push(s);
      else if (diff < 86400 * 2) groups.yesterday.push(s);
      else if (diff < 86400 * 7) groups.week.push(s);
      else groups.older.push(s);
    });
    return groups;
  }, [sessions]);

  const handleLogin = async (u: string, p: string) => {
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p })
      })
      if (!res.ok) throw new Error("Login failed")
      const data = await res.json()
      setToken(data.access_token)
      setUsername(u)
      setIsAdmin(!!data.is_admin)
      localStorage.setItem("jwt_token", data.access_token)
      localStorage.setItem("username", u)
      if (data.is_admin) setMainView('admin')
    } catch (err) {
      alert("Ошибка аутентификации. Доступ запрещен.")
    }
  }

  // Вход заказчика по API-ключу 
  const handleClientLogin = async (apiKey: string) => {
    try {
      const data = await adminApi.clientLogin({ api_key: apiKey })
      setToken(data.access_token)
      setUsername(data.username)
      setIsAdmin(false)
      localStorage.setItem("jwt_token", data.access_token)
      localStorage.setItem("username", data.username)
      setMainView('chat')
    } catch (err: any) {
      alert(err?.message || "Неверный ключ клиента.")
    }
  }

  // Вход «от лица заказчика» из админ-консоли
  const handleImpersonate = (clientToken: string, name: string) => {
    setToken(clientToken)
    setUsername(name)
    setIsAdmin(false)
    localStorage.setItem("jwt_token", clientToken)
    localStorage.setItem("username", name)
    setMessages([{ role: "assistant", content: `Вы вошли как заказчик «${name}». Готов помочь с аналитикой.` }])
    setMainView('chat')
  }

  const handleLogout = () => {
    setToken(null)
    setUsername("")
    setIsAdmin(false)
    localStorage.removeItem("jwt_token")
    localStorage.removeItem("username")
  }

  const handleWorkspaceUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/workspace/upload`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if(res.ok) {
        alert("Успешно загружено! Таблица: " + data.table_name);
      } else {
        alert("Ошибка: " + data.detail);
      }
    } catch (e) {
      alert("Ошибка сети");
    } finally {
      setLoading(false);
    }
  }

  const handleTriggerWatcher = async () => {
    setIsScanning(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/trigger_watcher`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await res.json();
      // Add fake notification for wow effect
      setAlerts([{ id: Date.now(), title: 'Новый отчет', description: data.message, severity: 'medium', date: 'Только что' }, ...alerts]);
    } catch (e) {
      alert("Ошибка при запуске сканирования");
    } finally {
      setIsScanning(false);
    }
  }

  const handlePin = (content: string) => {
    if (!pinnedCharts.includes(content)) {
      useChatStore.getState().pinChart(content)
      setSidebarOpen(true);
      setActiveSidebarTab('dashboard');
    }
  }

  const handleChartClick = (promptText: string, drilldown?: { key: string; value: string; action: string }) => {
    let sid = currentSessionId;
    if (!sid) {
      sid = 'session_' + Date.now();
      setCurrentSessionId(sid);
      setSessions(prev => [{ session_id: sid, message_count: 1, preview: promptText.slice(0, 50), timestamp: Date.now()/1000 }, ...prev]);
    }
    sendMessage(promptText, sid, drilldown);
  }

  const onSend = () => {
    if (!inputMessage.trim() || !token) return;
    let sid = currentSessionId;
    if (!sid) {
      sid = 'session_' + Date.now();
      setCurrentSessionId(sid);
      setSessions(prev => [{ session_id: sid, message_count: 1, preview: inputMessage.slice(0, 50), timestamp: Date.now()/1000 }, ...prev]);
    }
    sendMessage(inputMessage, sid);
    setInputMessage("");
  }

  if (!token) {
    return <LoginScreen onLogin={handleLogin} onClientLogin={handleClientLogin} />
  }

  // для admin-роли — отдельный экран без чата
  if (isAdmin) {
    return (
      <div className="flex h-screen flex-col bg-background overflow-hidden">
        <header className="h-16 shrink-0 border-b border-white/10 glass-panel flex items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-sky-400" />
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight leading-tight">
                Prototip <span className="text-gradient">BI</span>
              </h1>
              <p className="text-[11px] text-slate-400 leading-tight">Панель администрирования</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => setAdminView('console')}
              className={cn("flex items-center gap-2 transition-colors",
                adminView === 'console' ? "text-sky-300 bg-sky-500/15" : "text-slate-400 hover:text-white hover:bg-white/10")}
            >
              <LayoutGrid className="w-4 h-4" />
              <span className="text-sm font-medium hidden md:inline">Блоки</span>
            </Button>
            <Button
              variant="ghost"
              onClick={() => setAdminView('workspace')}
              className={cn("flex items-center gap-2 transition-colors",
                adminView === 'workspace' ? "text-violet-300 bg-violet-500/15" : "text-slate-400 hover:text-white hover:bg-white/10")}
            >
              <Database className="w-4 h-4" />
              <span className="text-sm font-medium hidden md:inline">Workspace БД</span>
            </Button>
            <Button
              variant="ghost"
              onClick={() => setAdminOpen(true)}
              className="flex items-center gap-2 text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <Settings className="w-4 h-4" />
              <span className="text-sm font-medium hidden md:inline">Настройки</span>
            </Button>
            <div className="mx-1 h-6 w-px bg-white/10" />
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 hover:bg-rose-500/20 rounded-lg border border-slate-700/50 text-slate-300 hover:text-rose-200 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span className="text-sm font-medium hidden md:inline">Выйти ({username})</span>
            </button>
          </div>
        </header>

        <AdminModal isOpen={isAdminOpen} onClose={() => setAdminOpen(false)} />

        <div className="flex-1 overflow-hidden">
          {adminView === 'workspace' ? (
            <WorkspaceDBView onBackToChat={() => setAdminView('console')} token={token} />
          ) : (
            <AdminConsole onBack={handleLogout} onImpersonate={handleImpersonate} />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background overflow-hidden relative">
      <div className="absolute top-[-20%] left-[20%] w-[40%] h-[40%] rounded-full bg-primary/10 blur-[150px] pointer-events-none" />
      
      {/* Sidebar Dashboard */}
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.div 
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 450, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="h-full border-r border-white/10 glass-panel flex flex-col z-10 shrink-0"
          >
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap justify-center gap-1 bg-slate-800/50 p-1 rounded-lg">
                    <button onClick={() => setActiveSidebarTab('dashboard')} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-2", activeSidebarTab === 'dashboard' ? "bg-slate-700 text-white shadow-sm border border-slate-600" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50")}>
                      <LayoutDashboard className="w-3 h-3" /> Dashboard
                    </button>
                    <button onClick={() => setActiveSidebarTab('generation')} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-2", activeSidebarTab === 'generation' ? "bg-slate-700 text-white shadow-sm border border-slate-600" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50")}>
                      <Sparkles className="w-3 h-3" /> Генерация
                    </button>
                    <button onClick={() => setActiveSidebarTab('workspace_db')} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-2", activeSidebarTab === 'workspace_db' ? "bg-slate-700 text-white shadow-sm border border-slate-600" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50")}>
                      <Database className="w-3 h-3" /> Workspace БД
                    </button>
                    <button onClick={() => setActiveSidebarTab('pdf')} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-2", activeSidebarTab === 'pdf' ? "bg-slate-700 text-white shadow-sm border border-slate-600" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50")}>
                      <UploadCloud className="w-3 h-3" /> PDF
                    </button>
                    <button onClick={() => setActiveSidebarTab('history')} className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-2", activeSidebarTab === 'history' ? "bg-slate-700 text-white shadow-sm border border-slate-600" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50")}>
                      <MessageSquare className="w-3 h-3" /> История
                    </button>
                  </div>
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)} className="text-slate-400 hover:text-white hover:bg-white/10">
                <X className="w-5 h-5" />
              </Button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
              {activeSidebarTab === 'dashboard' ? (
                <DashboardGrid 
                  pinnedCharts={pinnedCharts}
                  layouts={layouts}
                  setLayouts={setLayouts}
                  setPinnedCharts={(c: any) => useChatStore.setState({ pinnedCharts: c })}
                />
              ) : activeSidebarTab === 'generation' ? (
                <div className="h-full flex flex-col text-slate-400 space-y-6">
                  {/* Action Buttons */}
                  <div className="flex flex-col gap-3">
                    <Button 
                      onClick={() => setDashModalOpen(true)}
                      className="w-full justify-start bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    >
                      <LayoutDashboard className="w-4 h-4 mr-2" />
                      Создать Дашборд
                    </Button>

                    <Button 
                      onClick={() => setPresModalOpen(true)}
                      className="w-full justify-start bg-accent/10 hover:bg-accent/20 text-accent/80 border border-accent/30"
                    >
                      <Sparkles className="w-4 h-4 mr-2" />
                      Сгенерировать Презентацию
                    </Button>

                    <Button
                      onClick={() => setActiveSidebarTab('pdf')}
                      variant="outline"
                      className="w-full justify-start bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30"
                    >
                      <UploadCloud className="w-4 h-4 mr-2" />
                      Генерация из PDF
                    </Button>
                  </div>

                  {/* Generated Dashboards List */}
                  <div className="flex flex-col gap-3 pt-4 border-t border-slate-800">
                    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Сохраненные Дашборды</h3>
                    {dashboardHistory.length > 0 ? (
                      <div className="space-y-2">
                        {dashboardHistory.map(dashboard => (
                          <div 
                            key={dashboard.id}
                            className={`w-full p-3 rounded-lg flex items-center justify-between transition-colors border cursor-pointer group ${
                              activeDashboardId === dashboard.id && mainView === 'dashboard' 
                                ? 'bg-emerald-500/10 border-emerald-500/30' 
                                : 'bg-slate-800/40 hover:bg-slate-800 border-slate-700/50'
                            }`}
                            onClick={() => {
                              setActiveDashboard(dashboard.id);
                              setMainView('dashboard');
                            }}
                          >
                            <div className="flex items-center gap-3 overflow-hidden">
                              <LayoutDashboard className={`w-4 h-4 flex-shrink-0 transition-transform group-hover:scale-110 ${
                                activeDashboardId === dashboard.id && mainView === 'dashboard' ? 'text-emerald-400' : 'text-slate-400 group-hover:text-emerald-400'
                              }`} />
                              <div className="flex flex-col overflow-hidden">
                                <span className={`text-sm font-medium truncate ${
                                  activeDashboardId === dashboard.id && mainView === 'dashboard' ? 'text-emerald-400' : 'text-slate-200'
                                }`}>{dashboard.title}</span>
                                <span className="text-[10px] text-slate-500">{new Date(dashboard.timestamp).toLocaleString('ru-RU')}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 italic px-2">Нет сохраненных дашбордов</p>
                    )}
                  </div>

                  {/* Generated Presentations List */}
                  <div className="flex flex-col gap-3 pt-4 border-t border-slate-800">
                    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Презентации</h3>
                    {presentationHistory.length > 0 ? (
                      <div className="space-y-2">
                        {presentationHistory.map((pres) => (
                          <div
                            key={pres.id}
                            className={`w-full p-3 rounded-lg flex items-center gap-3 transition-colors border cursor-pointer group ${
                              activePresentationId === pres.id && mainView === 'presentation'
                                ? 'bg-accent/10 border-accent/30'
                                : 'bg-slate-800/40 hover:bg-slate-800 border-slate-700/50'
                            }`}
                            onClick={() => {
                              setActivePresentation(pres.id);
                              setMainView('presentation');
                            }}
                          >
                            <Presentation className={`w-4 h-4 flex-shrink-0 ${
                              activePresentationId === pres.id && mainView === 'presentation' ? 'text-accent' : 'text-slate-400 group-hover:text-accent'
                            }`} />
                            <div className="flex flex-col overflow-hidden">
                              <span className={`text-sm font-medium truncate ${
                                activePresentationId === pres.id && mainView === 'presentation' ? 'text-accent' : 'text-slate-200'
                              }`}>{pres.title}</span>
                              <span className="text-[10px] text-slate-500">{pres.num_slides} слайдов · {new Date(pres.timestamp).toLocaleDateString('ru-RU')}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 italic px-2">Нет презентаций</p>
                    )}
                  </div>
                </div>

              ) : activeSidebarTab === 'pdf' ? (
                <div className="h-full flex flex-col">
                  <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-800">
                    <button
                      onClick={() => setActiveSidebarTab('generation')}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-all"
                    >
                      <X className="w-4 h-4" />
                    </button>
                    <div>
                      <p className="text-sm font-bold text-white">Генерация из PDF</p>
                      <p className="text-xs text-slate-500">Загрузите документ и выберите тип</p>
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <PDFGenerationHub token={token} />
                  </div>
                </div>
              ) : activeSidebarTab === 'workspace_db' ? (
                <div className="h-full flex flex-col text-slate-400 space-y-6">
                   <div className="flex flex-col gap-3">
                     <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Менеджер</h3>
                     <Button 
                       variant="outline" 
                       className="w-full justify-start border-violet-700/50 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300"
                       onClick={() => setMainView('workspace_db')}
                     >
                       <Database className="w-4 h-4 mr-2" />
                       Открыть Workspace БД
                     </Button>
                   </div>
                  {loading && <div className="text-xs text-primary flex items-center gap-2"><div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div> Загрузка...</div>}
                </div>
              ) : (
                <div className="flex flex-col">
                  {sessions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center p-6 border border-dashed border-slate-700/50 rounded-2xl bg-slate-800/10 mt-4">
                      <MessageSquare className="w-8 h-8 text-slate-600 mb-2" />
                      <p className="text-xs text-slate-400 text-center">История сессий пуста. Начните диалог с агентом.</p>
                    </div>
                  ) : (
                    <>
                      <SessionGroup title="Сегодня" sessions={groupedSessions.today} currentSessionId={currentSessionId} setCurrentSessionId={setCurrentSessionId} setMessages={setMessages} />
                      <SessionGroup title="Вчера" sessions={groupedSessions.yesterday} currentSessionId={currentSessionId} setCurrentSessionId={setCurrentSessionId} setMessages={setMessages} />
                      <SessionGroup title="Неделю назад" sessions={groupedSessions.week} currentSessionId={currentSessionId} setCurrentSessionId={setCurrentSessionId} setMessages={setMessages} />
                      <SessionGroup title="Ранее" sessions={groupedSessions.older} currentSessionId={currentSessionId} setCurrentSessionId={setCurrentSessionId} setMessages={setMessages} />
                    </>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 z-0">
        <Header 
          isSidebarOpen={isSidebarOpen} 
          setSidebarOpen={setSidebarOpen} 
          wsConnected={wsConnected} 
          username={username} 
          setAdminOpen={setAdminOpen} 
          handleLogout={handleLogout} 
          onNewChat={() => {
            setMessages([{ role: "assistant", content: "Приветствую! Я ваш аналитик. Готов предоставить данные, построить графики или ответить на бизнес-вопросы." }]);
            setCurrentSessionId(null);
            setMainView('chat');
          }}
          onProfileClick={() => setMainView('profile')}
          onSubscriptionsClick={() => setMainView('subscriptions')}
          isAdmin={isAdmin}
          onAdminClick={() => setMainView('admin')}
        />

        {/* Admin Modal */}
        <AdminModal isOpen={isAdminOpen} onClose={() => setAdminOpen(false)} />

        {/* Generator Modals */}
        <DashboardGeneratorModal isOpen={isDashModalOpen} onClose={() => setDashModalOpen(false)} onSuccess={() => setMainView('dashboard')} token={token} />
        <PresentationGeneratorModal isOpen={isPresModalOpen} onClose={() => setPresModalOpen(false)} token={token} />

        {/* Main Content Area */}
        {mainView === 'admin' ? (
          <div className="flex-1 overflow-hidden">
            <AdminConsole onBack={() => setMainView('chat')} onImpersonate={handleImpersonate} />
          </div>
        ) : mainView === 'subscriptions' ? (
          <div className="flex-1 overflow-y-auto bg-slate-900/30 custom-scrollbar relative">
            <SubscriptionsView onBackToChat={() => setMainView('chat')} />
          </div>
        ) : mainView === 'workspace_db' ? (
          <div className="flex-1 overflow-hidden bg-slate-900/30">
            <WorkspaceDBView onBackToChat={() => setMainView('chat')} token={token} />
          </div>
        ) : mainView === 'profile' ? (
          <div className="flex-1 overflow-hidden">
            <UserProfile 
              username={username}
              wsConnected={wsConnected}
              onBack={() => setMainView('chat')}
              handleLogout={handleLogout}
            />
          </div>
        ) : mainView === 'dashboard' ? (
          <div className="flex-1 overflow-hidden bg-slate-900/30 custom-scrollbar">
            <DashboardView onBackToChat={() => setMainView('chat')} />
          </div>
        ) : mainView === 'presentation' ? (
          <div className="flex-1 overflow-hidden p-4">
            <PresentationView onBackToChat={() => setMainView('chat')} />
          </div>
        ) : (
          <>
            <ChatContainer onPin={handlePin} onChartClick={handleChartClick} />
            <ChatInput 
              inputMessage={inputMessage} 
              setInputMessage={setInputMessage} 
              handleSendMessage={onSend} 
              loading={loading}
            />
          </>
        )}
      </div>
    </div>
  )
}