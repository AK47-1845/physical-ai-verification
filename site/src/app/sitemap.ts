import type { MetadataRoute } from 'next';

export const dynamic = 'force-static';

const ROUTES = [
  '/',
  '/demo',
  '/playground',
  '/free',
  '/evidence',
  '/compliance',
  '/methodology',
  '/use-cases',
  '/release',
  '/share',
  '/privacy',
  '/contribute',
];

export default function sitemap(): MetadataRoute.Sitemap {
  const base =
    process.env.NEXT_PUBLIC_SITE_URL ??
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:5190');
  const stamped = new Date().toISOString().slice(0, 10);
  return ROUTES.map(route => ({
    url: `${base}${route === '/' ? '' : route}`,
    lastModified: stamped,
    changeFrequency: route === '/' ? 'weekly' : 'monthly',
    priority: route === '/' ? 1 : 0.7,
  }));
}
