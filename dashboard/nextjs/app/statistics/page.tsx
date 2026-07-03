'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from 'recharts';
import GradientHeader from '@/components/GradientHeader';
import { api, Overview, CategoryAnalytics, Post } from '@/lib/api';

gsap.registerPlugin(ScrollTrigger);

const BRAND_COLORS = ['#7c3aed','#60a5fa','#f472b6','#34d399','#fb923c','#a78bfa','#38bdf8'];

// ── Helpers ────────────────────────────────────────────────────────────────────
function getYtThumbnail(url: string): string {
  let id = '';
  const watchMatch = url.match(/[?&]v=([^&]+)/);
  const shortsMatch = url.match(/\/shorts\/([^?/]+)/);
  if (watchMatch) id = watchMatch[1];
  else if (shortsMatch) id = shortsMatch[1];
  return id ? `https://img.youtube.com/vi/${id}/mqdefault.jpg` : '';
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString();
}

// ── Custom Tooltip ─────────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; fill: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'white', border: '1px solid #e2e8f0', borderRadius: 14,
      padding: '12px 16px', boxShadow: '0 10px 30px rgba(0,0,0,0.1)', fontSize: 13,
    }}>
      <p style={{ fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>{label}</p>
      {payload.map((p) => (
        <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: p.fill, flexShrink: 0 }} />
          <span style={{ color: '#64748b' }}>{p.name}:</span>
          <span style={{ fontWeight: 600, color: '#0f172a' }}>{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
};

// ── Brand Comparison Modal ──────────────────────────────────────────────────────
function BrandComparisonModal({ data, onClose }: { data: CategoryAnalytics[]; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(15,23,42,0.55)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }} onClick={onClose}>
      <div style={{
        background: 'white', borderRadius: 24, padding: 32,
        width: '90vw', maxWidth: 1000, maxHeight: '85vh', overflowY: 'auto',
        boxShadow: '0 40px 80px rgba(0,0,0,0.2)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#0f172a' }}>Brand Comparison — Full View</div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>Complete performance breakdown per brand</div>
          </div>
          <button onClick={onClose} style={{
            background: '#f1f5f9', border: 'none', borderRadius: 12, padding: '8px 16px',
            fontSize: 14, fontWeight: 600, cursor: 'pointer', color: '#334155',
          }}>✕ Close</button>
        </div>
        <ResponsiveContainer width="100%" height={420}>
          <BarChart data={data} margin={{ top: 0, right: 20, left: 0, bottom: 40 }}>
            <CartesianGrid vertical={false} stroke="rgba(0,0,0,0.05)" />
            <XAxis
              dataKey="category_name"
              tick={{ fontSize: 13, fill: '#334155', fontWeight: 500 }}
              axisLine={false} tickLine={false}
              angle={-20} textAnchor="end"
            />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }}
              tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}K` : String(v)}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 13, paddingTop: 16 }} iconType="circle" iconSize={9} />
            <Bar dataKey="post_count"     name="Videos"   fill="#a78bfa" radius={[4,4,0,0]} />
            <Bar dataKey="total_views"    name="Views"    fill="#7dd3fc" radius={[4,4,0,0]} />
            <Bar dataKey="total_likes"    name="Likes"    fill="#f472b6" radius={[4,4,0,0]} />
            <Bar dataKey="total_comments" name="Comments" fill="#34d399" radius={[4,4,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── Metric Card (inline, uniform height) ──────────────────────────────────────
function MetricCard({ label, value, delta, icon, iconBg, isString = false, index = 0 }: {
  label: string; value: number | string; delta?: string;
  icon: string; iconBg?: string; isString?: boolean; index?: number;
}) {
  const cardRef  = useRef<HTMLDivElement>(null);
  const numRef   = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!cardRef.current) return;

    // Animate card in
    gsap.fromTo(cardRef.current,
      { y: 40, opacity: 0 },
      {
        y: 0, opacity: 1, duration: 0.7, ease: 'power3.out',
        delay: index * 0.1,
        scrollTrigger: { trigger: cardRef.current, start: 'top 92%', once: true },
      }
    );

    // Count-up for numbers
    if (!isString && typeof value === 'number' && numRef.current) {
      const obj = { val: 0 };
      gsap.to(obj, {
        val: value, duration: 1.8, ease: 'power2.out',
        delay: index * 0.1 + 0.3,
        scrollTrigger: { trigger: cardRef.current, start: 'top 92%', once: true },
        onUpdate() {
          if (numRef.current) numRef.current.textContent = formatNum(Math.round(obj.val));
        },
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const isUp   = typeof delta === 'string' && (delta.includes('+') || delta.includes('↑'));
  const isDown = typeof delta === 'string' && delta.includes('-');

  return (
    <div ref={cardRef} style={{
      background: 'rgba(255,255,255,0.95)',
      border: '1px solid rgba(255,255,255,1)',
      borderRadius: 20, padding: '28px 24px',
      boxShadow: '0 10px 25px -5px rgba(0,0,0,0.06)',
      position: 'relative', overflow: 'hidden', opacity: 0,
      minHeight: 190,
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      transition: 'transform 0.25s ease, box-shadow 0.25s ease',
      cursor: 'default',
    }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-5px)'; (e.currentTarget as HTMLDivElement).style.boxShadow = '0 20px 40px rgba(0,0,0,0.1)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = ''; (e.currentTarget as HTMLDivElement).style.boxShadow = '0 10px 25px -5px rgba(0,0,0,0.06)'; }}
    >
      {/* top accent line on hover */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 3,
        background: 'linear-gradient(90deg, #7c3aed, #8b5cf6, #60a5fa)',
        borderRadius: '20px 20px 0 0',
      }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {label}
        </div>
        <div style={{
          width: 40, height: 40, borderRadius: 12, background: iconBg ?? 'rgba(124,58,237,0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
          flexShrink: 0,
        }}>{icon}</div>
      </div>
      <div>
        <div ref={numRef} style={{ fontSize: 34, fontWeight: 800, color: '#0f172a', letterSpacing: '-0.03em', lineHeight: 1 }}>
          {isString ? value : '0'}
        </div>
        {delta && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 10,
            fontSize: 12, fontWeight: 600, padding: '3px 8px', borderRadius: 999,
            color: isUp ? '#059669' : isDown ? '#dc2626' : '#64748b',
            background: isUp ? '#d1fae5' : isDown ? '#fee2e2' : '#f1f5f9',
          }}>
            {isUp ? '▲' : isDown ? '▼' : ''} {delta}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function StatisticsPage() {
  const pageRef = useRef<HTMLDivElement>(null);

  const [overview, setOverview]         = useState<Overview | null>(null);
  const [categories, setCategories]     = useState<string[]>([]);
  const [catData, setCatData]           = useState<CategoryAnalytics[]>([]);
  const [allPosts, setAllPosts]         = useState<Post[]>([]);   // for top-performing rich view
  const [timeframe, setTimeframe]       = useState<'7' | '30'>('7');
  const [brandFilter, setBrandFilter]   = useState('');
  const [compareBrand, setCompareBrand] = useState('');
  const [topBrand, setTopBrand]         = useState('');
  const [showCompareModal, setShowCompareModal] = useState(false);

  // Fetch all posts sorted by engagement for "Most Viewed" + "Top Performing"
  const fetchPosts = useCallback(async (days: string, brand: string) => {
    const today = new Date();
    const from  = new Date(today);
    from.setDate(today.getDate() - parseInt(days));
    const dateFrom = from.toISOString().split('T')[0];
    const res = await api.posts({
      category: brand || undefined,
      date_from: dateFrom,
      limit: 50,
    });
    // Sort by total_engagement descending
    const sorted = (res.data ?? []).sort((a, b) => b.total_engagement - a.total_engagement);
    setAllPosts(sorted);
  }, []);

  useEffect(() => {
    Promise.all([
      api.overview(),
      api.categories(),
      api.byCategory(),
    ]).then(([ov, cats, catAn]) => {
      setOverview(ov);
      setCategories(cats.map(c => c.category_name));
      setCatData(catAn);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    fetchPosts(timeframe, brandFilter);
  }, [timeframe, brandFilter, fetchPosts]);

  // GSAP: section title wipe + chart card reveals
  useEffect(() => {
    if (!overview) return;
    const ctx = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>('[data-gsap="section-title"]').forEach(el => {
        gsap.fromTo(el,
          { clipPath: 'inset(0 100% 0 0)', opacity: 0 },
          { clipPath: 'inset(0 0% 0 0)', opacity: 1, duration: 0.8, ease: 'power3.out',
            scrollTrigger: { trigger: el, start: 'top 90%', once: true } }
        );
      });

      gsap.utils.toArray<HTMLElement>('.chart-card').forEach((el, i) => {
        gsap.fromTo(el,
          { y: 50, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.7, delay: i * 0.06, ease: 'power3.out',
            scrollTrigger: { trigger: el, start: 'top 92%', once: true } }
        );
      });

      gsap.fromTo('.rank-item',
        { x: -16, opacity: 0 },
        { x: 0, opacity: 1, stagger: 0.05, duration: 0.45, ease: 'power2.out',
          scrollTrigger: { trigger: '.rank-list', start: 'top 88%', once: true } }
      );
    }, pageRef);

    return () => ctx.revert();
  }, [overview, catData]);

  // Derived data
  const topTen = allPosts.slice(0, 10); // already sorted desc

  const topBrandPosts = topBrand
    ? allPosts.filter(p => p.category_name === topBrand)
    : allPosts;

  const compareData = compareBrand
    ? catData.filter(d => d.category_name === compareBrand)
    : catData;

  // For "Most Viewed" horizontal bar — we show desc order (index 0 = top)
  // We reverse for the bar chart so highest appears at the top
  const barChartData = [...topTen].reverse();

  return (
    <div ref={pageRef}>
      <GradientHeader
        title="Statistics"
        subtitle="Executive Summary Across All Choice Group Brands"
        breadcrumb="Choice Intelligence Platform"
      />

      <div className="page-container">

        {/* ── Executive Summary Metric Cards ───────────────────────────────── */}
        <div className="metrics-grid">
          <MetricCard label="Total Videos"   value={overview?.total_posts    ?? 0} icon="🎬" iconBg="rgba(124,58,237,0.1)" index={0} />
          <MetricCard label="Total Comments" value={overview?.total_comments ?? 0} icon="💬" iconBg="rgba(96,165,250,0.1)"  index={1} />
          <MetricCard label="Total Likes"    value={overview?.total_likes    ?? 0} icon="❤️" iconBg="rgba(244,114,182,0.1)" index={2} />
          <MetricCard label="Total Views"    value={overview?.total_views    ?? 0} icon="👁" iconBg="rgba(52,211,153,0.1)"  index={3} />
          <MetricCard label="Avg Watch Time" value="04:18" icon="⏱" iconBg="rgba(251,146,60,0.1)" isString index={4} />
        </div>

        <hr className="section-divider" />

        {/* ── Most Viewed Videos ───────────────────────────────────────────── */}
        <div className="section-header">
          <div>
            <div className="section-title" data-gsap="section-title">Most Viewed Videos</div>
            <div className="section-subtitle">Top content by total engagement — highest at top</div>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div className="toggle-group">
              {(['7','30'] as const).map(d => (
                <button key={d} className={`toggle-pill ${timeframe === d ? 'active' : ''}`} onClick={() => setTimeframe(d)}>
                  {d === '7' ? 'Last 7 Days' : 'Last 30 Days'}
                </button>
              ))}
            </div>
            <select className="select-input" value={brandFilter} onChange={e => setBrandFilter(e.target.value)}>
              <option value="">All Brands</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>

        <div className="chart-card">
          {topTen.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 14 }}>
              No videos found for this period.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={topTen.length * 48 + 40}>
              <BarChart
                data={barChartData}
                layout="vertical"
                margin={{ left: 24, right: 80, top: 8, bottom: 8 }}
              >
                <CartesianGrid horizontal={false} stroke="rgba(0,0,0,0.04)" />
                <XAxis type="number" axisLine={false} tickLine={false}
                  tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}K` : String(v)}
                  tick={{ fontSize: 12, fill: '#94a3b8' }}
                />
                <YAxis
                  type="category" dataKey="title" width={270}
                  tick={{ fontSize: 12, fill: '#334155', fontWeight: 500 }}
                  tickFormatter={v => v.length > 40 ? v.slice(0, 40) + '…' : v}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="total_engagement" name="Engagement" radius={[0, 8, 8, 0]}>
                  {barChartData.map((_, i) => {
                    // Top bar gets darkest, bottom gets lightest
                    const rev = barChartData.length - 1 - i;
                    const fill = rev === 0 ? '#7c3aed' : rev === 1 ? '#8b5cf6' : '#a78bfa';
                    return <Cell key={i} fill={fill} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <hr className="section-divider" />

        {/* ── Brand Comparison + Top Performing ───────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr', gap: 24 }}>

          {/* Brand Comparison — scrollable + clickable */}
          <div className="chart-card" style={{ cursor: 'pointer' }} onClick={() => setShowCompareModal(true)} title="Click to expand">
            <div className="chart-card-header">
              <div>
                <div className="chart-card-title">Brand Comparison</div>
                <div className="chart-card-subtitle">Click to expand · Scroll to see all brands</div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{
                  fontSize: 11, fontWeight: 600, color: '#7c3aed',
                  background: '#f3e8ff', padding: '4px 10px', borderRadius: 999,
                }}>⛶ Expand</span>
                <select
                  className="select-input"
                  value={compareBrand}
                  onClick={e => e.stopPropagation()}
                  onChange={e => setCompareBrand(e.target.value)}
                >
                  <option value="">All Brands</option>
                  {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>

            {/* Vertically scrollable chart wrapper */}
            <div style={{ overflowY: 'auto', maxHeight: 450, cursor: 'default', paddingRight: 8 }} onClick={e => e.stopPropagation()}>
              <ResponsiveContainer width="100%" height={Math.max(350, compareData.length * 50 + 60)}>
                <BarChart data={compareData} layout="vertical" margin={{ top: 0, right: 10, left: 10, bottom: 0 }}>
                  <CartesianGrid horizontal={true} vertical={false} stroke="rgba(0,0,0,0.05)" />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}K` : String(v)} />
                  <YAxis type="category" dataKey="category_name" tickFormatter={v => v.replace('Choice ', '')} tick={{ fontSize: 11, fill: '#334155', fontWeight: 500 }} axisLine={false} tickLine={false} width={85} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 12, paddingBottom: 10 }} iconType="circle" iconSize={8} />
                  <Bar dataKey="post_count"     name="Videos"   fill="#a78bfa" radius={[0,4,4,0]} />
                  <Bar dataKey="total_views"    name="Views"    fill="#7dd3fc" radius={[0,4,4,0]} />
                  <Bar dataKey="total_likes"    name="Likes"    fill="#f472b6" radius={[0,4,4,0]} />
                  <Bar dataKey="total_comments" name="Comments" fill="#34d399" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Top Performing Content — with thumbnail + individual stats */}
          <div className="chart-card" style={{ overflow: 'hidden' }}>
            <div className="chart-card-header">
              <div>
                <div className="chart-card-title">Top Performing Content</div>
                <div className="chart-card-subtitle">Ranked by total engagement</div>
              </div>
              <select className="select-input" value={topBrand} onChange={e => setTopBrand(e.target.value)}>
                <option value="">All Brands</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div className="rank-list" style={{ gap: 0, maxHeight: 450, overflowY: 'auto', paddingRight: 8 }}>
              {topBrandPosts.slice(0, 10).map((p, i) => {
                const thumb = getYtThumbnail(p.url);
                return (
                  <div key={p.post_id} className="rank-item" style={{
                    padding: '12px 0', gap: 12, alignItems: 'flex-start',
                    borderBottom: i < 9 ? '1px solid rgba(226,232,240,0.6)' : 'none',
                  }}>
                    <div style={{
                      fontSize: 13, fontWeight: 800, color: '#7c3aed',
                      width: 22, textAlign: 'center', flexShrink: 0, paddingTop: 2,
                    }}>#{i + 1}</div>

                    {/* Thumbnail */}
                    {thumb ? (
                      <img
                        src={thumb}
                        alt=""
                        style={{ width: 72, height: 48, borderRadius: 8, objectFit: 'cover', flexShrink: 0 }}
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    ) : (
                      <div style={{ width: 72, height: 48, borderRadius: 8, background: '#f1f5f9', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
                        🎬
                      </div>
                    )}

                    <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', lineHeight: 1.4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                          {p.title}
                        </div>
                        <div style={{ fontSize: 11.5, color: '#94a3b8', marginTop: 4 }}>{p.category_name}</div>
                        {/* Stats row */}
                        <div style={{ display: 'flex', gap: 10, marginTop: 6, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 11.5, color: '#7c3aed', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
                            👁 {formatNum(p.latest_views)}
                          </span>
                          <span style={{ fontSize: 11.5, color: '#be185d', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
                            ❤️ {formatNum(p.latest_likes)}
                          </span>
                          <span style={{ fontSize: 11.5, color: '#0369a1', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
                            💬 {formatNum(p.latest_comments)}
                          </span>
                        </div>
                      </div>
                      
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm" style={{ padding: '6px 12px', fontSize: 11, borderRadius: 6, textDecoration: 'none', flexShrink: 0, whiteSpace: 'nowrap' }}>
                        ↗ Watch
                      </a>
                    </div>
                  </div>
                );
              })}
              {topBrandPosts.length === 0 && (
                <div style={{ color: '#94a3b8', fontSize: 14, padding: '20px 0', textAlign: 'center' }}>
                  No content found for this filter.
                </div>
              )}
            </div>
          </div>
        </div>

      </div>

      {/* ── Brand Comparison Modal ───────────────────────────────────────── */}
      {showCompareModal && (
        <BrandComparisonModal data={catData} onClose={() => setShowCompareModal(false)} />
      )}
    </div>
  );
}
