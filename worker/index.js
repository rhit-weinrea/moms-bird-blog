export default {
  // Simple proxy worker: forwards all requests to an origin server.
  // Configure ORIGIN_URL in wrangler (or dashboard) to point at your Flask app.
  async fetch(request, env) {
    const origin = env.ORIGIN_URL || 'https://example.com';
    const url = new URL(request.url);
    // Rebuild target URL using origin + path + query
    const target = origin.replace(/\/$/, '') + url.pathname + url.search;

    // Build fetch init, forwarding most headers and the body
    const init = {
      method: request.method,
      headers: new Headers(request.headers),
      redirect: 'manual',
    };

    // Only include a body for non-GET/HEAD requests
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      init.body = await request.arrayBuffer();
    }

    try {
      const resp = await fetch(target, init);

      // Copy response headers and return the proxied response
      const headers = new Headers(resp.headers);
      headers.set('x-proxied-by', 'cloudflare-worker');
      return new Response(resp.body, {
        status: resp.status,
        statusText: resp.statusText,
        headers,
      });
    } catch (err) {
      return new Response('Proxy error: ' + String(err), { status: 502 });
    }
  }
};
