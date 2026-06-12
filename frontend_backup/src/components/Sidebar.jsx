import { X, Plus, MessageSquare, Trash2, Clock } from 'lucide-react'

export default function Sidebar({ isOpen, onClose, onNewChat, savedChats = [], onLoadChat, onDeleteChat }) {
  const handleDeleteChat = (e, chatId) => {
    e.stopPropagation()
    onDeleteChat(chatId)
  }

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Panel */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-white/5 bg-black/90 backdrop-blur-2xl transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-11 pt-28 pb-4 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-primary shadow-[0_0_8px_var(--primary)]" />
              <span className="text-sm font-semibold tracking-wide text-white/80">Chat History</span>
            </div>
        </div>

        {/* New Chat Button */}
        <div className="px-4 pt-4 shrink-0">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white/70 transition hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/20 text-primary">
              <Plus size={14} />
            </span>
            New Chat
          </button>
        </div>

        {/* Chat List */}
        <div className="flex-1 overflow-y-auto px-4 pt-4 pb-4 space-y-1 custom-scrollbar">
          <p className="px-1 pb-2 text-[10px] uppercase tracking-[0.3em] text-white/25">Recent</p>

          {savedChats.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
              <Clock size={20} className="text-white/20" />
              <p className="text-xs text-white/30">No chats yet</p>
            </div>
          ) : (
            savedChats.map((chat) => (
              <div
                key={chat.id}
                onClick={() => onLoadChat(chat)}
                className="group relative w-full cursor-pointer rounded-xl border border-transparent px-3 py-3 transition hover:border-white/5 hover:bg-white/[0.04]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-white/70 group-hover:text-white/90 transition">
                      {chat.title}
                    </p>
                    <p className="mt-0.5 text-[10px] text-white/25">{chat.timestamp}</p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteChat(e, chat.id)}
                    className="shrink-0 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition p-2 rounded-md hover:bg-red-500/10 active:bg-red-500/20 text-red-400/60 hover:text-red-400"
                    title="Delete"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>  
              </div>
            ))
          )}
        </div>

        {/* Footer Tip */}
        <div className="shrink-0 px-4 pb-5">
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <div className="flex items-start gap-3">
              <MessageSquare size={14} className="mt-0.5 shrink-0 text-primary/60" />
              <div>
                <p className="text-xs font-medium text-white/60">Tip</p>
                <p className="mt-1 text-[11px] leading-5 text-white/30">
                  Try "Good plumber nearby" or "Best coffee shops" for better results.
                </p>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}