import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, Send, Menu, KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { RoleBadge } from '@/components/RoleBadge';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { EmptyState } from '@/components/chat/EmptyState';
import { ThinkingBubble } from '@/components/chat/ThinkingBubble';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { CHAT } from '@/constants/testIds';

// `api` and `navigate` are stable references and intentionally omitted from
// dependency arrays where React documentation guarantees stability.

export default function Chat() {
  const { conversationId: routeConvId } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(routeConvId || null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const scrollRef = useRef(null);

  const loadConversations = useCallback(async () => {
    try {
      const { data } = await api.get('/chat/conversations');
      setConversations(data);
    } catch (err) {
      console.warn('[chat] failed to load conversations', err?.response?.status || err?.message);
    }
  }, []);

  const loadMessages = useCallback(async (id) => {
    setLoadingMessages(true);
    try {
      const { data } = await api.get(`/chat/conversations/${id}/messages`);
      setMessages(data);
    } catch (err) {
      console.error('[chat] failed to load conversation messages', err);
      toast.error('Failed to load conversation');
      setActiveConvId(null);
      setMessages([]);
      navigate('/chat', { replace: true });
    } finally {
      setLoadingMessages(false);
    }
  }, [navigate]);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  useEffect(() => {
    if (routeConvId && routeConvId !== activeConvId) setActiveConvId(routeConvId);
  }, [routeConvId, activeConvId]);

  useEffect(() => {
    if (activeConvId) loadMessages(activeConvId);
    else setMessages([]);
  }, [activeConvId, loadMessages]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const newConversation = useCallback(() => {
    setActiveConvId(null);
    setMessages([]);
    setSidebarOpen(false);
    navigate('/chat', { replace: true });
  }, [navigate]);

  const selectConversation = useCallback((id) => {
    setActiveConvId(id);
    setSidebarOpen(false);
    navigate(`/chat/${id}`, { replace: true });
  }, [navigate]);

  const deleteConversation = useCallback(async (id, e) => {
    e.stopPropagation();
    // eslint-disable-next-line no-alert
    if (!window.confirm('Delete this conversation?')) return;
    try {
      await api.delete(`/chat/conversations/${id}`);
      toast.success('Conversation deleted');
      if (activeConvId === id) newConversation();
      await loadConversations();
    } catch (err) {
      console.error('[chat] delete conversation failed', err);
      toast.error('Failed to delete conversation');
    }
  }, [activeConvId, loadConversations, newConversation]);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || sending) return;
    setSending(true);

    const tempUser = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: q,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUser]);
    setInput('');

    try {
      const { data } = await api.post('/chat/ask', {
        question: q,
        conversation_id: activeConvId,
      });
      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.id !== tempUser.id);
        return [...withoutTemp, data.user_message, data.assistant_message];
      });
      if (!activeConvId) {
        setActiveConvId(data.conversation_id);
        navigate(`/chat/${data.conversation_id}`, { replace: true });
      }
      loadConversations();
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || 'Something went wrong.';
      const msg = typeof detail === 'string' ? detail : 'Request failed';

      console.error('[chat] ask failed', status, msg);
      setMessages((prev) => prev.filter((m) => m.id !== tempUser.id));
      setInput(q);

      if (status === 429) toast.error('Rate limit reached (NIM free tier). Please wait a moment.');
      else if (status === 401) { logout(); navigate('/login'); }
      else if (status === 403) toast.error('Your account is not approved yet.');
      else toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const activeConversation = useMemo(
    () => conversations.find((conv) => conv.id === activeConvId),
    [conversations, activeConvId],
  );

  return (
    <div className="chat-shell text-slate-100">
      <div className="top-nav z-30 border-b border-white/8 backdrop-blur-md bg-[hsl(var(--background))]/60 flex items-center justify-between gap-2 px-2 sm:px-4">
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
          <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden shrink-0 text-slate-300 hover:bg-white/5">
                <Menu className="w-4 h-4" strokeWidth={1.75} />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="p-0 bg-[hsl(var(--background))] border-white/8 w-[min(20rem,88vw)]">
              <ChatSidebar
                user={user}
                conversations={conversations}
                activeConvId={activeConvId}
                onNew={newConversation}
                onSelect={selectConversation}
                onDelete={deleteConversation}
              />
            </SheetContent>
          </Sheet>
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-400/30 flex items-center justify-center shrink-0">
              <Shield className="w-4 h-4 text-cyan-300" strokeWidth={1.75} />
            </div>
            <span className="font-display font-bold text-lg hidden sm:inline truncate">
              SENTRY<span className="text-cyan-300">/RAG</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          <div className="flex items-center gap-1.5 sm:gap-2 border border-white/10 bg-white/[0.03] px-1.5 sm:px-2 py-1 rounded-full max-w-[42vw] sm:max-w-none">
            <span data-testid={CHAT.topBarUserEmail} className="font-mono text-[10px] sm:text-[11px] text-slate-200 truncate hidden min-[400px]:inline max-w-[7rem] sm:max-w-[180px]">
              {user?.email}
            </span>
            <RoleBadge role={user?.role} testId={CHAT.topBarRoleBadge} />
          </div>
          {user?.role === 'admin' && (
            <Button
              data-testid={CHAT.goToAdminButton}
              onClick={() => navigate('/admin')}
              variant="outline"
              size="sm"
              className="border-cyan-400/30 bg-cyan-500/8 hover:bg-cyan-500/12 text-cyan-100 px-2 sm:px-3"
            >
              <KeyRound className="w-3.5 h-3.5 sm:mr-1" strokeWidth={1.75} />
              <span className="hidden sm:inline">Admin</span>
            </Button>
          )}
          <Button
            data-testid={CHAT.logoutButton}
            onClick={() => { logout(); navigate('/login'); }}
            variant="ghost"
            size="sm"
            className="text-slate-300 hover:bg-white/5 px-2 sm:px-3"
          >
            <LogOut className="w-3.5 h-3.5 sm:mr-1" strokeWidth={1.75} />
            <span className="hidden sm:inline">Sign out</span>
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex">
        <aside className="hidden lg:flex w-72 border-r border-white/8 bg-black/20" data-testid={CHAT.sidebar}>
          <ChatSidebar
            user={user}
            conversations={conversations}
            activeConvId={activeConvId}
            onNew={newConversation}
            onSelect={selectConversation}
            onDelete={deleteConversation}
          />
        </aside>

        <main className="flex-1 min-w-0 flex flex-col">
          <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-3 sm:px-6 lg:px-8 py-4 sm:py-6">
            <div className="max-w-4xl mx-auto space-y-4 sm:space-y-5">
              {messages.length === 0 && !loadingMessages && <EmptyState role={user?.role} />}
              {messages.map((m) => (<MessageBubble key={m.id} message={m} />))}
              {sending && <ThinkingBubble />}
            </div>
          </div>

          <div className="shrink-0 border-t border-white/8 bg-[hsl(var(--background))]/70 backdrop-blur-md px-2 sm:px-6 py-2.5 sm:py-3 pb-[max(0.625rem,var(--safe-bottom))]">
            <div className="max-w-4xl mx-auto">
              <div className="panel-inset flex items-end gap-2 p-1.5 sm:p-2">
                <Textarea
                  data-testid={CHAT.messageInput}
                  placeholder={user?.role === 'admin' ? 'Ask anything…' : `Ask as ${user?.role}…`}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={sending}
                  rows={1}
                  className="resize-none bg-transparent border-0 focus-visible:ring-0 text-slate-100 placeholder:text-slate-500 max-h-32 sm:max-h-40 min-h-[40px] flex-1 py-2.5 text-base sm:text-sm"
                />
                <Button
                  data-testid={CHAT.sendButton}
                  onClick={sendMessage}
                  disabled={sending || !input.trim()}
                  size="icon"
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium shrink-0 h-10 w-10"
                >
                  <Send className="w-4 h-4" strokeWidth={2} />
                </Button>
              </div>
              <div className="mt-1.5 flex items-center justify-between gap-2 px-1">
                <div className="text-[10px] font-mono text-slate-500 truncate min-w-0">
                  {activeConversation ? activeConversation.title : 'New conversation'}
                </div>
                <div className="text-[10px] font-mono text-slate-500 shrink-0 hidden sm:block">
                  Enter to send · Shift+Enter for newline
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
