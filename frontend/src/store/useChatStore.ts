import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  pptx_path?: string;
  excel_path?: string;
  sql?: string;
  debates?: {role: string; content: string}[];
  /** true пока typewriter-анимация ещё идёт */
  isStreaming?: boolean;
}

export type TabType = 'chat' | 'dashboard' | 'presentation' | 'admin';

export interface DashboardHistoryItem {
  id: string;
  title: string;
  timestamp: number;
  data: string;
}

export interface PresentationSlide {
  title: string;
  content?: string;
  chart_type?: string;
  data?: any[];
  png_path?: string;
}

export interface PresentationHistoryItem {
  id: string;
  title: string;
  theme: string;
  timestamp: number;
  pptx_path: string;
  num_slides: number;
  slide_png_paths: string[];
  slides?: any[];
  reasoning?: string;
}

export interface PdfGenerationHistoryItem {
  id: string;
  title: string;
  file_name: string;
  output_type: 'presentation' | 'dashboard';
  timestamp: number;
  doc_summary: string;
  doc_topics: string[];
  doc_type: string;
  num_pages: number;
  // For presentation output
  pptx_path?: string;
  slide_png_paths?: string[];
  slides?: any[];
  // For dashboard output
  dashboard_data?: any;
}

interface ChatState {
  messages: Message[];
  input: string;
  isLoading: boolean;
  isStreaming: boolean;
  socketConnected: boolean;
  activeTab: TabType;
  pinnedCharts: any[];
  layout: any[];
  isAnalystMode: boolean;
  activeNode: string | null;
  pipelineStages: Record<string, any>;
  dashboardHistory: DashboardHistoryItem[];
  activeDashboardId: string | null;
  presentationHistory: PresentationHistoryItem[];
  activePresentationId: string | null;
  pdfGenerations: PdfGenerationHistoryItem[];
  activePdfGenerationId: string | null;
  verifiedEmail: string | null;

  // Actions
  setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
  addMessage: (message: Message) => void;
  updateLastMessage: (content: string) => void;
  setInput: (input: string) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setSocketConnected: (connected: boolean) => void;
  setActiveTab: (tab: TabType) => void;
  pinChart: (chartData: any) => void;
  removePinnedChart: (index: number) => void;
  setLayout: (layout: any[]) => void;
  setAnalystMode: (enabled: boolean) => void;
  setActiveNode: (node: string | null) => void;
  setPipelineStages: (stages: Record<string, any>) => void;
  addDashboard: (item: DashboardHistoryItem) => void;
  setActiveDashboard: (id: string | null) => void;
  deleteDashboard: (id: string) => void;
  addPresentation: (item: PresentationHistoryItem) => void;
  updatePresentation: (id: string, update: Partial<PresentationHistoryItem>) => void;
  setActivePresentation: (id: string | null) => void;
  deletePresentation: (id: string) => void;
  addPdfGeneration: (item: PdfGenerationHistoryItem) => void;
  deletePdfGeneration: (id: string) => void;
  setActivePdfGeneration: (id: string | null) => void;
  setVerifiedEmail: (email: string | null) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      input: '',
      isLoading: false,
      isStreaming: false,
      socketConnected: false,
      activeTab: 'chat',
      pinnedCharts: [],
      layout: [],
      isAnalystMode: false,
      activeNode: null,
      pipelineStages: {},
      dashboardHistory: [],
      activeDashboardId: null,
      presentationHistory: [],
      activePresentationId: null,
      pdfGenerations: [],
      activePdfGenerationId: null,
      verifiedEmail: null,

      setMessages: (messages) => set((state) => ({
        messages: typeof messages === 'function' ? messages(state.messages) : messages
      })),
      
      addMessage: (message) => set((state) => ({
        messages: [...state.messages, message]
      })),

      updateLastMessage: (content) => set((state) => {
        if (state.messages.length === 0) return state;
        const newMessages = [...state.messages];
        newMessages[newMessages.length - 1] = {
          ...newMessages[newMessages.length - 1],
          content: newMessages[newMessages.length - 1].content + content
        };
        return { messages: newMessages };
      }),

      setInput: (input) => set({ input }),
      setIsLoading: (isLoading) => set({ isLoading }),
      setIsStreaming: (isStreaming) => set({ isStreaming }),
      setSocketConnected: (socketConnected) => set({ socketConnected }),
      setActiveTab: (activeTab) => set({ activeTab }),
      
      pinChart: (chartData) => set((state) => {
        const newItem = { i: `pinned-${state.pinnedCharts.length}`, x: (state.pinnedCharts.length * 4) % 12, y: Infinity, w: 4, h: 4 };
        return {
          pinnedCharts: [...state.pinnedCharts, chartData],
          layout: [...state.layout, newItem]
        };
      }),
      
      removePinnedChart: (index) => set((state) => {
        const newPinned = [...state.pinnedCharts];
        newPinned.splice(index, 1);
        const newLayout = state.layout.filter((_, i) => i !== index);
        return { pinnedCharts: newPinned, layout: newLayout };
      }),
      
      setLayout: (layout) => set({ layout }),
      setAnalystMode: (isAnalystMode) => set({ isAnalystMode }),
      setActiveNode: (activeNode) => set({ activeNode }),
      setPipelineStages: (pipelineStages) => set({ pipelineStages }),

      addDashboard: (item) => set((state) => ({ 
        dashboardHistory: [item, ...state.dashboardHistory],
        activeDashboardId: item.id
      })),
      setActiveDashboard: (id) => set({ activeDashboardId: id }),
      deleteDashboard: (id) => set((state) => {
        const newHistory = state.dashboardHistory.filter(d => d.id !== id);
        const newActiveId = state.activeDashboardId === id 
          ? (newHistory.length > 0 ? newHistory[0].id : null) 
          : state.activeDashboardId;
        return { dashboardHistory: newHistory, activeDashboardId: newActiveId };
      }),

      addPresentation: (item) => set((state) => ({
        presentationHistory: [item, ...state.presentationHistory],
        activePresentationId: item.id,
      })),
      updatePresentation: (id, update) => set((state) => ({
        presentationHistory: state.presentationHistory.map(p => 
          p.id === id ? { ...p, ...update } : p
        )
      })),
      setActivePresentation: (id) => set({ activePresentationId: id }),
      deletePresentation: (id) => set((state) => ({
        presentationHistory: state.presentationHistory.filter(p => p.id !== id),
        activePresentationId: state.activePresentationId === id ? null : state.activePresentationId
      })),

      addPdfGeneration: (item) => set((state) => ({
        pdfGenerations: [item, ...state.pdfGenerations],
        activePdfGenerationId: item.id,
      })),
      deletePdfGeneration: (id) => set((state) => ({
        pdfGenerations: state.pdfGenerations.filter(p => p.id !== id),
        activePdfGenerationId: state.activePdfGenerationId === id ? null : state.activePdfGenerationId,
      })),
      setActivePdfGeneration: (id) => set({ activePdfGenerationId: id }),

      setVerifiedEmail: (email) => set({ verifiedEmail: email }),
    }),
    {
      name: 'prototip-chat-store',
      partialize: (state) => ({
        dashboardHistory: state.dashboardHistory,
        activeDashboardId: state.activeDashboardId,
        presentationHistory: state.presentationHistory,
        activePresentationId: state.activePresentationId,
        pdfGenerations: state.pdfGenerations,
        activePdfGenerationId: state.activePdfGenerationId,
      }),
    }
  )
);
