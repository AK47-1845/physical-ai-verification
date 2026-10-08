import { ImageResponse } from 'next/og';

export const dynamic = 'force-static';
export const alt = 'Verification. Physical intelligence needs physical evidence.';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(<div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', background: '#0c0f10', color: '#f2f5f3', padding: 66 }}><div style={{ display: 'flex', alignItems: 'center', fontSize: 32, color: '#83ece4' }}>verification</div><div style={{ display: 'flex', flexDirection: 'column', marginTop: 86, fontSize: 78, lineHeight: 1.06 }}><span>Physical intelligence.</span><span style={{ color: '#a3afae' }}>Physical evidence.</span></div><div style={{ display: 'flex', borderTop: '1px solid #35403c', marginTop: 'auto', paddingTop: 28, justifyContent: 'space-between', fontSize: 18 }}><span>VERIFICATION FOR PHYSICAL AI</span><span style={{ color: '#83ece4' }}>TEST / VERIFY / GOVERN</span></div></div>, size);
}