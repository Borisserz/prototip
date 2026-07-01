import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../store/useChatStore';
import { API_BASE } from '../lib/config';

// ws-url строим из API_BASE (http→ws), токен кидаем query-параметром — backend проверяет до handshake
function buildChatSocketUrl(): string | null {
  const token = localStorage.getItem('jwt_token');
  if (!token) return null;
  const wsBase = API_BASE.replace(/^http/, 'ws');
  return `${wsBase}/ws/chat?token=${encodeURIComponent(token)}`;
}

export function useChatSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typewriterIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  const setWsConnected = useChatStore((state) => state.setSocketConnected);
  const setMessages = useChatStore((state) => state.setMessages);
  const setIsLoading = useChatStore((state) => state.setIsLoading);
  const addMessage = useChatStore((state) => state.addMessage);
  const setIsStreaming = useChatStore((state) => state.setIsStreaming);

  const connectWebSocketRef = useRef<((retryCount: number) => void) | null>(null);

  const connectWebSocket = useCallback((retryCount = 0) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = buildChatSocketUrl();
    if (!url) {
      // Пользователь не залогинен — откладываем подключение.
      setWsConnected(false);
      return;
    }
    wsRef.current = new WebSocket(url);
    
    wsRef.current.onopen = () => {
      setWsConnected(true);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "status") {
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role === "assistant" && last.content.includes("...")) {
            return [...prev.slice(0, -1), { ...last, content: data.content }];
          } else if (last.role === "assistant") {
            return [...prev.slice(0, -1), { ...last, content: `${last.content}\n\n${data.content}` }];
          }
          return prev;
        });
      } else if (data.type === "debate") {
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          const newDebates = [...(last.debates || []), { role: data.role, content: data.content }];
          return [...prev.slice(0, -1), { ...last, debates: newDebates }];
        });
      } else if (data.type === "node_event") {
        useChatStore.getState().setActiveNode(data.node);
      } else if (data.type === "pipeline_update") {
        useChatStore.getState().setPipelineStages(data.stages);
      } else if (data.type === "result") {
        if (typewriterIntervalRef.current) clearInterval(typewriterIntervalRef.current);
        
        setIsStreaming(true);
        // разбиваем на слова, новые строки — отдельный токен
        const tokens = data.content.split(/(\n)/);
        const words: string[] = [];
        tokens.forEach((tok: string) => {
          if (tok === '\n') { words.push('\n'); }
          else { tok.split(' ').forEach((w: string) => { if (w !== '') words.push(w); }); }
        });

        let currentText = "";
        let i = 0;
        const CHUNK = 3;
        const DELAY = 40;

        typewriterIntervalRef.current = setInterval(() => {
          if (i < words.length) {
            const slice = words.slice(i, i + CHUNK);
            const toAdd = slice.map((w, idx) => {
              if (w === '\n') return '\n';
              // пробел перед словом, если предыдущий символ не \n и idx>0 или currentText не пуст
              const needSpace = (currentText.length > 0 || i > 0) && idx === 0 && w !== '\n' && !currentText.endsWith('\n');
              return (needSpace ? ' ' : '') + w;
            }).join('');
            currentText += toAdd;
            i += CHUNK;
            const isLast = i >= words.length;
            setMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              return [...prev.slice(0, -1), {
                ...last,
                role: "assistant",
                content: currentText,
                isStreaming: !isLast,
                // мета: pptx/excel/sql прицепляем только когда анимация закончилась
                ...(isLast ? {
                  pptx_path: data.pptx_path,
                  excel_path: data.excel_path,
                  sql: data.sql,
                } : {}),
              }];
            });
            if (isLast) {
              if (typewriterIntervalRef.current) clearInterval(typewriterIntervalRef.current);
              setIsStreaming(false);
              setIsLoading(false);
              useChatStore.getState().setActiveNode(null);
            }
          } else {
            if (typewriterIntervalRef.current) clearInterval(typewriterIntervalRef.current);
            setIsStreaming(false);
            setIsLoading(false);
            useChatStore.getState().setActiveNode(null);
          }
        }, DELAY);
      } else if (data.type === "error") {
        setIsLoading(false);
        setIsStreaming(false);
        useChatStore.getState().setActiveNode(null);
        addMessage({ role: "assistant", content: `Ошибка: ${data.content}` });
      }
    };
    
    wsRef.current.onclose = () => {
      setWsConnected(false);
      const timeout = Math.min(10000, Math.pow(2, retryCount) * 1000);
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocketRef.current?.(retryCount + 1);
      }, timeout);
    };
    
    wsRef.current.onerror = () => {
      wsRef.current?.close();
    };
  }, [setWsConnected, setMessages, setIsLoading, addMessage, setIsStreaming]);
  useEffect(() => {
    connectWebSocketRef.current = connectWebSocket;
  }, [connectWebSocket]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (typewriterIntervalRef.current) clearInterval(typewriterIntervalRef.current);
      wsRef.current?.close();
    };
  }, [connectWebSocket]);

  const sendMessage = useCallback((content: string, sessionId?: string | null, drilldown?: { key: string; value: string; action: string }) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setIsLoading(true);
      addMessage({ role: 'user', content });
      addMessage({ role: 'assistant', content: 'Ожидание ответа...' });
      const payload: any = { 
        message: content,
        session_id: sessionId
      };
      if (drilldown) {
        payload.drilldown = drilldown;
      }
      wsRef.current.send(JSON.stringify(payload));
    }
  }, [addMessage, setIsLoading]);

  return { sendMessage };
}
