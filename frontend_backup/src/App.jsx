import { useState, useRef, useEffect } from 'react'
import Header from './components/Header'
import ChatBox from './components/ChatBox'
import SearchBar from './components/SearchBar'
import PricingPage from './components/PricingPage'
import FeaturePage from './components/FeaturePage'

export default function App() {
  const [messages, setMessages] = useState([])
  const [chatHistory, setChatHistory] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)
  const [savedChats, setSavedChats] = useState([])
  const [loading, setLoading] = useState(false)
  const [userLocation, setUserLocation] = useState(null)
  const [locationNudge, setLocationNudge] = useState(false)
  const [requestingLocation, setRequestingLocation] = useState(false)
  const [searchActive, setSearchActive] = useState(false)
  const [currentPage, setCurrentPage] = useState('home')
  const chatEndRef = useRef(null)

  // Load saved chats on mount
  useEffect(() => {
    const stored = localStorage.getItem('chatHistory')
    if (stored) {
      try { setSavedChats(JSON.parse(stored)) } catch { }
    }
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const requestGeolocation = () => {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error('Not supported')); return }
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const { latitude: lat, longitude: lng } = pos.coords
          setUserLocation({ lat, lng })
          resolve({ lat, lng })
        },
        (err) => reject(err)
      )
    })
  }

  useEffect(() => {
    requestGeolocation().catch(() => setUserLocation(null))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleEnableLocation = async () => {
    setRequestingLocation(true)
    try {
      await requestGeolocation()
      setLocationNudge(false)
    } catch { }
    finally { setRequestingLocation(false) }
  }

  const handleNewChat = () => {
    setMessages([])
    setChatHistory([])
    setCurrentChatId(null)
    setLocationNudge(false)
  }

  const handleLoadChat = (chat) => {
    setMessages(chat.messages)
    setChatHistory(chat.chatHistory)
    setCurrentChatId(chat.id)
    setLocationNudge(false)
  }

  const handleDeleteChat = (chatId) => {
    setSavedChats((prev) => {
      const updated = prev.filter((c) => c.id !== chatId)
      localStorage.setItem('chatHistory', JSON.stringify(updated))
      return updated
    })
    if (chatId === currentChatId) {
      setMessages([])
      setChatHistory([])
      setCurrentChatId(null)
    }
  }

  const handleSearch = async (query, radiusKm = 25, locationOverride = null) => {
    if (!query.trim()) return
    const loc = locationOverride || userLocation

    const userMsg = { id: Date.now(), type: 'user', text: query, timestamp: new Date() }
    const currentMessages = [...messages, userMsg]
    setMessages(currentMessages)
    setLoading(true)
    setLocationNudge(false)

    const updatedHistory = [...chatHistory, { role: 'user', content: query }]

    try {
      const response = await fetch('/api/smart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          userLat: loc?.lat ?? null,
          userLng: loc?.lng ?? null,
          radiusKm,
          messages: updatedHistory
        })
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      if (data.no_location && data.results?.length > 0) setLocationNudge(true)

      const replyText = data.message || data.reply || `Found ${data.total_results || 0} results`
      // Deduplicate results by shop name to prevent showing same shop twice
      const rawResults = data.results || []
      const dedupedResults = (data.is_offer_search || data.is_shop_offer_search)
        ? rawResults.filter((r, idx, arr) =>
            arr.findIndex(x => (x.name || x.shop_name) === (r.name || r.shop_name)) === idx
          )
        : rawResults

      const aiMsg = {
        id: Date.now() + 1,
        type: 'ai',
        text: replyText,
        results: dedupedResults,
        resultType: data.is_job_search ? 'jobs' : (data.is_offer_search || data.is_shop_offer_search) ? 'offers' : data.is_product_search ? 'products' : data.is_service_search ? 'services' : 'shops',
        timestamp: new Date()
      }

      const finalMessages = [...currentMessages, aiMsg]
      const finalHistory = [...updatedHistory, { role: 'assistant', content: replyText }]

      setMessages(finalMessages)
      setChatHistory(finalHistory)

      // Save snapshot
      const snapId = currentChatId || Date.now()
      setCurrentChatId(snapId)
      setSavedChats((prev) => {
        const snap = {
          id: snapId,
          title: query.substring(0, 30),
          timestamp: new Date().toLocaleString(),
          messages: finalMessages,
          chatHistory: finalHistory
        }
        const updated = [snap, ...prev.filter(c => c.id !== snapId)].slice(0, 10)
        localStorage.setItem('chatHistory', JSON.stringify(updated))
        return updated
      })

    } catch {
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, type: 'ai', text: 'Something went wrong. Please try again.', results: [], timestamp: new Date() }
      ])
    } finally {
      setLoading(false)
    }
  }


  if (currentPage === 'feature') {
  return (
    <FeaturePage
      onNavigate={setCurrentPage}
      savedChats={savedChats}
      onNewChat={handleNewChat}
      onLoadChat={handleLoadChat}
      onDeleteChat={handleDeleteChat}
    />
  )
}

if (currentPage === 'pricing') {
  return (
    <PricingPage
      onNavigate={setCurrentPage}
      savedChats={savedChats}
      onNewChat={handleNewChat}
      onLoadChat={handleLoadChat}
      onDeleteChat={handleDeleteChat}
    />
  )
}
return (
  <div className="fixed inset-0 flex flex-col overflow-hidden bg-background text-foreground">

    <div className="pointer-events-none absolute inset-0 z-0">
      <div className={`absolute left-1/2 top-1/2 h-[500px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-hero-glow blur-3xl transition-opacity duration-500 ${searchActive ? 'opacity-0' : 'opacity-20'}`} />
    </div>
    <div className="pointer-events-none absolute inset-0 z-0 grid-noise opacity-30" />

    <Header
    savedChats={savedChats}
    onNewChat={handleNewChat}
    onLoadChat={handleLoadChat}
    onDeleteChat={handleDeleteChat}
    onNavigate={setCurrentPage}
  />

    {/* Spacer that matches the fixed header height */}
    <div className="shrink-0 h-20 md:h-24" />

    {/* Scrollable middle */}
    <div className="relative z-10 flex-1 overflow-y-auto hide-scrollbar overscroll-none">
      <ChatBox
        hidden={searchActive || messages.length > 0}
        messages={messages}
        loading={loading}
        scrollRef={chatEndRef}
      />
      <div className="relative z-10 flex-1 overflow-y-auto hide-scrollbar overscroll-none"></div>

      {locationNudge && (
        <div className="fixed bottom-[160px] left-0 right-0 z-30 flex justify-center px-5">
          <div className="w-full max-w-xl flex items-center justify-between gap-3 rounded-xl border border-amber-700/40 bg-amber-950/60 px-4 py-2.5 text-sm text-amber-300 backdrop-blur-sm">
            <div className="flex items-center gap-2 min-w-0">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
                <path fillRule="evenodd" d="M11.54 22.351l.07.04.028.016a.76.76 0 00.723 0l.028-.015.071-.041a16.975 16.975 0 001.144-.742 19.58 19.58 0 002.683-2.282c1.944-2.003 3.5-4.697 3.5-8.333 0-4.36-3.515-7.994-8-7.994S4 3.641 4 8.001c0 3.636 1.556 6.33 3.5 8.333a19.583 19.583 0 002.683 2.282 16.975 16.975 0 001.144.742l.07.04zM12 10.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" clipRule="evenodd" />
              </svg>
              <span className="truncate">Showing top-rated shops — enable location to find shops near you.</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button onClick={handleEnableLocation} disabled={requestingLocation} className="rounded-md bg-amber-700/60 px-3 py-1 text-xs font-medium text-amber-100 transition hover:bg-amber-600/60 disabled:opacity-60">
                {requestingLocation ? 'Requesting…' : 'Enable Location'}
              </button>
              <button onClick={() => setLocationNudge(false)} className="rounded-md p-1 text-amber-400 transition hover:bg-amber-900/40">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>

    {/* Spacer that matches the fixed search bar height */}
    <div className="shrink-0 h-44" />

    <SearchBar
      onSearch={handleSearch}
      loading={loading}
      onActiveChange={setSearchActive}
    />
  </div>
)
}