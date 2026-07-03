'use client';

import { useEffect, useRef } from 'react';

export default function CustomCursor() {
  const dotRef  = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dot  = dotRef.current!;
    const ring = ringRef.current!;

    let mouseX = -100, mouseY = -100;
    let ringX  = -100, ringY  = -100;
    let rafId: number;

    const onMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      dot.style.left = `${mouseX}px`;
      dot.style.top  = `${mouseY}px`;
    };

    // Lag ring behind cursor for smooth trail effect
    const tick = () => {
      ringX += (mouseX - ringX) * 0.12;
      ringY += (mouseY - ringY) * 0.12;
      ring.style.left = `${ringX}px`;
      ring.style.top  = `${ringY}px`;
      rafId = requestAnimationFrame(tick);
    };

    const onEnter = () => {
      dot.classList.add('hovered');
      ring.classList.add('hovered');
    };

    const onLeave = () => {
      dot.classList.remove('hovered');
      ring.classList.remove('hovered');
    };

    const onDown = () => {
      dot.classList.add('clicked');
      ring.classList.add('clicked');
    };

    const onUp = () => {
      dot.classList.remove('clicked');
      ring.classList.remove('clicked');
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('mouseup', onUp);

    // All interactive elements trigger hovered state
    const targets = 'a, button, [data-cursor-hover], input, select, .nav-link, .metric-card, .chart-card';
    const interactive = document.querySelectorAll<HTMLElement>(targets);
    interactive.forEach(el => {
      el.addEventListener('mouseenter', onEnter);
      el.addEventListener('mouseleave', onLeave);
    });

    rafId = requestAnimationFrame(tick);

    // Observe DOM changes to attach listeners to new elements
    const observer = new MutationObserver(() => {
      document.querySelectorAll<HTMLElement>(targets).forEach(el => {
        el.addEventListener('mouseenter', onEnter);
        el.addEventListener('mouseleave', onLeave);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('mouseup', onUp);
      cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  return (
    <>
      <div ref={dotRef}  className="cursor-dot"  aria-hidden="true" />
      <div ref={ringRef} className="cursor-ring" aria-hidden="true" />
    </>
  );
}
