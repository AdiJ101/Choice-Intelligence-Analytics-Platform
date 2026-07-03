'use client';

import { useState, useEffect } from 'react';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import LoadingScreen from '@/components/LoadingScreen';
import CustomCursor from '@/components/CustomCursor';
import LenisProvider from '@/components/LenisProvider';
import FloatingChat from '@/components/FloatingChat';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);

  // Only show loading on first visit per session
  useEffect(() => {
    if (sessionStorage.getItem('cip_loaded')) {
      setLoading(false);
    }
  }, []);

  const handleLoadComplete = () => {
    setLoading(false);
    sessionStorage.setItem('cip_loaded', '1');
  };

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>Choice Intelligence Platform</title>
        <meta name="description" content="Premium analytics dashboard for Choice Group brands" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
        <style>{`body { cursor: none; }`}</style>
      </head>
      <body>
        {loading && <LoadingScreen onComplete={handleLoadComplete} />}

        <CustomCursor />

        <LenisProvider>
          <div className="app-shell" style={{ visibility: loading ? 'hidden' : 'visible' }}>
            <Sidebar />
            <main className="main-content">
              {children}
            </main>
            <FloatingChat />
          </div>
        </LenisProvider>
      </body>
    </html>
  );
}
