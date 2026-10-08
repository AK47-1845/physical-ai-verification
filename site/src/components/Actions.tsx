'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { ArrowUpRight, Check, Download, Play, ScanLine, X } from 'lucide-react';
import { memo, useState, type FormEvent } from 'react';
import { downloadJson } from '@/lib/demo';
import dynamic from 'next/dynamic';

const DemoExperience = dynamic(() => import('./DemoExperience'), { ssr: false });

export const PilotButton = memo(function PilotButton({ className = 'button primary', children = 'Request pilot' }: { className?: string; children?: React.ReactNode }) {
  const [saved, setSaved] = useState(false);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    downloadJson('verification-pilot-request.json', { status: 'LOCAL_DRAFT_NOT_SUBMITTED', ...data });
    setSaved(true);
  }
  return <Dialog.Root onOpenChange={() => setSaved(false)}><Dialog.Trigger className={className}>{children}<ArrowUpRight size={16} /></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content"><ScanLine size={26} className="signal" /><Dialog.Title>Start with one real failure.</Dialog.Title><Dialog.Description>Define the robot, policy and evidence you want to validate.</Dialog.Description><Dialog.Close className="icon-button dialog-close" aria-label="Close pilot request"><X /></Dialog.Close><form className="pilot-form" onSubmit={submit}><label>Name<input name="name" autoComplete="name" required maxLength={100} placeholder="Your name" /></label><label>Work email<input name="email" type="email" autoComplete="email" required maxLength={254} placeholder="you@company.com" /></label><label>System<select name="system" defaultValue="manipulator"><option value="manipulator">Robotic manipulation</option><option value="humanoid">Humanoid / locomotion</option><option value="autonomous">Autonomous system</option><option value="assurance">Assessment / insurance</option></select></label><label>Validation challenge<textarea name="challenge" required maxLength={1000} placeholder="What needs to be proven before deployment?" /></label><div className="notice">[REPLACE] Pilot contact is not configured. This creates a local draft; nothing is submitted.</div><button type="submit" className="button primary">{saved ? <Check size={16} /> : <Download size={16} />}{saved ? 'Draft downloaded' : 'Download pilot brief'}</button><span role="status" className="mono muted">{saved ? 'LOCAL DRAFT / NOT SUBMITTED' : 'NO CONTACT DATA LEAVES THIS BROWSER'}</span></form></Dialog.Content></Dialog.Portal></Dialog.Root>;
});

export const DemoVideoButton = memo(function DemoVideoButton() {
  const [open, setOpen] = useState(false);
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger className="button secondary"><Play size={14} />Watch 90-sec demo</Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="demo-overlay" /><Dialog.Content className="demo-dialog"><Dialog.Title className="demo-sr-only">The 90-second evidence walkthrough</Dialog.Title><Dialog.Description className="demo-sr-only">A captioned synthetic demonstration of scoring, failure hunting and evidence verification.</Dialog.Description><DemoExperience onClose={() => setOpen(false)} /></Dialog.Content></Dialog.Portal></Dialog.Root>;
});