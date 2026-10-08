import type { Metadata } from 'next';
import FreeLab from '@/components/FreeLab';

export const metadata: Metadata = {
  title: 'Free Lab | Verification',
  description: 'Screen a robot trace, explore failure modes, run a drift duel and export scoped evidence. Anonymous first run, explicit limits, optional sharing.',
  openGraph: { title: 'Bring a trace. Find the failure.', description: 'Free screening tools for physical-AI builders. Draft gates, transparent limits and exportable evidence.', images: ['/opengraph-image'] },
};

export default function FreePage() { return <FreeLab />; }