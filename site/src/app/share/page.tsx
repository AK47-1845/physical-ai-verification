import type { Metadata } from 'next';
import ShareArtifact from '@/components/ShareArtifact';

export const metadata: Metadata = {
  title: 'Shared evidence | Verification',
  description: 'An explicitly shared trace-screening artifact. Inspect its measurements, scope and draft qualifications.',
  robots: { index: false, follow: false },
  openGraph: { title: 'Inspect the evidence. Then run your own trace.', description: 'Verification Free Lab. Scoped screening, draft thresholds, explicit provenance.', images: ['/opengraph-image'] },
};

export default function SharePage() { return <ShareArtifact />; }