import { TrendingDown, Navigation, Phone, Copy, Check, ChevronDown, ChevronUp } from "lucide-react"
import { useState, useEffect } from "react"
export default function OfferCard({ offers = [], shop }) {
  const [copied, setCopied] = useState(false)
  const [openIndex, setOpenIndex] = useState(null)

  useEffect(() => {
    if (openIndex === null) return
    const close = () => setOpenIndex(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [openIndex])

  if (!offers.length) return null
  const offer = offers[0]
  const activeOffer = offers[openIndex ?? 0]

  const logoUrl = shop?.logo ? `https://coupown.in/storage/${shop.logo}` : null
  const shopName    = shop?.name        || offer.shop_name || 'Unknown Shop'
  const phone       = shop?.phone       || offer.phone     || ''
  const latitude    = shop?.latitude    ?? offer.latitude  ?? null
  const longitude   = shop?.longitude   ?? offer.longitude ?? null
  const rawDistance = shop?.distance_km ?? offer.distance_km ?? null

  const offerHeading = offer.offer_heading || 'Special Offer'
  const category     = activeOffer.category_name || shop?.category || ''
  const description  = activeOffer.description   || ''

  const parseQuillDescription = (raw) => {
    if (!raw) return ''
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) {
        return parsed.map(op => typeof op.insert === 'string' ? op.insert : '').join('').trim()
      }
      return raw
    } catch {
      return raw.replace(/<[^>]*>/g, '').trim()
    }
  }

  const descriptionText = parseQuillDescription(description)
  const actualPrice = activeOffer.actual_price != null ? Number(activeOffer.actual_price) : null
  const offerPrice  = activeOffer.offer_price  != null ? Number(activeOffer.offer_price)  : null
  const startDate   = activeOffer.start_date ? new Date(activeOffer.start_date).toLocaleDateString('en-IN') : ''
  const endDate     = activeOffer.end_date   ? new Date(activeOffer.end_date).toLocaleDateString('en-IN')   : ''

  const distance =
    rawDistance !== null && rawDistance !== undefined && isFinite(Number(rawDistance))
      ? Number(rawDistance).toFixed(1)
      : null

  const hasCoords = latitude !== null && latitude !== undefined &&
                    longitude !== null && longitude !== undefined

  const discount =
    actualPrice && offerPrice && actualPrice > offerPrice
      ? Math.round(((actualPrice - offerPrice) / actualPrice) * 100)
      : null

  const handleMapClick = () => {
    if (hasCoords)
      window.open(`https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`, '_blank')
  }

  const handleCall = () => {
    if (phone) window.location.href = `tel:${phone}`
  }

  const handleCopyPhone = async () => {
    if (!phone) return
    try {
      await navigator.clipboard.writeText(phone)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleDownloadApp = () => {
    window.open('https://play.google.com/store/apps/details?id=com.coupown.mobile', '_blank')
  }


  return (
    <div className="group relative rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-md p-4 sm:p-5
      shadow-[0_8px_32px_-12px_rgba(0,0,0,0.4)]
      hover:border-primary/40 hover:bg-white/[0.06]
      hover:shadow-[0_0_60px_-15px_rgba(251,154,0,0.2)]
      hover:-translate-y-1.5
      active:scale-[0.99]
      transition-all duration-300 ease-out
      overflow-hidden">

      {/* Top glow line on hover */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent
        opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

      <div className="flex flex-col gap-3.5">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="flex-shrink-0 w-9 h-9 rounded-full border-[3px] border-primary overflow-hidden bg-white/[0.05] ring-2 ring-primary/40">
              {logoUrl
                ? <img src={logoUrl} alt={shopName} className="w-full h-full object-cover" />
                : <div className="w-full h-full flex items-center justify-center text-primary font-bold text-sm">
                    {(shopName || '?')[0].toUpperCase()}
                  </div>
              }
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base sm:text-lg font-semibold text-white/90 truncate
                group-hover:text-primary transition-colors duration-200">
                {shopName}
              </h3>
              {offerHeading && (
                <p className="mt-1 text-[11px] sm:text-xs text-white/40 truncate">
                  {offerHeading}
                </p>
              )}
            </div>
          </div>

          <div className="flex-shrink-0 flex items-center gap-2">
            {discount !== null && (
              <div className="rounded-xl bg-primary/10 border border-primary/20 px-2.5 py-1.5 sm:px-3 sm:py-2
                group-hover:bg-primary/15 group-hover:border-primary/30 transition-all duration-200">
                <div className="flex items-center justify-center gap-1">
                  <TrendingDown size={12} className="text-primary" />
                  <span className="text-xs sm:text-sm font-bold text-primary">{discount}% OFF</span>
                </div>
              </div>
            )}
            {hasCoords && (
              <button
                onClick={handleMapClick}
                className="flex-shrink-0 p-2 rounded-xl border border-white/10 bg-white/[0.04]
                  hover:border-primary/40 hover:bg-primary/10 active:scale-95 transition-all duration-200"
                title="Get directions"
                aria-label="Get directions on map">
                <img src="/directions_new.png" alt="directions" className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
            )}
          </div>
        </div>

        {/* Divider */}
        <div className="h-px bg-white/5" />

        {/* Offer details chip */}
        <div className="rounded-xl bg-white/[0.02] border border-white/5 p-2.5 sm:p-3
          group-hover:border-white/10 transition-colors duration-200">

          <p className="text-[9px] sm:text-[10px] uppercase tracking-widest text-white/30 mb-2">Offer details</p>

          {/* Offer badge row */}
          <div className="flex flex-wrap gap-1.5 sm:gap-2">
            {offers.map((o, i) => {
              const hasImg = o?.offer_image && o.offer_image.trim() !== ''
              return ( 
                <button
                  key={i}
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setOpenIndex(openIndex === i ? null : i) }}
                  disabled={!hasImg}
                  className="rounded-lg bg-primary/10 border border-primary/20 px-2 py-1 sm:px-2.5 sm:py-1.5
                    text-[11px] sm:text-xs text-primary font-medium flex items-center gap-1.5
                    transition-all duration-150 select-none
                    disabled:cursor-default
                    enabled:cursor-pointer enabled:hover:bg-primary/20 enabled:active:scale-95"
                  style={{ maxWidth: '100%' }}>
                  <img src="/offer.png" alt="offer" className="w-4 h-4 sm:w-5 sm:h-5 shrink-0" />
                  <span className="truncate">{o.offer_heading || 'Special Offer'}</span>
                  {hasImg && (
                    <span className="shrink-0 ml-1">
                      {openIndex === i ? <ChevronUp size={12} className="text-primary/70" /> : <ChevronDown size={12} className="text-primary/70" />}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {openIndex !== null && offers[openIndex]?.offer_image && (
            <div className="mt-2.5 rounded-xl overflow-hidden cursor-pointer" onClick={() => setOpenIndex(null)}>
              <div className="relative w-full bg-black/20 rounded-xl overflow-hidden" style={{ aspectRatio: '16/9' }}>
                <img
                  src={offers[openIndex].offer_image}
                  alt="Offer image"
                  className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                  onError={(e) => { e.target.style.display = 'none' }}
                />
              </div>
              {(startDate || endDate) && (
                  <div className="mt-1.5 text-[11px] text-white/40">
                    {startDate}{startDate && endDate && ' → '}{endDate}
                  </div>
                )}
            </div>
          )}
          {/* Pricing */}
          {(actualPrice !== null || offerPrice !== null) && (
            <div className="flex items-baseline gap-3 mt-2.5">
              {offerPrice !== null && (
                <span className="text-xl sm:text-2xl font-bold text-primary">
                  ₹{offerPrice.toLocaleString('en-IN')}
                </span>
              )}
              {actualPrice !== null && actualPrice !== offerPrice && (
                <span className="text-sm text-white/30 line-through">
                  ₹{actualPrice.toLocaleString('en-IN')}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Description */}
        {descriptionText && (
          <div className="rounded-xl bg-white/[0.02] border border-white/5 px-2.5 py-2 sm:px-3 sm:py-2.5
            text-[11px] sm:text-xs text-white/50 line-clamp-2 leading-relaxed
            hover:border-white/10 transition-colors duration-200">
            {descriptionText}
          </div>
        )}

        {/* Location & Distance */}
        <div className="grid gap-2 grid-cols-2">
          {category && (
            <div className="flex items-center gap-2 rounded-xl bg-white/[0.02] border border-white/5
              px-2.5 py-2 sm:px-3 sm:py-2.5
              hover:border-primary/20 hover:bg-white/[0.04] transition-all duration-200">
              <span className="text-[11px] sm:text-xs text-white/70 truncate">{category}</span>
            </div>
          )}
          {distance !== null && (
            <div className="flex items-center gap-2 rounded-xl bg-white/[0.02] border border-white/5
              px-2.5 py-2 sm:px-3 sm:py-2.5
              hover:border-primary/20 hover:bg-white/[0.04] transition-all duration-200">
              <Navigation size={14} className="flex-shrink-0 text-primary/70" />
              <span className="text-[11px] sm:text-xs text-white/70 whitespace-nowrap">~{distance} km</span>
            </div>
          )}
        </div>

        {/* Phone */}
        {phone && (
          <div className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.02] border border-white/5
            px-2.5 py-2 sm:px-3 sm:py-2.5
            hover:border-primary/20 hover:bg-white/[0.04] transition-all duration-200">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <Phone size={14} className="flex-shrink-0 text-primary/70" />
              <span className="text-[11px] sm:text-xs text-white/70 truncate font-mono">{phone}</span>
            </div>
            <button
              type="button"
              onClick={handleCopyPhone}
              className="flex-shrink-0 p-1.5 rounded-lg hover:bg-primary/10 active:scale-95
                transition-all duration-200 text-white/40 hover:text-primary"
              title="Copy phone number">
              {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
            </button>
          </div>
        )}

        {/* Call Button */}
        <button
          type="button"
          onClick={handleCall}
          disabled={!phone}
          className="w-full rounded-xl border border-primary/30 bg-primary/10 px-4 py-2.5
            text-xs sm:text-sm font-medium text-primary
            hover:border-primary/50 hover:bg-primary/20 hover:shadow-[0_0_20px_-5px_rgba(251,154,0,0.3)]
            active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200 flex items-center justify-center gap-2">
          <Phone size={16} />
          {phone ? 'Call Now' : 'No Phone Available'}
        </button>

        {/* Download App Button */}
        <button
          type="button"
          onClick={handleDownloadApp}
          className="w-full rounded-xl border border-primary/30 bg-primary/10 px-4 py-2.5
            text-xs sm:text-sm font-medium text-primary
            hover:border-primary/50 hover:bg-primary/20 hover:shadow-[0_0_20px_-5px_rgba(251,154,0,0.3)]
            active:scale-[0.98] transition-all duration-200 flex items-center justify-center gap-2">
          <img src="/download.png" alt="download" className="w-4 h-4 sm:w-5 sm:h-5" />
          More Info
        </button>

      </div>
    </div>
  )
}