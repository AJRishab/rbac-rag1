import React from 'react';
import { MessageSquare, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RoleBadge } from '@/components/RoleBadge';
import { CHAT } from '@/constants/testIds';
import { cn } from '@/lib/utils';

export function ChatSidebar({ user, conversations, activeConvId, onNew, onSelect, onDelete }) {
  return (
    <div className="flex flex-col w-full h-full min-h-0">
      <div className="p-3 border-b border-white/8 shrink-0">
        <Button
          data-testid={CHAT.newConversationButton}
          onClick={onNew}
          className="w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400 font-medium shadow-[0_0_0_1px_rgba(34,211,238,0.35)]"
        >
          <Plus className="w-4 h-4 mr-1" strokeWidth={2} />
          New conversation
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-2">
        {conversations.length === 0 ? (
          <div className="text-xs text-slate-500 px-3 py-4 font-mono">No conversations yet.</div>
        ) : (
          <ul className="space-y-1">
            {conversations.map((c) => (
              <ConversationItem
                key={c.id}
                conversation={c}
                active={c.id === activeConvId}
                onSelect={onSelect}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}
      </div>
      <div className="p-3 border-t border-white/8 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-md bg-white/[0.04] border border-white/10 flex items-center justify-center text-xs font-mono text-slate-300 shrink-0">
            {(user?.email?.[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-slate-100 truncate">{user?.email}</div>
            <div className="mt-0.5"><RoleBadge role={user?.role} /></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConversationItem({ conversation, active, onSelect, onDelete }) {
  const { id, title, updated_at } = conversation;
  return (
    <li>
      <button
        data-testid={CHAT.conversationItem}
        onClick={() => onSelect(id)}
        className={cn(
          'group relative w-full text-left rounded-lg px-3 py-2.5 hover:bg-white/[0.04] transition-colors flex items-start gap-2',
          active && 'bg-white/[0.06] border border-cyan-400/25 shadow-[0_0_0_1px_rgba(34,211,238,0.18)]',
        )}
      >
        <MessageSquare className="w-3.5 h-3.5 text-slate-400 mt-1 shrink-0" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="text-sm text-slate-100 truncate pr-1">{title}</div>
          <div className="text-[10px] font-mono text-slate-500">
            {new Date(updated_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
          </div>
        </div>
        <button
          data-testid={CHAT.conversationItemDelete}
          onClick={(e) => onDelete(id, e)}
          className="opacity-100 sm:opacity-0 sm:group-hover:opacity-100 text-slate-400 hover:text-red-300 transition-opacity p-1.5 -mr-1 shrink-0 touch-manipulation"
          title="Delete conversation"
          aria-label="Delete conversation"
        >
          <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
        </button>
      </button>
    </li>
  );
}
