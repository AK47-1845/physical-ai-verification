'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, BookOpen, CirclePlay, FileCheck2, FlaskConical, Home, Layers3, ShieldCheck, Workflow, type LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = { '/': Home, '/use-cases': Workflow, '/compliance': ShieldCheck, '/evidence': FileCheck2, '/methodology': BookOpen, '/playground': Activity, '/demo': CirclePlay, '/free': FlaskConical };

export default function Sidebar({ links }: { links: { href: string; label: string }[] }) {
  const path = usePathname();
  const displayed = [...links, { href: '/demo', label: '90-second Demo' }, { href: '/free', label: 'Free Lab' }];
  return <nav className={`sidebar${path === '/' ? '' : ' product-sidebar'}`} aria-label="Section navigation">
    {path === '/' ? <span className="mono muted side-brand">V / INDEX</span> : <div className="product-brand"><Layers3 size={23} strokeWidth={1.4} /><span>Verification</span></div>}
    {displayed.map(link => { const Icon = ICONS[link.href] ?? FileCheck2; return <Link key={link.href} href={link.href} className={path === link.href ? 'active' : ''} aria-current={path === link.href ? 'page' : undefined}>{path !== '/' && <Icon size={17} strokeWidth={1.5} />}{link.label}</Link>; })}
    {path === '/' ? <span className="mono muted side-foot">V1 / MORE SOON</span> : <div className="product-side-scope"><span className="status-dot" /><span>Independent screening<small>Draft gates. Human decisions.</small></span></div>}
  </nav>;
}
