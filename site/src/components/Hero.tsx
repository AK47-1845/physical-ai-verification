'use client';

import { Pause, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { DemoVideoButton, PilotButton } from './Actions';
import { sampleTrace } from '@/lib/demo';
import HeroScene from './HeroScene';

export default function Hero() {
  const [paused, setPaused] = useState(false);
  const [sample, setSample] = useState(0);
  const point = sampleTrace(sample);
  useEffect(() => {
    if (paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = setInterval(() => { if (!document.hidden) setSample(value => (value + 1) % 120); }, 50);
    return () => clearInterval(timer);
  }, [paused]);
  return <section className="hero" aria-labelledby="hero-title"><div className="hero-scene"><HeroScene sample={sample} paused={paused} /></div><div className="container"><div className="hero-content"><h1 id="hero-title"><span className="hero-title-top">Physical AI</span><br /><span>V&amp;V Engine</span></h1><p className="hero-copy hero-description">Test robotic and world-model behavior. Expose the failure boundary. Build an auditable case for deployment.</p><div className="hero-actions"><PilotButton /><DemoVideoButton /></div><div className="hero-note mono">INDEPENDENT ASSURANCE / BEFORE AND AFTER DEPLOYMENT</div></div><div className="scene-corner mono">V / TRACE 0248<br /><span className="signal">SYNTHETIC REPLAY</span></div><div className="scene-annotation mono">END-EFFECTOR PATH<br />x {point.observed[0].toFixed(3)} &nbsp; y {point.observed[1].toFixed(3)} &nbsp; z {point.observed[2].toFixed(3)}<br /><span className="muted">TASK SPACE / METERS</span></div><div className="hero-stats"><div className="hero-stat"><span className="mono">VERIFICATION STREAM</span><strong className="pass">NOMINAL / PASS</strong><button className="icon-button trace-toggle" onClick={() => setPaused(!paused)} aria-label={paused ? 'Play verification trace' : 'Pause verification trace'} title={paused ? 'Play' : 'Pause'}>{paused ? <Play size={12} /> : <Pause size={12} />}</button></div><div className="hero-stat"><span className="mono">TRACKING ERROR</span><strong>{(point.drift * 1000).toFixed(1)}<small>mm</small></strong></div><div className="hero-stat"><span className="mono">EVIDENCE GATES</span><strong>04<small>/ 04 passing</small></strong></div><div className="hero-stat"><span className="mono">RUN TIME</span><strong>{(sample * .05).toFixed(2)}<small>s / demonstration</small></strong></div></div></div></section>;
}