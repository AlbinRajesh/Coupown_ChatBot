import Header from './Header'

const userFeatures = [
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
      </svg>
    ),
    title: 'Hyperlocal Discovery',
    desc: 'Find shops, services, restaurants, and businesses right around your neighbourhood — not just the city.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z" />
      </svg>
    ),
    title: 'Natural Language Chat',
    desc: "Just type the way you speak. \"Good biryani near me open now\" works exactly as you'd expect.",
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M12 1l2.753 8.472H23l-7.122 5.17 2.753 8.471L12 18.012l-6.631 5.101 2.753-8.471L2 9.472h8.247z" />
      </svg>
    ),
    title: 'Live Offers & Deals',
    desc: 'Browse real-time discounts and exclusive offers posted by local businesses — updated as they happen.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6V11c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
      </svg>
    ),
    title: 'Instant Notifications',
    desc: 'Get push alerts the moment a deal, offer, or service you care about goes live near you.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 3c1.93 0 3.5 1.57 3.5 3.5S13.93 13 12 13s-3.5-1.57-3.5-3.5S10.07 6 12 6zm7 13H5v-.23c0-.62.28-1.2.76-1.58C7.47 15.82 9.64 15 12 15s4.53.82 6.24 2.19c.48.38.76.97.76 1.58V19z" />
      </svg>
    ),
    title: 'Saved History & Chats',
    desc: 'All your past searches and conversations are saved so you can pick up right where you left off.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm4.24 16L12 15.45 7.77 18l1.12-4.81-3.73-3.23 4.92-.42L12 5l1.92 4.53 4.92.42-3.73 3.23L16.23 18z" />
      </svg>
    ),
    title: 'Personalised Results',
    desc: 'CORA learns your preferences over time and surfaces results that match your taste, not just proximity.',
  },
]

const businessFeatures = [
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M20 4H4v2l8 5 8-5V4zm0 4.236l-8 5-8-5V20h16V8.236z" />
      </svg>
    ),
    title: 'List Your Business',
    desc: 'Get discovered by thousands of nearby customers searching for exactly what you offer — in minutes.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z" />
      </svg>
    ),
    title: 'Post Unlimited Offers',
    desc: 'Push deals, flash sales, and seasonal promotions to your customer base with zero listing limits.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
      </svg>
    ),
    title: 'Reach Unlimited Customers',
    desc: 'Your business page is visible to every user searching in your area — no cap on followers or reach.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M4 4h16v2H4zm2 3h12l-1 9H7L6 7zm5 2v2H9v2h2v2h2v-2h2v-2h-2V9h-2z" />
      </svg>
    ),
    title: 'Multi-Branch Management',
    desc: 'Manage all your outlets from a single dashboard. Basic supports 3 branches; Standard supports 7.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z" />
      </svg>
    ),
    title: '2 GB Cloud Storage',
    desc: 'Store menus, catalogues, images, and documents in the cloud — with upgrade options as your business grows.',
  },
  {
    icon: (
      <svg className="h-6 w-6 fill-primary" viewBox="0 0 24 24">
        <path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" />
      </svg>
    ),
    title: 'Brand Visibility on CORA AI',
    desc: 'Standard plan businesses get showcased prominently across the CORA AI platform for maximum exposure.',
  },
]

function FeatureCard({ icon, title, desc }) {
  return (
    <div className="flex gap-4 rounded-xl border border-primary/20 bg-[#0d0d0d] p-5 hover:border-primary/50 transition-colors duration-200">
      <div className="shrink-0 flex h-11 w-11 items-center justify-center rounded-full border border-primary/40 bg-primary/10">
        {icon}
      </div>
      <div>
        <h3 className="text-sm font-bold text-white mb-1">{title}</h3>
        <p className="text-xs text-white/50 leading-relaxed">{desc}</p>
      </div>
    </div>
  )
}

export default function FeaturePage({ onNavigate, savedChats, onNewChat, onLoadChat, onDeleteChat }) {
  return (
    <div className="fixed inset-0 bg-black text-white flex flex-col overflow-hidden">

      <Header
        savedChats={savedChats}
        onNewChat={onNewChat}
        onLoadChat={onLoadChat}
        onDeleteChat={onDeleteChat}
        onNavigate={onNavigate}
      />

      {/* Spacer matching header height */}
      <div className="shrink-0 h-20 md:h-24" />

      {/* Page title */}
      <div className="shrink-0 text-center pt-4 pb-4 px-4">
        <h1 className="text-3xl font-bold tracking-wide text-primary mb-2">
          Everything CORA Offers
        </h1>
        <p className="text-xs text-white/30 tracking-widest uppercase">
          Built for users · Designed for businesses
        </p>
      </div>

      {/* Scrollable content — stays below header */}
      <div className="flex-1 min-h-0 overflow-y-auto hide-scrollbar px-4 md:px-10 pb-10 max-w-5xl mx-auto w-full">

        {/* For Users */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-5">
            <div className="h-px flex-1 bg-primary/20" />
            <span className="text-[10px] font-extrabold tracking-widest uppercase text-primary px-3 py-1 rounded-full border border-primary/40">
              For Users
            </span>
            <div className="h-px flex-1 bg-primary/20" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {userFeatures.map((f) => (
              <FeatureCard key={f.title} {...f} />
            ))}
          </div>
        </div>

        {/* For Businesses */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-5">
            <div className="h-px flex-1 bg-primary/20" />
            <span className="text-[10px] font-extrabold tracking-widest uppercase text-primary px-3 py-1 rounded-full border border-primary/40">
              For Businesses
            </span>
            <div className="h-px flex-1 bg-primary/20" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {businessFeatures.map((f) => (
              <FeatureCard key={f.title} {...f} />
            ))}
          </div>
        </div>

        {/* CTA strip */}
        <div className="rounded-2xl border border-primary/40 bg-[#0f0a00] p-8 text-center">
          <h2 className="text-xl font-bold text-white mb-2">Ready to get started?</h2>
          <p className="text-xs text-white/40 mb-6">
            Join thousands of users and businesses already on CORA.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={() => onNavigate('pricing')}
              className="rounded-full bg-primary px-8 py-3 text-sm font-bold text-black tracking-wide hover:opacity-90 transition"
            >
              View Pricing
            </button>
            <button
              onClick={() => onNavigate('home')}
              className="rounded-full border border-primary/50 px-8 py-3 text-sm font-bold text-primary tracking-wide hover:bg-primary/10 transition"
            >
              Try CORA Free
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}