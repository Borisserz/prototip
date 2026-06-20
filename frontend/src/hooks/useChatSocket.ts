import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../store/useChatStore';
import { API_BASE } from '../lib/config';

// WS-URL выводится из API_BASE (http→ws, https→wss), а не хардкодится.
// P0-1: токен передаётся query-параметром — backend валидирует его до accept().
function buildChatSocketUrl(): string | null {
  const token = localStorage.getItem('jwt_token');
  if (!token) return null; // без токена не подключаемся (бэкенд всё равно отклонит)
  const wsBase = API_BASE.replace(/^http/, 'ws');
  return `${wsBase}/ws/chat?token=${encodeURIComponent(token)}`;
}

export function useChatSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  const setWsConnected = useChatStore((state) => state.setSocketConnected);
  const setMessages = useChatStore((state) => state.setMessages);
  const setIsLoading = useChatStore((state) => state.setIsLoading);
  const addMessage = useChatStore((state) => state.addMessage);

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
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          return [...prev.slice(0, -1), { 
            ...last, 
            role: "assistant", 
            content: data.content, 
            pptx_path: data.pptx_path,
            sql: data.sql
          }];
        });
        setIsLoading(false);
        useChatStore.getState().setActiveNode(null);
      } else if (data.type === "error") {
        setIsLoading(false);
        useChatStore.getState().setActiveNode(null);
        addMessage({ role: "assistant", content: `Ошибка: ${data.content}` });
      }
    };
    
    wsRef.current.onclose = () => {
      setWsConnected(false);
      const timeout = Math.min(10000, Math.pow(2, retryCount) * 1000);
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket(retryCount + 1);
      }, timeout);
    };
    
    wsRef.current.onerror = () => {
      wsRef.current?.close();
    };
  }, [setWsConnected, setMessages, setIsLoading, addMessage]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
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
