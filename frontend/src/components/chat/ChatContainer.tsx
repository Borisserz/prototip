import React, { useRef, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import { AgentGraph } from './AgentGraph';
import { useChatStore } from '../../store/useChatStore';

interface ChatContainerProps {
  onPin: (content: string) => void;
  onChartClick: (prompt: string, drilldown?: { key: string; value: string; action: string }) => void;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({ onPin, onChartClick }) => {
  const messages = useChatStore((state) => state.messages);
  const isLoading = useChatStore((state) => state.isLoading);
  const activeNode = useChatStore((state) => state.activeNode);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeNode]);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 custom-scrollbar">
      <div className="max-w-5xl mx-auto space-y-8 pb-10">
        {messages.map((msg, i) => (
          <MessageBubble 
            key={i} 
            msg={msg} 
            isLastLoading={isLoading && i === messages.length - 1 && msg.content === ""} 
            onPin={onPin}
            onChartClick={onChartClick}
          />
        ))}
        <AgentGraph />
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};
