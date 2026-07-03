'use client';

import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

export default function LoadingScreen({ onComplete }: { onComplete: () => void }) {
  const screenRef = useRef<HTMLDivElement>(null);
  const iconRef   = useRef<HTMLDivElement>(null);
  const titleRef  = useRef<HTMLDivElement>(null);
  const subRef    = useRef<HTMLDivElement>(null);
  const barRef    = useRef<HTMLDivElement>(null);
  const wordsRef  = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        onComplete: () => {
          // Slide out the loading screen
          gsap.to(screenRef.current, {
            yPercent: -100,
            duration: 0.8,
            ease: 'power3.inOut',
            onComplete,
          });
        },
      });

      // Start all elements invisible
      gsap.set([iconRef.current, titleRef.current, subRef.current, wordsRef.current], {
        opacity: 0, y: 20,
      });
      gsap.set(barRef.current, { scaleX: 0, transformOrigin: 'left center' });

      tl
        .to(iconRef.current, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' })
        .to(titleRef.current, { opacity: 1, y: 0, duration: 0.4, ease: 'power3.out' }, '-=0.25')
        .to(subRef.current,   { opacity: 1, y: 0, duration: 0.4, ease: 'power3.out' }, '-=0.2')
        .to(barRef.current,   { scaleX: 1, duration: 1.2, ease: 'power2.inOut' }, '-=0.1')
        .to(wordsRef.current, { opacity: 1, y: 0, duration: 0.3, ease: 'power3.out' }, '-=0.8')
        .to({}, { duration: 0.3 }); // hold
    }, screenRef);

    return () => ctx.revert();
  }, [onComplete]);

  return (
    <div ref={screenRef} className="loading-screen">
      <div className="loading-logo">
        <div ref={iconRef} className="loading-logo-icon">✦</div>
        <div className="loading-logo-text">
          <div ref={titleRef} className="loading-logo-title">Choice Intelligence</div>
          <div ref={subRef} className="loading-logo-sub">Analytics Platform</div>
        </div>
      </div>

      <div className="loading-bar-track">
        <div ref={barRef} className="loading-bar-fill" />
      </div>

      <div ref={wordsRef} className="loading-words" style={{ opacity: 0 }}>
        {['Statistics', 'Insights', 'Analytics'].map(w => (
          <span key={w} className="loading-word">{w}</span>
        ))}
      </div>
    </div>
  );
}
