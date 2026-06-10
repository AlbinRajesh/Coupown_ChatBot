import { useState, useEffect, useRef } from 'react'
import { Send, Loader, MapPin, X } from 'lucide-react'

const SUGGESTIONS = [
  'Try "food nearby"',
  'Try "offers on biriyani"',
  'Try "nearby auto"',
  'Try "job vacancy"',
  'Try "drinks"',
]

export default function SearchBar({ onSearch, loading = false, onActiveChange }) {
  const [query, setQuery] = useState('')
  const [radius, setRadius] = useState(25)
  const [focused, setFocused] = useState(false)
  const [locationEnabled, setLocationEnabled] = useState(false)
  const [locationDenied, setLocationDenied] = useState(false)
  const [userLocation, setUserLocation] = useState(null)
  const [distanceFilterOpen, setDistanceFilterOpen] = useState(false)
  const [locationName, setLocationName] = useState('')
  const [selectedImage, setSelectedImage] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [placeholderIndex, setPlaceholderIndex] = useState(0)
  const [placeholderVisible, setPlaceholderVisible] = useState(true)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)

  // Cycle placeholder text with slide-up animation
  useEffect(() => {
    const interval = setInterval(() => {
    setPlaceholderVisible(false)
    setTimeout(() => {
      setPlaceholderIndex((prev) => (prev + 1) % SUGGESTIONS.length)
      setPlaceholderVisible(true)
    }, 500)
  }, 3500)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const stored = localStorage.getItem('coraLocationPermission')
    if (stored === 'granted') {
      setLocationEnabled(true)
      requestUserLocation()
    } else if (stored === 'denied') {
      setLocationDenied(true)
      setLocationEnabled(false)
    }
  }, [])

  useEffect(() => {
    const handleFocus = () => {
      if (locationEnabled) requestUserLocation()
    }
    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [locationEnabled])

  const getLocationName = async (lat, lng) => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`
      )
      const data = await res.json()
      const city =
        data.address?.city ||
        data.address?.town ||
        data.address?.village ||
        'Current Location'
      setLocationName(city)
    } catch {
      setLocationName('Current Location')
    }
  }

  const requestUserLocation = () => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords
        setUserLocation({ lat, lng })
        setLocationEnabled(true)
        setLocationDenied(false)
        localStorage.setItem('coraLocationPermission', 'granted')
        getLocationName(lat, lng)
      },
      () => {
        setLocationDenied(true)
        setLocationEnabled(false)
        localStorage.setItem('coraLocationPermission', 'denied')
      }
    )
  }

  const handleLocationClick = () => {
    if (!locationEnabled && !locationDenied) {
      requestUserLocation()
      setDistanceFilterOpen(true)
    } else if (locationEnabled) {
      setDistanceFilterOpen((v) => !v)
    }
  }

  const handleAttachClick = () => {
    fileInputRef.current?.click()
  }

const handleFileChange = (e) => {
  const file = e.target.files?.[0]
  if (!file) return

  const isImage = file.type.startsWith('image/')
  const isSupported = isImage || file.type === 'application/pdf' ||
    file.type === 'application/msword' ||
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    file.type === 'text/plain'

  if (!isSupported) {
    alert('Unsupported file type. Please upload an image, PDF, Word doc, or text file.')
    e.target.value = ''
    return
  }

  if (isImage) {
    setSelectedFile(null)
    setSelectedImage(file)
    const reader = new FileReader()
    reader.onloadend = () => setImagePreview(reader.result)
    reader.readAsDataURL(file)
  } else {
    setSelectedImage(null)
    setImagePreview(null)
    setSelectedFile(file)
  }

  e.target.value = ''
}

  const removeImage = () => {
  setSelectedImage(null)
  setImagePreview(null)
  setSelectedFile(null)
}

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!query.trim() || loading) return
    onSearch(query, radius, userLocation)
    setQuery('')
    setDistanceFilterOpen(false)
    onActiveChange?.(false)
    inputRef.current?.focus()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const setFocus = (v) => {
    setFocused(v)
    onActiveChange?.(v || query.length > 0)
  }

  return (
    <>
      <style>{`
      @keyframes placeholderSlideUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 0.3; transform: translateY(0); }
      }
      @keyframes placeholderSlideOut {
        from { opacity: 0.3; transform: translateY(0); }
        to   { opacity: 0; transform: translateY(-12px); }
      }
      .placeholder-enter {
        animation: placeholderSlideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards;
      }
      .placeholder-exit {
        animation: placeholderSlideOut 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards;
      }
      .placeholder-wrapper {
        overflow: hidden;
        pointer-events: none;
      }
    `}</style>

      <div className="fixed bottom-8 left-0 right-0 z-20 flex flex-col items-center gap-3 px-5 md:bottom-10">

        {/* Distance Filter Panel */}
        {locationEnabled && distanceFilterOpen && (
          <div className="w-full max-w-xl rounded-2xl border border-white/5 bg-white/[0.02] px-5 py-3 backdrop-blur-md shadow-[0_8px_32px_-12px_rgba(0,0,0,0.4)]">
            <div className="flex items-center justify-between text-xs uppercase tracking-wider text-foreground/50 mb-3">
              <span>Search radius</span>
              <span className="font-mono text-primary">{radius} km</span>
            </div>
            <input
              type="range"
              min={1}
              max={500}
              value={radius}
              onChange={(e) => setRadius(Number(e.target.value))}
              className="w-full accent-primary"
              style={{
                background: `linear-gradient(to right, var(--primary) 0%, var(--primary) ${(radius / 500) * 100}%, oklch(1 0 0 / 0.08) ${(radius / 500) * 100}%, oklch(1 0 0 / 0.08) 100%)`,
                height: '4px',
                borderRadius: '999px',
                WebkitAppearance: 'none',
                appearance: 'none',
              }}
            />
            <div className="mt-1.5 flex justify-between text-[10px] text-foreground/30">
              <span>1 km</span>
              <span>500 km</span>
            </div>
          </div>
        )}

        {/* Location Pill */}
        {locationEnabled && locationName && (
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full border border-white/10 bg-white/[0.06] backdrop-blur-md">
            <MapPin className="w-3 h-3 text-primary" />
            <span className="text-[11px] text-foreground/60 tracking-wide">{locationName}</span>
            <span className="text-[11px] text-foreground/20">·</span>
            <span className="text-[11px] text-primary tabular-nums">{radius} km</span>
          </div>
        )}

        {/* Image Preview */}
        {(imagePreview || selectedFile) && (
          <div className="w-full max-w-xl flex justify-start">
            <div className="relative">
              {imagePreview ? (
                <div className="h-16 w-16 rounded-lg bg-white/5 border border-white/10">
                  <img src={imagePreview} alt="preview" className="h-full w-full rounded-lg object-cover" />
                </div>
              ) : (
                <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl border border-white/10 bg-white/[0.05] backdrop-blur-md max-w-[220px]">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-[12px] text-foreground/80 font-medium truncate leading-tight">
                      {selectedFile.name}
                    </span>
                    <span className="text-[10px] text-foreground/40 uppercase tracking-wide mt-0.5">
                      {selectedFile.name.split('.').pop()} · {(selectedFile.size / 1024).toFixed(0)} KB
                    </span>
                  </div>
                </div>
              )}
              <button
                onClick={removeImage}
                className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-white hover:brightness-110 transition-all active:scale-95"
                title="Remove"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}

        {/* Search Input */}
        <div
          className={`w-full max-w-xl flex items-center gap-2 rounded-[22px] border bg-white/[0.04] p-2 pl-4 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.5)] backdrop-blur-2xl transition-all duration-300 ${
            focused
              ? 'border-primary/40 bg-white/[0.06] shadow-[0_0_50px_-15px_rgba(251,154,0,0.25)] scale-[1.01] -translate-y-0.5'
              : 'border-white/10'
          }`}
        >
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf,.doc,.docx,.txt"
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Attach / + button */}
          <button
            type="button"
            onClick={handleAttachClick}
            aria-label="Upload image"
            title="Upload image"
            className={`h-7 w-7 shrink-0 flex items-center justify-center rounded-full border transition-all duration-200 active:scale-95 ${
              imagePreview || selectedFile
                ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-white/10 bg-white/[0.06] text-foreground/50 hover:text-primary hover:border-primary/40 hover:bg-primary/10'
            }`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>

          {/* Location button */}
          <button
            type="button"
            onClick={handleLocationClick}
            aria-label="Toggle location"
            disabled={locationDenied}
            title={locationEnabled ? 'Toggle distance filter' : 'Enable location'}
            className={`h-5 w-5 shrink-0 transition ${
              locationEnabled
                ? 'text-primary cursor-pointer hover:text-primary/80'
                : locationDenied
                  ? 'text-foreground/20 cursor-not-allowed'
                  : 'text-foreground/40 hover:text-foreground/60 cursor-pointer'
            }`}
          >
            <img src="/adjust.png" alt="adjust" className="w-5 h-5" />
          </button>
          {locationDenied && (
            <button
              type="button"
              onClick={() => {
                localStorage.removeItem('coraLocationPermission')
                setLocationDenied(false)
              }}
              className="text-[10px] text-foreground/30 hover:text-primary underline"
            >
              reset location
            </button>
          )}

          {/* Input + animated placeholder wrapper */}
          <div className="relative flex-1 flex items-center">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                onActiveChange?.(focused || e.target.value.length > 0)
              }}
              onKeyDown={handleKeyDown}
              onFocus={() => setFocus(true)}
              onBlur={() => setFocus(false)}
              placeholder=""
              className="w-full bg-transparent py-3 text-base text-foreground outline-none"
              disabled={loading}
              autoComplete="off"
              spellCheck="false"
            />

            {/* Animated placeholder — only shown when input is empty */}
            {!query && (
              <div className="placeholder-wrapper absolute left-0 top-0 bottom-0 flex items-center">
                <span
                  key={placeholderIndex}
                  className={`text-sm text-foreground/20 whitespace-nowrap tracking-wide ${
                    placeholderVisible ? 'placeholder-enter' : 'placeholder-exit'
                  }`}
                >
                  {SUGGESTIONS[placeholderIndex]}
                </span>
              </div>
            )}
          </div>

          <button
            onClick={handleSubmit}
            disabled={loading || !query.trim()}
            aria-label="Send"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_4px_20px_-6px_rgba(251,154,0,0.5)] transition hover:brightness-110 hover:shadow-[0_6px_28px_-6px_rgba(251,154,0,0.6)] active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? <Loader size={15} className="animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>

        {/* Footer hint */}
        <p className="text-[11px] tracking-wide">
          <span className="text-white/[0.35]">©Copyright</span>
          <span className="text-white/[0.55]"> BossApp Studio Pvt Ltd</span>
          <span className="text-white/[0.35]">. All Rights Reserved</span>
        </p>
      </div>
    </>
  )
}