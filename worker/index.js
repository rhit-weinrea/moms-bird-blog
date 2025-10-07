export default {
  // Simple proxy worker: forwards all requests to an origin server.
  // Configure ORIGIN_URL in wrangler (or dashboard) to point at your Flask app.
  async fetch(request, env) {
    // First, attempt to serve static assets (if the ASSETS binding exists)
    if (env && env.ASSETS) {
      try {
        const assetResp = await env.ASSETS.fetch(request);
        // If asset found (not a 404), return it
        if (assetResp && assetResp.status !== 404) {
          return assetResp;
        }
      } catch (e) {
        // ignore and fall back to proxy
      }
    }

    const origin = env.ORIGIN_URL || 'https://example.com';
    const url = new URL(request.url);
    const target = origin.replace(/\/$/, '') + url.pathname + url.search;

    const init = {
      method: request.method,
      headers: new Headers(request.headers),
      redirect: 'manual',
    };

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      init.body = await request.arrayBuffer();
    }

    try {
      const resp = await fetch(target, init);
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
