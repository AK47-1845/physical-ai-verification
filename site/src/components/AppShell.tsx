'use client';

import { ArrowUpRight, Menu } from 'lucide-react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { DemoVideoButton, PilotButton } from './Actions';
import Sidebar from './Sidebar';
import Chatbot from './Chatbot';

const LINKS = [
  { href: '/', label: 'Home' },
  { href: '/use-cases', label: 'Use Cases' },
  { href: '/compliance', label: 'Compliance' },
  { href: '/evidence', label: 'Evidence' },
  { href: '/methodology', label: 'Methodology' },
  { href: '/playground', label: 'Playground' },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const home = pathname === '/';
  const productLinks = [...LINKS, { href: '/demo', label: 'Demo' }, { href: '/free', label: 'Free Lab' }];
  const title = productLinks.find(link => link.href === pathname)?.label ?? 'Evidence review';
  return <>
    <Sidebar links={LINKS} />
    <div className={`shell-main${home ? '' : ' product-main'}`}>
      {home ? <header className="site-header"><div className="container header-inner">
        
        <nav className="desktop-nav" aria-label="Main navigation">{LINKS.map(link => <a key={link.href} href={link.href}>{link.label}</a>)}</nav>
        <div className="header-cta"><PilotButton /></div>
        <details className="mobile-menu"><summary aria-label="Navigation menu"><Menu size={20} /></summary><nav aria-label="Mobile navigation">{LINKS.map(link => <a key={link.href} href={link.href}>{link.label}</a>)}</nav></details>
      </div></header> : <header className="product-header"><div className="product-breadcrumb"><span>Verification</span><span>/</span><strong>{title}</strong></div><div className="product-header-actions"><Link href="/free" className="product-free-link">Free Lab <ArrowUpRight size={14} /></Link><DemoVideoButton /></div><details className="product-mobile-menu"><summary aria-label="Navigation menu"><Menu size={20} /></summary><nav aria-label="Mobile navigation">{productLinks.map(link => <Link key={link.href} href={link.href}>{link.label}</Link>)}</nav></details></header>}
      {children}
      <footer className="site-footer"><div className="container footer-inner"><span className="mono muted">PHYSICAL INTELLIGENCE. PHYSICAL EVIDENCE.</span><div className="footer-links"><a href="/evidence">Assurance</a><a href="/compliance">Compliance</a><a href="/privacy">Privacy</a><span>2026 Verification</span></div></div></footer>
    </div>
    {process.env.NEXT_PUBLIC_CHATBOT === 'on' ? <Chatbot /> : null}
  </>;
}
