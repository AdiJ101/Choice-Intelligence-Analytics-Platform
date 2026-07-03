'use client';

import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

interface GradientHeaderProps {
  title: string;
  subtitle?: string;
  breadcrumb?: string;
}

export default function GradientHeader({ title, subtitle, breadcrumb }: GradientHeaderProps) {
  const headerRef  = useRef<HTMLDivElement>(null);
  const titleRef   = useRef<HTMLHeadingElement>(null);
  const subRef     = useRef<HTMLParagraphElement>(null);
  const orbRef1    = useRef<HTMLDivElement>(null);
  const orbRef2    = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(headerRef.current, {
        y: -20, opacity: 0, duration: 0.6, ease: 'power3.out',
      });
      gsap.from(titleRef.current, {
        y: 16, opacity: 0, duration: 0.55, ease: 'power3.out', delay: 0.1,
      });
      gsap.from(subRef.current, {
        y: 12, opacity: 0, duration: 0.45, ease: 'power3.out', delay: 0.2,
      });

      // Slow ambient float for the orbs
      gsap.to(orbRef1.current, {
        y: '-=15', x: '+=10', duration: 4, repeat: -1, yoyo: true,
        ease: 'sine.inOut',
      });
      gsap.to(orbRef2.current, {
        y: '+=12', x: '-=8', duration: 5, repeat: -1, yoyo: true,
        ease: 'sine.inOut', delay: 1.5,
      });
    }, headerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={headerRef} className="gradient-header">
      <div ref={orbRef1} style={{
        position: 'absolute', top: '-50%', right: '-5%',
        width: 500, height: 500,
        background: 'radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />
      <div ref={orbRef2} style={{
        position: 'absolute', bottom: '-30%', left: '25%',
        width: 300, height: 300,
        background: 'radial-gradient(circle, rgba(255,255,255,0.2) 0%, transparent 70%)',
        borderRadius: '50%', pointerEvents: 'none',
      }} />

      <div className="gradient-header-content">
        {breadcrumb && (
          <div style={{
            fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.7)',
            textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12,
          }}>
            {breadcrumb}
          </div>
        )}
        <h1 ref={titleRef}>{title}</h1>
        {subtitle && <p ref={subRef}>{subtitle}</p>}
      </div>
    </div>
  );
}
