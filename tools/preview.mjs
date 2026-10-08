import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = existsSync(path.join(project, 'portable-preview', 'index.html')) ? path.join(project, 'portable-preview') : path.join(project, 'site', '.next-transfer');
if (!existsSync(path.join(root, 'index.html'))) throw new Error('Ready-to-preview build missing. Use the transfer archive or build with VERIFICATION_STATIC_EXPORT=1.');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.txt': 'text/plain; charset=utf-8', '.woff2': 'font/woff2', '.woff': 'font/woff', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };
const server = http.createServer((request, response) => {
  if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405); response.end(); return; }
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    let destination = path.resolve(root, `.${pathname}`);
    if (destination !== root && !destination.startsWith(root + path.sep)) { response.writeHead(403); response.end(); return; }
    if (existsSync(destination + '.html')) destination += '.html';
    else if (existsSync(destination) && statSync(destination).isDirectory()) destination = path.join(destination, 'index.html');
    if (!existsSync(destination) || !statSync(destination).isFile()) { response.writeHead(404); response.end('Not found'); return; }
    const extension = path.extname(destination);
    const contentType = types[extension] ?? (['icon', 'opengraph-image'].includes(path.basename(destination)) ? 'image/png' : 'application/octet-stream');
    response.writeHead(200, { 'Content-Type': contentType, 'Content-Length': statSync(destination).size, 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-cache' });
    if (request.method === 'HEAD') { response.end(); return; }
    createReadStream(destination).pipe(response);
  } catch { response.writeHead(400); response.end('Invalid request'); }
});
const port = Number(process.env.PORT ?? 5192);
server.on('error', error => { console.error(`Preview could not start: ${error.message}. Choose another port using PORT.`); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Physical AI Verification portable preview: http://127.0.0.1:${port}\nNo packages, network services, or backend required. Keep this terminal open.`));