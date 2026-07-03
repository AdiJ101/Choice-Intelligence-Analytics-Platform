'use client';

import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import GradientHeader from '@/components/GradientHeader';
import { api } from '@/lib/api';

gsap.registerPlugin(ScrollTrigger);

// ── Types matching the actual API response ────────────────────────────────────
interface AIResult {
  demands: string[];
  likes: string[];
  dislikes: string[];
  trends: string[];
  launches: string[];
  announcements: string[];
  focus_areas: string[];
  campaigns: string[];
  analyzed_comments: number;
  analyzed_posts: number;
  generated_at: string;
  error: string | null;
}

interface AIAnalyticsResponse {
  metadata: {
    category: string;
    date_from: string;
    date_to: string;
    started_at: string;
  };
  result: AIResult;
}

// ── Pill tag ──────────────────────────────────────────────────────────────────
function Tag({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      display: 'inline-block', padding: '5px 14px', borderRadius: 999,
      fontSize: 13, fontWeight: 500, color: color,
      background: `${color}18`, border: `1px solid ${color}35`,
      margin: '4px',
    }}>{text}</span>
  );
}

// ── Insight section card ──────────────────────────────────────────────────────
function InsightCard({
  title, items, icon, color, emptyMsg,
}: {
  title: string; items: string[]; icon: string;
  color: string; emptyMsg?: string;
}) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!cardRef.current) return;
    gsap.fromTo(cardRef.current,
      { y: 40, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.65, ease: 'power3.out',
        scrollTrigger: { trigger: cardRef.current, start: 'top 90%', once: true } }
    );
  }, []);

  return (
    <div ref={cardRef} style={{
      background: 'rgba(255,255,255,0.95)',
      border: '1px solid rgba(255,255,255,1)',
      borderRadius: 20,
      boxShadow: '0 10px 25px -5px rgba(0,0,0,0.06)',
      overflow: 'hidden',
      opacity: 0,
    }}>
      <div style={{
        padding: '18px 24px 16px',
        borderBottom: '1px solid rgba(226,232,240,0.5)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{
          width: 38, height: 38, borderRadius: 12, fontSize: 18,
          background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{icon}</div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>{title}</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 1 }}>{items.length} insight{items.length !== 1 ? 's' : ''}</div>
        </div>
      </div>
      <div style={{ padding: '16px 20px' }}>
        {items.length === 0 ? (
          <div style={{ fontSize: 13, color: '#94a3b8', fontStyle: 'italic' }}>{emptyMsg ?? 'No data found.'}</div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            {items.map((item, i) => <Tag key={i} text={item} color={color} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Stat bubble ───────────────────────────────────────────────────────────────
function StatBubble({ value, label, color }: { value: number; label: string; color: string }) {
  const numRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!numRef.current) return;
    const obj = { val: 0 };
    gsap.to(obj, {
      val: value, duration: 1.6, ease: 'power2.out', delay: 0.3,
      scrollTrigger: { trigger: numRef.current, start: 'top 92%', once: true },
      onUpdate() { if (numRef.current) numRef.current.textContent = Math.round(obj.val).toString(); },
    });
  }, [value]);

  return (
    <div style={{
      textAlign: 'center', background: 'rgba(255,255,255,0.95)',
      border: '1px solid rgba(255,255,255,1)', borderRadius: 20, padding: '28px 24px',
      boxShadow: '0 10px 25px -5px rgba(0,0,0,0.06)',
    }}>
      <div ref={numRef} style={{ fontSize: 48, fontWeight: 800, color, lineHeight: 1, letterSpacing: '-0.04em' }}>0</div>
      <div style={{ fontSize: 13, color: '#64748b', marginTop: 8, fontWeight: 500 }}>{label}</div>
    </div>
  );
}



// ── Main Page ──────────────────────────────────────────────────────────────────
export default function AIAnalyticsPage() {
  const pageRef = useRef<HTMLDivElement>(null);
  const [data, setData]       = useState<AIAnalyticsResponse | null>(null);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg]   = useState('');
  
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedBrand, setSelectedBrand] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const pollJob = async (jobId: string, tries = 0): Promise<void> => {
    if (tries > 60) { setRunMsg('Timed out — please refresh the page.'); setRunning(false); return; }
    try {
      const status = await api.getAIJobStatus(jobId);
      if (status.status === 'completed' || status.status === 'done') {
        const fresh = await api.getLastAIAnalytics();
        setData(fresh as unknown as AIAnalyticsResponse);
        setRunMsg('✅ Analysis complete!');
        setRunning(false);
      } else if (status.status === 'failed') {
        setRunMsg('❌ Analysis failed. Please try again.');
        setRunning(false);
      } else {
        setRunMsg(`Running… (${status.progress ?? 0}%)`);
        setTimeout(() => pollJob(jobId, tries + 1), 3000);
      }
    } catch {
      setRunMsg('❌ Error checking job status.');
      setRunning(false);
    }
  };

  useEffect(() => {
    api.categories().then(cats => setCategories(cats.map(c => c.category_name))).catch(console.error);
    api.getLastAIAnalytics()
      .then(d => setData(d as unknown as AIAnalyticsResponse))
      .catch(() => setError('No AI analysis found. Click "Run Analysis" to generate one.'))
      .finally(() => setLoading(false));

    // Check if an analysis is already running
    api.getActiveAIJob().then(job => {
      if (job && job.job_id && (job.status === 'generating' || job.status === 'running')) {
        setRunning(true);
        setRunMsg('An analysis is currently in progress...');
        pollJob(job.job_id);
      }
    }).catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runAnalysis = async () => {
    setRunning(true);
    setRunMsg('Starting analysis job…');
    
    // Apply default date behaviors if not provided
    const computedDateFrom = dateFrom || '2020-01-01'; // from beginning
    const computedDateTo = dateTo || new Date().toISOString().split('T')[0]; // up to today

    try {
      const job = await api.startAIJob({
        category: selectedBrand || undefined,
        date_from: computedDateFrom,
        date_to: computedDateTo,
      });
      setRunMsg(`Job started (ID: ${job.job_id}). This may take 1–2 minutes.`);
      pollJob(job.job_id);
    } catch {
      setRunMsg('❌ Could not start analysis. Check the AI service is running.');
      setRunning(false);
    }
  };

  const clearAnalysis = async () => {
    try {
      await api.clearAIAnalytics();
      setData(null);
      setError('No AI analysis found. Click "Run Analysis" to generate one.');
    } catch (err) {
      console.error('Failed to clear analysis:', err);
    }
  };

  const result = data?.result;

  return (
    <div ref={pageRef}>
      <GradientHeader
        title="AI Analytics"
        subtitle="Deep audience and content intelligence powered by AI"
        breadcrumb="Choice Intelligence Platform"
      />

      <div className="page-container">

        {/* ── Top Bar: meta + run button ───────────────────────────────────── */}
        <div style={{
          background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255,255,255,0.6)', borderRadius: 20,
          padding: '20px 24px', boxShadow: '0 4px 20px rgba(0,0,0,0.05)',
        }}>
          {/* Filters for new analysis */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="select-input" value={selectedBrand} onChange={e => setSelectedBrand(e.target.value)}>
                <option value="">All Brands</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <input type="date" className="select-input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
              <input type="date" className="select-input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
            
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              {runMsg && (
                <span style={{ fontSize: 13, color: running ? '#7c3aed' : '#059669', fontWeight: 500 }}>{runMsg}</span>
              )}
              {data?.metadata && !running && (
                <button
                  onClick={clearAnalysis}
                  style={{
                    padding: '10px 22px', borderRadius: 14, border: '1px solid #e2e8f0', cursor: 'pointer',
                    background: 'white', color: '#64748b', fontWeight: 600, fontSize: 14,
                    transition: 'all 0.2s',
                  }}
                >
                  Clear Analysis
                </button>
              )}
              <button
                onClick={runAnalysis}
                disabled={running}
                style={{
                  padding: '10px 22px', borderRadius: 14, border: 'none', cursor: 'pointer',
                  background: running ? '#e2e8f0' : 'linear-gradient(135deg, #7c3aed, #8b5cf6)',
                  color: running ? '#94a3b8' : 'white', fontWeight: 700, fontSize: 14,
                  transition: 'all 0.2s',
                }}
              >
                {running ? '⏳ Running…' : '🚀 Run New Analysis'}
              </button>
            </div>
          </div>

          {/* Current analysis metadata */}
          <div style={{ width: '100%', marginTop: 20, paddingTop: 16, borderTop: '1px dashed rgba(226,232,240,0.8)' }}>
            {data?.metadata ? (
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Viewing Analysis For</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', marginTop: 2 }}>{data.metadata.category}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Period</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', marginTop: 2 }}>{data.metadata.date_from} → {data.metadata.date_to}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Generated</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', marginTop: 2 }}>
                    {(() => {
                      const utcStr = result?.generated_at;
                      if (!utcStr) return '—';
                      try {
                        const isoStr = utcStr.replace(' UTC', 'Z').replace(' ', 'T');
                        return new Date(isoStr).toLocaleString();
                      } catch {
                        return utcStr;
                      }
                    })()}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 14, color: '#94a3b8' }}>{loading ? 'Loading last analysis…' : error}</div>
            )}
          </div>
        </div>

        {result && (
          <>
            {/* ── Coverage Stats ───────────────────────────────────────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 28 }}>
              <StatBubble value={result.analyzed_posts}    label="Videos Analysed" color="#7c3aed" />
              <StatBubble value={result.analyzed_comments} label="Comments Analysed" color="#0369a1" />
            </div>

            <hr className="section-divider" />

            {/* ── Audience Intelligence ─────────────────────────────────────── */}
            <div className="section-header">
              <div>
                <div className="section-title" data-gsap="section-title">Audience Intelligence</div>
                <div className="section-subtitle">What your viewers love, dislike, and want to see</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
              <InsightCard title="What They Love"    items={result.likes}    icon="❤️" color="#be185d" emptyMsg="No likes data yet." />
              <InsightCard title="What They Dislike" items={result.dislikes} icon="👎" color="#dc2626" emptyMsg="No dislikes data yet." />
              <InsightCard title="What They Want"    items={result.demands}  icon="💡" color="#7c3aed" emptyMsg="No demand data yet." />
            </div>

            <hr className="section-divider" />

            {/* ── Content Intelligence ──────────────────────────────────────── */}
            <div className="section-header">
              <div>
                <div className="section-title" data-gsap="section-title">Content Intelligence</div>
                <div className="section-subtitle">Trending topics, campaigns, launches and company focus areas</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <InsightCard title="Trending Topics"  items={result.trends}       icon="📈" color="#059669" emptyMsg="No trend data." />
              <InsightCard title="Focus Areas"      items={result.focus_areas}  icon="🎯" color="#0369a1" emptyMsg="No focus areas." />
              <InsightCard title="Active Campaigns" items={result.campaigns}    icon="📣" color="#f59e0b" emptyMsg="No campaigns." />
              <InsightCard title="Product Launches" items={result.launches}     icon="🚀" color="#7c3aed" emptyMsg="No launches." />
            </div>

            {result.announcements?.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <InsightCard title="Announcements" items={result.announcements} icon="📢" color="#64748b" />
              </div>
            )}


          </>
        )}

        {/* No data state */}
        {!loading && !result && (
          <div style={{
            marginTop: 48, textAlign: 'center', padding: '60px 24px',
            background: 'rgba(255,255,255,0.7)', borderRadius: 24,
            border: '2px dashed rgba(124,58,237,0.2)',
          }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>No Analysis Yet</div>
            <div style={{ fontSize: 14, color: '#64748b', marginBottom: 24 }}>
              Click "Run New Analysis" above to start an AI analysis of your content.
            </div>

            {/* Removed inline Ask AI */}
          </div>
        )}

        <div style={{ height: 60 }} />
      </div>

      <style>{`
        .thinking-dots { animation: blink 1.2s step-start infinite; }
        @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>
    </div>
  );
}
