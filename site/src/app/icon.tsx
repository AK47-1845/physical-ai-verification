import { ImageResponse } from 'next/og';

export const dynamic = 'force-static';
export const size = { width: 64, height: 64 };
export const contentType = 'image/png';
export default function Icon() {
  return new ImageResponse(<div style={{ display: 'flex', background: '#0c0f10', color: '#83ece4', width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center', fontSize: 46, fontWeight: 600 }}>v</div>, size);
}