import React, { useState } from 'react';
import { LogOut, Menu, Settings, Database, FolderUp, Mail, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/App";
import { useChatStore } from "../../store/useChatStore";
import { WorkspaceModal } from "./WorkspaceModal";

interface HeaderProps {
  isSidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  wsConnected: boolean;
  username: string;
  setAdminOpen: (open: boolean) => void;
  handleLogout: () => void;
  onNewChat: () => void;
  onProfileClick: () => void;
  onSubscriptionsClick: () => void;
}

export const Header: React.FC<HeaderProps> = ({ isSidebarOpen, setSidebarOpen, wsConnected, username, setAdminOpen, handleLogout, onNewChat, onProfileClick, onSubscriptionsClick }) => {
  const isAnalystMode = useChatStore((state) => state.isAnalystMode);
  const setAnalystMode = useChatStore((state) => state.setAnalystMode);

  return (
    <>
    <header className="h-20 border-b border-white/10 glass-panel flex items-center justify-between px-8 shrink-0">
      <div className="flex items-center gap-4">
        {!isSidebarOpen && (
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(true)} className="text-slate-400 hover:text-white hover:bg-white/10 mr-2 transition-transform hover:scale-105">
            <Menu className="w-6 h-6" />
          </Button>
        )}
        <div className="group cursor-default">
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2 drop-shadow-md">
            Prototip <span className="text-gradient group-hover:animate-pulse">BI</span>
          </h1>
          <p className="text-sm text-slate-400 font-light">Enterprise AI Assistant</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <Button 
          variant="ghost" 
          onClick={onNewChat} 
          className="flex items-center gap-2 text-violet-400 hover:text-white hover:bg-violet-500/20 transition-colors"
        >
          <MessageSquarePlus className="w-4 h-4" />
          <span className="text-sm font-medium hidden md:inline">Новый чат</span>
        </Button>
        
        <Button 
          variant="ghost" 
          onClick={onSubscriptionsClick} 
          className="flex items-center gap-2 text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <Mail className="w-4 h-4" />
          <span className="text-sm font-medium hidden md:inline">Рассылки</span>
        </Button>

        <button 
          onClick={onProfileClick}
          className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 hover:bg-slate-700/50 rounded-lg border border-slate-700/50 shadow-sm transition-colors group cursor-pointer"
        >
          <div className="w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center relative">
            <span className="text-xs font-bold text-primary uppercase">{username.substring(0, 1)}</span>
            <div className={cn("absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-slate-900", wsConnected ? "bg-emerald-400" : "bg-red-500")}></div>
          </div>
          <span className="text-sm text-slate-300 font-medium group-hover:text-white">{username}</span>
        </button>
      </div>
    </header>
    </>
  );
};
