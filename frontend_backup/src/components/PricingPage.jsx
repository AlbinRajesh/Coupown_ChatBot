import Header from './Header'

const handleDownloadApp = () => {
  window.open('https://play.google.com/store/apps/details?id=com.coupown.mobile', '_blank')
}

const plans = [
  {
    name: 'Basic Plan',
    price: '3,999',
    period: '300 Days',
    badge: null,
    border: 'border border-primary/60',
    bg: 'bg-[#0d0d0d]',
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
      </svg>
    ),
    features: [
      'Basic Plan – 300 days.',
      'Allowing 3 branches to be added.',
      '2 GB cloud storage included.',
      'Post unlimited offers/services.',
      'Unlimited customer reach.',
      'Instant push notifications.',
      'Personalized e-mail alerts.',
      '24/7 priority customer support.',
    ],
  },
  {
    name: 'Standard Plan',
    price: '4,999',
    period: '300 Days',
    badge: 'Most Popular',
    border: 'border-2 border-primary',
    bg: 'bg-[#0f0a00]',
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
    features: [
      'Standard Plan – 300 days.',
      'Allowing 7 branches to be added.',
      '2 GB cloud storage included.',
      'Post unlimited offers/services.',
      'Unlimited customer reach.',
      'E-mail & push notifications.',
      '24/7 priority customer support.',
      'Brand visibility on CORA AI platform.',
    ],
  },
]

export default function PricingPage({ onNavigate, savedChats, onNewChat, onLoadChat, onDeleteChat }) {
  return (
    <div className="fixed inset-0 bg-black text-white flex flex-col overflow-hidden">

      <Header
        savedChats={savedChats}
        onNewChat={onNewChat}
        onLoadChat={onLoadChat}
        onDeleteChat={onDeleteChat}
        onNavigate={onNavigate}
      />

      <div className="shrink-0 h-20 md:h-24" />

      {/* Title */}
      <div className="shrink-0 text-center pt-3 pb-2 px-4">
        <h1 className="text-2xl md:text-3xl font-bold tracking-wide text-primary mb-1">
          Pick Your Plan
        </h1>
        <p className="text-[10px] text-white/30 tracking-widest uppercase">
          Powered by CORA · Private by default
        </p>
      </div>

      {/* Cards */}
      <div className="
        flex-1 min-h-0
        flex flex-row
        overflow-x-auto overflow-y-hidden
        snap-x snap-mandatory scroll-smooth
        hide-scrollbar
        md:overflow-visible
        md:justify-center
        md:items-center
        gap-4 md:gap-8
        px-5 md:px-10
        py-4 md:py-6
      ">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`
              w-[78vw] shrink-0 snap-center
              md:w-full md:max-w-[360px] md:shrink
              rounded-2xl ${plan.border} ${plan.bg}
              p-5 md:p-7
              flex flex-col items-center text-center relative
            `}
          >
            {plan.badge && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-black text-[9px] font-extrabold tracking-widest px-4 py-1 rounded-full uppercase whitespace-nowrap">
                {plan.badge}
              </div>
            )}

            {/* Icon */}
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border-2 border-primary bg-primary/10">
              {plan.icon}
            </div>

            <h2 className="text-base font-bold text-white mb-0.5">{plan.name}</h2>
            <p className="text-[10px] text-white/40 mb-3">Subscription plan for your business</p>

            {/* Price */}
            <div className="mb-4">
              <div className="flex items-start justify-center">
                <span className="text-lg font-bold text-primary mt-1">₹</span>
                <span className="text-4xl font-extrabold text-primary leading-none">{plan.price}</span>
              </div>
              <p className="text-[10px] text-white/40 mt-1">/{plan.period}</p>
            </div>

            <div className="w-full h-px bg-primary/20 mb-4" />

            {/* Features */}
            <ul className="w-full text-left space-y-1.5 mb-5">
              {plan.features.map((f) => (
                <li key={f} className="flex gap-2 text-[11px] text-white/70 leading-relaxed">
                  <span className="text-primary font-bold shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>

            {/* CTA */}
            <div className="w-full mt-auto space-y-2">
              <button
                onClick={handleDownloadApp}
                className="w-full rounded-full bg-primary py-3 text-xs font-bold text-black tracking-wide hover:opacity-90 transition flex items-center justify-center gap-2"
              >
                <svg className="h-4 w-4 fill-black" viewBox="0 0 24 24">
                  <path d="M3.18 23.76c.3.17.64.24.99.2l12.5-7.23-2.55-2.55-10.94 9.58zm-1.85-20.1A2 2 0 0 0 1 5v14c0 .7.37 1.32.93 1.67l.1.06 12.5-12.5-.1-.1L1.33 3.66zm20.4 8.57-2.67-1.54-2.88 2.88 2.88 2.88 2.68-1.55A2 2 0 0 0 23 13a2 2 0 0 0-1.27-1.77zM4.17.28L16.67 7.5l-2.55 2.56L1.17.48a1.99 1.99 0 0 1 3-.2z" />
                </svg>
                Get on Google Play
              </button>
              <p className="text-[9px] text-white/25 text-center tracking-wide">
                Download the app to subscribe
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom hint for mobile swipe */}
      <div className="shrink-0 pb-4 flex justify-center gap-2 md:hidden">
        {plans.map((plan, i) => (
          <div key={i} className="h-1 w-6 rounded-full bg-primary/30" />
        ))}
      </div>

      {/* ← ADD HERE */}
      <div className="shrink-0 pb-5 text-center">
        <p className="text-[11px] text-white/55 italic tracking-wide">
           Amount may vary by category
        </p>
      </div>

    </div>
  )
}