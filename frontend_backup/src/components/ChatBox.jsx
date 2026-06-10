import { Loader } from 'lucide-react'
import ResultCard from './ResultCard'
import JobCard from './JobCard'
import OfferCard from './OfferCard'
import coraLogo from '/cora_logo.png'

export default function ChatBox({ hidden = false, messages = [], loading = false, scrollRef }) {
  const chatActive = messages.length > 0 || loading

  return (
    <main className="flex flex-col items-center px-3 sm:px-5 w-full">

      {/* Hero Title */}
      {!chatActive && (
        <div className={`flex flex-col items-center justify-center min-h-[50vh] transition-all duration-500 ease-out ${
          hidden ? 'pointer-events-none opacity-0 blur-sm' : 'opacity-100'
        }`}>
          <h1 className="font-display sm:text-5xl md:text-6xl tracking-tight text-glow select-none text-7xl font-extrabold">
            Hello, CORA
          </h1>
        </div>
      )}

      {/* Messages */}
      {chatActive && (
        <div className="w-full max-w-3xl flex flex-col gap-5 py-6">
          {messages.map((msg) => (
            <div key={msg.id} className="flex flex-col gap-3">

              {/* User message */}
              {msg.type === 'user' && (
                <div className="flex justify-end">
                  <div className="max-w-[75%] sm:max-w-sm rounded-2xl rounded-br-sm
                    bg-primary/15 border border-primary/25
                    px-4 py-2.5
                    text-sm sm:text-base text-white/90
                    backdrop-blur-sm">
                    {msg.text}
                  </div>
                </div>
              )}

              {/* AI message */}
              {msg.type === 'ai' && (
                <div className="flex flex-col gap-3">
                  {msg.text && (
                    <div className="flex items-start gap-2.5">
                      <img
                        src={coraLogo}
                        alt="CORA"
                        className="mt-0.5 h-5 w-5 sm:h-6 sm:w-6 shrink-0 rounded-full object-cover"
                      />
                      <p className="text-sm sm:text-base text-white/70 leading-relaxed">
                        {msg.text}
                      </p>
                    </div>
                  )}

                  {/* Result Cards */}
                  {msg.results && msg.results.length > 0 && (
                  <div className="pl-7 sm:pl-8 grid gap-3 grid-cols-1 sm:grid-cols-2">
                    {msg.results.map((result, idx) => {
                      if (msg.resultType === 'jobs')
                        return <JobCard key={idx} job={result} />

                      if (msg.resultType === 'offers') {
                        if (result.offers?.length > 0)
                          return <OfferCard key={idx} offers={result.offers} shop={result} />
                        if (result.offer_heading)
                          return <OfferCard key={idx} offer={result} shop={result} />
                        return <ResultCard key={idx} shop={result} />
                      }

                      if (msg.resultType === 'products') {
                        const shopWithOffer = result.has_offer ? {
                          id: result.id,
                          name: result.shop_name || result.name,
                          phone: result.phone || result.shop_phone,
                          logo: result.logo || result.shop_logo,
                          city: result.city,
                          arearoadname: result.arearoadname,
                          nearbylandmark: result.nearbylandmark,
                          latitude: result.latitude,
                          longitude: result.longitude,
                          rating: result.rating,
                          review_count: result.review_count,
                          category: result.category,
                          subcategory: result.subcategory,
                          distance_km: result.distance_km,
                          offers: [{ offer_heading: result.offer_heading }]
                        } : result
                        return <ResultCard key={idx} shop={shopWithOffer} />
                      }

                      if (msg.resultType === 'services') {
                        const shopWithOffer = result.has_offer ? {
                          id: result.id,
                          name: result.shop_name || result.name,
                          phone: result.phone || result.shop_phone,
                          logo: result.logo || result.shop_logo,
                          city: result.city,
                          arearoadname: result.arearoadname,
                          nearbylandmark: result.nearbylandmark,
                          latitude: result.latitude,
                          longitude: result.longitude,
                          rating: result.rating,
                          review_count: result.review_count,
                          category: result.category,
                          subcategory: result.subcategory,
                          distance_km: result.distance_km,
                          offers: [{ offer_heading: result.offer_heading }]
                        } : result
                        return <ResultCard key={idx} shop={shopWithOffer} />
                      }

                      return <ResultCard key={idx} shop={result} />
                    })}
                  </div>
                )}
                </div>
                )}

                </div>
                ))}

          {/* Loading */}
          {loading && (
            <div className="flex items-center gap-2.5">
              <img
                src={coraLogo}
                alt="CORA"
                className="h-5 w-5 sm:h-6 sm:w-6 shrink-0 rounded-full object-cover animate-pulse"
              />
              <div className="flex items-center gap-2 text-white/30">
                <Loader size={13} className="animate-spin text-primary/60" />
                <span className="text-sm">Searching nearby...</span>
              </div>
            </div>
          )}

          <div ref={scrollRef} />
        </div>
      )}
    </main>
  )
}