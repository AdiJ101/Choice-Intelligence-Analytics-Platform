'use client';

import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

interface MetricCardProps {
  label: string;
  value: number | string;
  delta?: string;
  icon: string;
  iconBg?: string;
  prefix?: string;
  suffix?: string;
  animate?: boolean;
  delay?: number;
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString();
}

export default function MetricCard({
  label, value, delta, icon, iconBg = 'rgba(124,58,237,0.1)',
  prefix = '', suffix = '', animate = true, delay = 0,
}: MetricCardProps) {
  const cardRef   = useRef<HTMLDivElement>(null);
  const valueRef  = useRef<HTMLDivElement>(null);

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    if (!animate || typeof value !== 'number') return;

    const ctx = gsap.context(() => {
      // Card scroll reveal
      gsap.from(cardRef.current, {
        y: 40, opacity: 0, duration: 0.7, ease: 'power3.out',
        delay,
        scrollTrigger: {
          trigger: cardRef.current,
          start: 'top 90%',
          once: true,
        },
      });

      // Number count-up
      const obj = { val: 0 };
      gsap.to(obj, {
        val: value,
        duration: 1.8,
        ease: 'power2.out',
        delay: delay + 0.2,
        scrollTrigger: {
          trigger: cardRef.current,
          start: 'top 90%',
          once: true,
        },
        onUpdate() {
          if (valueRef.current) {
            valueRef.current.textContent = prefix + formatNum(Math.round(obj.val)) + suffix;
          }
        },
      });
    }, cardRef);

    return () => ctx.revert();
  }, [value, animate, delay, prefix, suffix]);

  const isUp   = typeof delta === 'string' && (delta.includes('+') || delta.includes('↑'));
  const isDown = typeof delta === 'string' && delta.includes('-');

  return (
    <div ref={cardRef} className="metric-card">
      <div className="metric-icon" style={{ background: iconBg }}>{icon}</div>
      <div className="metric-label">{label}</div>
      <div ref={valueRef} className="metric-value">
        {typeof value === 'number' ? prefix + '0' + suffix : value}
      </div>
      {delta && (
        <div className={`metric-delta ${isUp ? 'up' : isDown ? 'down' : ''}`}>
          {isUp ? '▲' : isDown ? '▼' : ''} {delta}
        </div>
      )}
    </div>
  );
}
