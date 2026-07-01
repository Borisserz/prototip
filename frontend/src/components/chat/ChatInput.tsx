import React, { useRef } from 'react';
import { Send, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ChatInputProps {
  inputMessage: string;
  setInputMessage: (val: string) => void;
  handleSendMessage: () => void;
  loading: boolean;

}

export const ChatInput: React.FC<ChatInputProps> = ({ inputMessage, setInputMessage, handleSendMessage, loading }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  return (
    <div className="p-6 bg-gradient-to-t from-background via-background to-transparent border-t border-white/5 relative z-10">
      <div className="max-w-4xl mx-auto">
        <div className="relative group">
          <div className="absolute -inset-1 bg-slate-800/50 rounded-xl blur-sm opacity-50"></div>
          <div className="relative flex items-center bg-slate-900 border border-slate-700 rounded-xl p-1.5 shadow-xl">
            <Input
              className="flex-1 bg-transparent border-0 focus-visible:ring-0 text-white placeholder:text-slate-500 text-base h-10 px-3"
              placeholder="Задайте вопрос аналитику (например, 'Какая динамика налогов за год?')"
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
              disabled={loading}
            />
            <Button 
              onClick={handleSendMessage} 
              disabled={loading || !inputMessage.trim()}
              className="shrink-0 bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:text-white text-slate-300 rounded-md h-10 w-12 p-0 flex items-center justify-center shadow-sm transition-colors ml-1"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <div className="text-center mt-3 text-xs text-slate-500">
          Prototip BI Analytics Engine • Powered by Agentic Architecture
        </div>
      </div>
    </div>
  );
};
