import { useState } from 'react'
import { ChevronDown, MoreVertical, Menu } from 'lucide-react'
import Sidebar from './Sidebar'

export default function Header({ onNewChat, onLoadChat, onDeleteChat, savedChats }) {
  const [moreOpen, setMoreOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <>
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { onNewChat(); setSidebarOpen(false) }}
        savedChats={savedChats}
        onLoadChat={(chat) => { onLoadChat(chat); setSidebarOpen(false) }}
        onDeleteChat={onDeleteChat}
      />

      <div className="fixed left-4 top-4 z-50 flex items-center gap-3 md:left-6 md:top-6 select-none">
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label="Toggle sidebar"
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/5 bg-black/60 backdrop-blur-md transition hover:bg-black/80 hover:border-primary/30"
        >
          <Menu className="h-5 w-5 text-white/80" />
        </button>

        <img src="/cora_logo.png" alt="Cora Logo" className="h-10 w-10 md:h-14 md:w-14" />

        <div className="flex flex-col justify-center">
          <div className="flex flex-col items-end relative">
            <div className="flex items-center gap-1.5 leading-none mr-4">
              <span className="text-lg font-semibold tracking-wide text-white md:text-2xl">CORA</span>
              <ChevronDown className="h-3.5 w-3.5 fill-white text-white translate-y-[1px] absolute right-0 top-1" />
            </div>
            <span className="mt-0.5 text-[10px] md:text-xs font-bold tracking-wider text-white mr-4">AI X</span>
          </div>
        </div>
      </div>

      <nav className="fixed left-1/2 top-4 z-30 -translate-x-1/2 md:top-6 hidden md:block">
        <div className="flex items-center gap-6 md:gap-8 h-11 md:h-14 justify-center">
          {['Home', 'Feature', 'Pricing'].map((item) => (
            <button key={item} className="text-xs font-medium tracking-wide text-white/60 transition hover:text-primary md:text-sm">
              {item}
            </button>
          ))}
        </div>
      </nav>

      <div className="fixed right-4 top-4 z-30 md:hidden">
        <div className="relative">
          <button
            onClick={() => setMoreOpen((v) => !v)}
            aria-label="More options"
            className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/5 bg-black/60 backdrop-blur-md transition hover:bg-black/80 hover:border-primary/30"
          >
            <MoreVertical className="h-5 w-5 text-white/80" />
          </button>
          {moreOpen && (
            <div className="fixed inset-0 z-40" onClick={() => setMoreOpen(false)}>
              <div onClick={(e) => e.stopPropagation()} className="absolute right-0 top-14 w-40 rounded-xl border border-white/5 bg-black/95 backdrop-blur-md shadow-lg">
                <nav className="flex flex-col">
                  {['Home', 'Feature', 'Pricing'].map((item) => (
                    <button key={item} onClick={() => setMoreOpen(false)} className="w-full rounded-lg px-4 py-3 text-left text-sm text-white/70 transition hover:bg-white/5 hover:text-primary font-medium border-b border-white/5 last:border-b-0">
                      {item}
                    </button>
                  ))}
                </nav>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}