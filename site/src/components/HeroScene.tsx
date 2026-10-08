'use client';

import dynamic from 'next/dynamic';
import { Box } from 'lucide-react';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { sampleTrace } from '@/lib/demo';

const RobotScene = dynamic(() => import('./RobotScene'), { ssr: false });

function subscribeDesktop(changed: () => void) {
  const query = window.matchMedia('(min-width: 768px)');
  query.addEventListener('change', changed);
  return () => query.removeEventListener('change', changed);
}

export default function HeroScene({ sample, paused }: { sample: number; paused: boolean }) {
  const desktop = useSyncExternalStore(subscribeDesktop, () => window.matchMedia('(min-width: 768px)').matches, () => false);
  const [requested, setThree] = useState(false);
  const three = desktop || requested;
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const element = canvas.current;
    if (!element || three) return;
    const context = element.getContext('2d');
    if (!context) return;
    const width = 600;
    const height = 350;
    element.width = width;
    element.height = height;
    context.clearRect(0, 0, width, height);
    const position = (index: number) => {
      const point = sampleTrace(index).intended;
      return [235 + (point[0] - .5) * 210, 210 + point[2] * 135 - (point[1] - .68) * 80];
    };
    context.beginPath();
    for (let index = 0; index < 120; index++) {
      const [horizontal, vertical] = position(index);
      if (index === 0) context.moveTo(horizontal, vertical); else context.lineTo(horizontal, vertical);
    }
    context.strokeStyle = '#83ece4';
    context.lineWidth = 1.5;
    context.stroke();
    const [horizontal, vertical] = position(sample);
    context.beginPath();
    context.arc(horizontal, vertical, 4, 0, Math.PI * 2);
    context.fillStyle = '#d9fff4';
    context.fill();
    element.parentElement!.dataset.rendered = 'true';
    element.parentElement!.dataset.frame = String(sample);
  }, [sample, three]);
  if (three) return <RobotScene hero paused={paused} sampleIndex={sample} />;
  return <div className="robot-scene lite-scene" data-testid="hero-scene"><img src="/robot-poster.webp" srcSet="/robot-poster-mobile.webp 640w, /robot-poster.webp 1280w" sizes="(max-width: 767px) 100vw, 80vw" className="scene-poster" width="1280" height="782" alt="Robotic arm in its bounded task workspace. Synthetic visualization." fetchPriority="high" /><canvas ref={canvas} aria-label="Animated synthetic end-effector verification trace" role="img" /><button className="scene-upgrade mono" onClick={() => setThree(true)} title="Load the interactive 3D rendering"><Box size={13} />Enable 3D view</button></div>;
}