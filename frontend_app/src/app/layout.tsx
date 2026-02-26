'use client';
import './globals.css';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const pathname = usePathname();

    return (
        <html lang="en" suppressHydrationWarning>
            <body suppressHydrationWarning>
                <div className="app-layout">
                    <aside className="sidebar">
                        <div className="sidebar-title">
                            <span style={{ fontSize: '24px', marginRight: '8px' }}>🎬</span>
                            AI Director
                        </div>

                        <nav className="nav-links">
                            <Link href="/" className={`nav-link ${pathname === '/' ? 'active' : ''}`}>
                                <span style={{ fontSize: '18px', marginRight: '8px' }}>⚙️</span>
                                Settings
                            </Link>
                            <Link href="/studio" className={`nav-link ${pathname === '/studio' ? 'active' : ''}`}>
                                <span style={{ fontSize: '18px', marginRight: '8px' }}>✨</span>
                                Studio
                            </Link>
                        </nav>
                    </aside>

                    <main className="page-content">
                        {children}
                    </main>
                </div>
            </body>
        </html>
    );
}
