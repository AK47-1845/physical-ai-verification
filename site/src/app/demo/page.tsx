import type { Metadata } from 'next';
import { DemoRoute } from '@/components/DemoExperience';

export const metadata: Metadata = {
  title: '90-second product demo | Verification',
  description: 'Watch a synthetic trace become a scored, scoped and re-verifiable evidence record. Live engine when available, clearly labeled replay otherwise.',
  openGraph: { title: 'From a robot trace to inspectable evidence', description: 'The 90-second product walkthrough. Synthetic inputs. Actual engine evidence.', images: ['/opengraph-image'] },
};

export default function DemoPage() { return <DemoRoute />; }