'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

const navItems = [
  { href: '/statistics',    label: 'Statistics',       icon: '📊' },
  { href: '/content',       label: 'Content Explorer', icon: '🎬' },
  { href: '/analytics',     label: 'AI Analytics',     icon: '✦',  badge: 'AI' },
];

export default function Sidebar() {
  const pathname   = usePathname();
  const sidebarRef = useRef<HTMLElement>(null);
  const linksRef   = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Slide in on mount
      gsap.from(sidebarRef.current, {
        x: -30, opacity: 0, duration: 0.6, ease: 'power3.out',
      });
      // Stagger nav links
      gsap.from(linksRef.current?.querySelectorAll('.nav-link') ?? [], {
        x: -16, opacity: 0, stagger: 0.07, duration: 0.45, ease: 'power3.out', delay: 0.3,
      });
    }, sidebarRef);

    return () => ctx.revert();
  }, []);

  return (
    <aside ref={sidebarRef} className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">✦</div>
        <div className="sidebar-logo-text">
          <strong>Choice Intelligence</strong>
          <span>Analytics Platform</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav" ref={linksRef}>
        <div className="nav-section-label">Navigation</div>
        {navItems.map(item => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
              {item.badge && <span className="nav-badge">{item.badge}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer status */}
      <div className="sidebar-footer">
        <div className="sidebar-status">
          <span className="status-dot" />
          All systems online
        </div>
      </div>
    </aside>
  );
}
