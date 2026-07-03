'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import GradientHeader from '@/components/GradientHeader';
import { api, Post, PostDetail, ScraperStatus } from '@/lib/api';

gsap.registerPlugin(ScrollTrigger);

function StatusDot({ status }: { status: string }) {
  const color = status === 'running' ? '#10b981' : status === 'idle' ? '#f59e0b' : '#94a3b8';
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: color, marginRight: 6,
      boxShadow: `0 0 0 3px ${color}30`,
    }} />
  );
}

export default function ContentExplorerPage() {
  const pageRef     = useRef<HTMLDivElement>(null);
  const tableRef    = useRef<HTMLDivElement>(null);
  const detailRef   = useRef<HTMLDivElement>(null);

  const [categories, setCategories]   = useState<string[]>([]);
  const [posts, setPosts]             = useState<Post[]>([]);
  const [total, setTotal]             = useState(0);
  const [selectedPost, setSelectedPost] = useState<PostDetail | null>(null);
  const [scraperStatus, setScraperStatus] = useState<ScraperStatus | null>(null);
  const [loading, setLoading]         = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  // Filters
  const [search, setSearch]       = useState('');
  const [brand, setBrand]         = useState('');
  const [dateFrom, setDateFrom]   = useState('');
  const [dateTo, setDateTo]       = useState('');
  const [page, setPage]           = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const [showRecentScraped, setShowRecentScraped] = useState(false);
  const LIMIT = 5;

  const getYtThumbnail = (url: string) => {
    if (!url) return '';
    const m = url.match(/(?:v=|youtu\.be\/)([^&]+)/);
    return m ? `https://img.youtube.com/vi/${m[1]}/mqdefault.jpg` : '';
  };

  const fetchPosts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.posts({
        category: brand || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: LIMIT,
        offset: page * LIMIT,
      });
      setPosts(res.data ?? []);
      setTotal(res.total ?? 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [brand, dateFrom, dateTo, page]);

  useEffect(() => {
    api.categories().then(cats => setCategories(cats.map(c => c.category_name)));
    api.scraperStatus().then(setScraperStatus).catch(console.error);
  }, []);

  useEffect(() => { fetchPosts(); }, [fetchPosts]);

  // Filter by search client-side
  const displayPosts = search
    ? posts.filter(p => p.title.toLowerCase().includes(search.toLowerCase()))
    : posts;

  const openDetail = async (postId: number) => {
    setDetailLoading(true);
    try {
      const d = await api.postDetail(postId);
      setSelectedPost(d);
      setShowHistory(false); // reset history toggle
      // Slide in panel
      if (detailRef.current) {
        gsap.from(detailRef.current, {
          y: 30, opacity: 0, duration: 0.5, ease: 'power3.out',
        });
        setTimeout(() => {
          detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    if (detailRef.current) {
      gsap.to(detailRef.current, {
        y: 20, opacity: 0, duration: 0.3, ease: 'power2.in',
        onComplete: () => setSelectedPost(null),
      });
    } else {
      setSelectedPost(null);
    }
  };

  // GSAP table row animations
  useEffect(() => {
    if (!loading && posts.length > 0) {
      gsap.fromTo('.data-table tbody tr', 
        { y: 12, opacity: 0 },
        { y: 0, opacity: 1, stagger: 0.035, duration: 0.45, ease: 'power2.out', delay: 0.05 }
      );
    }
  }, [loading, posts]);

  const scraperControl = async (cmd: string) => {
    try {
      await api.scraperControl(cmd);
      const st = await api.scraperStatus();
      setScraperStatus(st);
    } catch (e) {
      console.error(e);
    }
  };

  const totalPages = Math.ceil(total / LIMIT);

  const formatDate = (ts: string) => ts ? ts.split('T')[0] : '—';
  const engagement = (p: Post) => {
    const views = p.latest_views || 1;
    return (((p.latest_likes + p.latest_comments) / views) * 100).toFixed(1);
  };

  // Derive latest stats from last engagement snapshot (detail endpoint doesn't return latest_* fields)
  const getLatestStats = (post: any) => {
    const hist = post.engagement_history ?? [];
    if (hist.length === 0) return { views: post.latest_views ?? 0, likes: post.latest_likes ?? 0, comments: post.latest_comments ?? 0 };
    const last = hist[hist.length - 1];
    return { views: last.views_count, likes: last.likes_count, comments: last.comments_count };
  };

  return (
    <div ref={pageRef}>
      <GradientHeader
        title="Content Explorer"
        subtitle="Browse, search, and analyse every video across the Choice Group"
        breadcrumb="Choice Intelligence Platform"
      />

      <div className="page-container">

        {/* ── 1. Filter Bar ────────────────────────────────────────────────── */}
        <div style={{
          display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 12,
          background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255,255,255,0.6)', borderRadius: 20,
          padding: '16px 20px', boxShadow: '0 4px 20px rgba(0,0,0,0.05)',
          position: 'relative', zIndex: 10,
        }}>
          <div className="search-bar">
            <span style={{ fontSize: 16, color: '#94a3b8' }}>🔍</span>
            <input
              placeholder="Search videos…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select className="select-input" value={brand} onChange={e => { setBrand(e.target.value); setPage(0); }}>
            <option value="">All Brands</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            type="date" className="select-input" value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(0); }}
            style={{ cursor: 'pointer' }}
          />
          <input
            type="date" className="select-input" value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(0); }}
            style={{ cursor: 'pointer' }}
          />
        </div>

        {/* ── 2. Content Table ─────────────────────────────────────────────── */}
        <div ref={tableRef} className="chart-card" style={{ marginTop: 28, padding: 0, overflow: 'hidden' }}>
          {loading ? (
            <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>
              Loading videos…
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>VIDEO</th>
                  <th>BRAND</th>
                  <th>DATE</th>
                  <th>VIEWS</th>
                  <th>LIKES</th>
                  <th>ENGAGEMENT</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {displayPosts.map(p => (
                  <tr key={p.post_id} onClick={() => openDetail(p.post_id)}>
                    <td style={{ maxWidth: 340 }}>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <img src={getYtThumbnail(p.url)} alt="" style={{ width: 64, height: 36, objectFit: 'cover', borderRadius: 6, background: '#e2e8f0', flexShrink: 0 }} />
                        <div style={{ overflow: 'hidden' }}>
                          <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.title}
                          </div>
                          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
                            {p.platform_display_name}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-purple">
                        {p.category_name.replace('Choice ', '')}
                      </span>
                    </td>
                    <td style={{ color: '#64748b', fontSize: 13 }}>{formatDate(p.publish_timestamp)}</td>
                    <td style={{ fontWeight: 600 }}>{p.latest_views.toLocaleString()}</td>
                    <td style={{ fontWeight: 600 }}>{p.latest_likes.toLocaleString()}</td>
                    <td>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 13, fontWeight: 600,
                        color: parseFloat(engagement(p)) > 5 ? '#059669' : '#64748b',
                      }}>
                        {engagement(p)}%
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={e => { e.stopPropagation(); openDetail(p.post_id); }}
                        data-cursor-hover
                      >
                        View →
                      </button>
                    </td>
                  </tr>
                ))}
                {displayPosts.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                      No videos found matching your filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '16px 20px', borderTop: '1px solid rgba(226,232,240,0.5)',
            }}>
              <span style={{ fontSize: 13, color: '#64748b' }}>
                Showing {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, total)} of {total} videos
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  ← Prev
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── 3. Video Detail Panel ────────────────────────────────────────── */}
        {selectedPost && (
          <div ref={detailRef} className="video-detail-panel" style={{ marginTop: 28 }}>
            <div className="video-detail-header">
              <img src={getYtThumbnail(selectedPost.url)} alt="" style={{ width: 120, height: 68, objectFit: 'cover', borderRadius: 8, background: '#e2e8f0', flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#7c3aed', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                  Video Detail
                </div>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: '#0f172a', lineHeight: 1.3 }}>
                  {selectedPost.title}
                </h2>
                <div style={{ marginTop: 12, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <span className="badge badge-purple">{selectedPost.category_name}</span>
                  <span className="badge badge-blue">{selectedPost.platform_display_name}</span>
                  <span className="badge badge-amber">{formatDate(selectedPost.publish_timestamp)}</span>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                <button className="btn btn-secondary btn-sm" onClick={closeDetail}>✕ Close</button>
                <a href={selectedPost.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm" style={{ padding: '6px 12px', fontSize: 12, borderRadius: 8, textDecoration: 'none' }}>
                  ↗ Watch Video
                </a>
              </div>
            </div>

            {(() => {
              const stats = getLatestStats(selectedPost);
              return (
                <div className="video-detail-stats">
                  <div className="video-stat-block">
                    <div className="video-stat-label">👁 Total Views</div>
                    <div className="video-stat-value" style={{ color: '#7c3aed' }}>
                      {stats.views.toLocaleString()}
                    </div>
                  </div>
                  <div className="video-stat-block">
                    <div className="video-stat-label">❤️ Total Likes</div>
                    <div className="video-stat-value" style={{ color: '#be185d' }}>
                      {stats.likes.toLocaleString()}
                    </div>
                  </div>
                  <div className="video-stat-block">
                    <div className="video-stat-label">💬 Comments</div>
                    <div className="video-stat-value" style={{ color: '#0369a1' }}>
                      {stats.comments.toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Description */}
            {selectedPost.body && (
              <div style={{ padding: '20px 32px', borderBottom: '1px solid rgba(226,232,240,0.5)' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#64748b', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Description
                </div>
                <p style={{ fontSize: 14, color: '#334155', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                  {selectedPost.body.slice(0, 600)}{selectedPost.body.length > 600 ? '…' : ''}
                </p>
              </div>
            )}

            {/* Engagement History */}
            {selectedPost.engagement_history?.length > 0 && (
              <div style={{ padding: '20px 32px', borderBottom: '1px solid rgba(226,232,240,0.5)' }}>
                <div 
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', padding: '4px 0' }}
                  onClick={() => setShowHistory(!showHistory)}
                >
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Engagement History
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: 14 }}>
                    {showHistory ? '▲ Hide' : '▼ Show'}
                  </div>
                </div>
                
                {showHistory && (
                  <div style={{ overflowX: 'auto', marginTop: 16 }}>
                    <table className="data-table" style={{ minWidth: 500 }}>
                      <thead>
                        <tr>
                          <th>SNAPSHOT</th>
                          <th>VIEWS</th>
                          <th>LIKES</th>
                          <th>COMMENTS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedPost.engagement_history.slice(-8).map((h, i) => (
                          <tr key={i}>
                            <td style={{ color: '#64748b' }}>{h.snapshot_timestamp.replace('T', ' ').slice(0, 16)}</td>
                            <td style={{ fontWeight: 600 }}>{h.views_count.toLocaleString()}</td>
                            <td>{h.likes_count.toLocaleString()}</td>
                            <td>{h.comments_count.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Comments */}
            {selectedPost.comments?.length > 0 && (
              <div style={{ padding: '20px 32px' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#64748b', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Comments ({selectedPost.comments.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {selectedPost.comments.slice(0, 5).map((c, i) => (
                    <div key={i} style={{
                      background: '#f8fafc', borderRadius: 12, padding: '12px 16px',
                      border: '1px solid rgba(226,232,240,0.6)',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ fontWeight: 600, fontSize: 13, color: '#7c3aed' }}>{c.author || 'Anonymous'}</span>
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>{formatDate(c.timestamp)}</span>
                      </div>
                      <p style={{ fontSize: 13.5, color: '#334155', lineHeight: 1.5 }}>{c.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {detailLoading && (
          <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 14 }}>
            Loading video details…
          </div>
        )}

        <hr className="section-divider" />

        {/* ── 4. Scraper Status ────────────────────────────────────────────── */}
        <div className="section-header">
          <div>
            <div className="section-title" data-gsap="section-title">Scraper Status</div>
            <div className="section-subtitle">Real-time overview of the data scraper</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => api.scraperStatus().then(setScraperStatus)}>
            ↺ Refresh
          </button>
        </div>

        <div className="scraper-grid">
          <div className="scraper-stat-card">
            <div className="scraper-stat-label">Status</div>
            <div className="scraper-stat-value" style={{ display: 'flex', alignItems: 'center' }}>
              {scraperStatus && <StatusDot status={scraperStatus.status} />}
              {scraperStatus?.status?.replace(/_/g, ' ') ?? 'Loading…'}
            </div>
          </div>
          <div className="scraper-stat-card">
            <div className="scraper-stat-label">Last Scrape</div>
            <div className="scraper-stat-value" style={{ fontSize: 15 }}>
              {scraperStatus?.last_successful_scrape
                ? new Date(scraperStatus.last_successful_scrape).toLocaleString()
                : '—'}
            </div>
          </div>
          <div className="scraper-stat-card">
            <div className="scraper-stat-label">Next Scrape</div>
            <div className="scraper-stat-value" style={{ fontSize: 15 }}>
              {scraperStatus?.next_scheduled_scrape
                ? new Date(scraperStatus.next_scheduled_scrape).toLocaleString()
                : '—'}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={() => scraperControl('start')}>
            ▶ Run Now
          </button>
          <button className="btn btn-secondary" onClick={() => scraperControl('stop')}>
            ⏹ Stop Scraper
          </button>
        </div>

        {scraperStatus?.message && (
          <div style={{ marginTop: 16, padding: '12px 16px', background: '#f1f5f9', borderRadius: 8, fontSize: 14, color: '#475569' }}>
            {scraperStatus.message}
          </div>
        )}

        {/* Recent Scraped Videos Collapsible */}
        {scraperStatus?.recent_videos && scraperStatus.recent_videos.length > 0 && (
          <div style={{ marginTop: 24, padding: '20px', background: 'rgba(255,255,255,0.6)', border: '1px solid rgba(226,232,240,0.8)', borderRadius: 16 }}>
            <div 
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
              onClick={() => setShowRecentScraped(!showRecentScraped)}
            >
              <div style={{ fontSize: 14, fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Recently Scraped Videos ({scraperStatus.scraped_today} scraped today)
              </div>
              <div style={{ color: '#94a3b8', fontSize: 14, fontWeight: 600 }}>
                {showRecentScraped ? '▲ Hide' : '▼ View'}
              </div>
            </div>

            {showRecentScraped && (
              <div style={{ overflowX: 'auto', marginTop: 16 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Brand</th>
                      <th>Platform</th>
                      <th>Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scraperStatus.recent_videos.map((v: any, i: number) => (
                      <tr key={i}>
                        <td style={{ maxWidth: 300 }}>
                          <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {v.title}
                          </div>
                        </td>
                        <td><span className="badge badge-purple">{v.category_name}</span></td>
                        <td>{v.platform_code}</td>
                        <td style={{ color: '#64748b' }}>{formatDate(v.publish_timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
