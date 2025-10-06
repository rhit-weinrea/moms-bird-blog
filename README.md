# Mom's Creature Blog

Small Flask app for maintaining animal (bird) species profiles and posts. Features:

- Single editor user (credentials via environment variables EDITOR_USER / EDITOR_PASS; defaults: editor/password)
- Create species profiles
- Create posts with image uploads tied to a species
- Posts include time, date, caption, species, optional animal name, and notes

## Quick start

1. Create a virtualenv and install requirements

   ```bash
   python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
   ```

2. (Optional) Set editor credentials and Flask secret

   ```bash
   $env:EDITOR_USER = 'editor'; $env:EDITOR_PASS = 'password'; $env:FLASK_SECRET = 'change_me'
   ```

3. Run the app

   ```bash
   python app.py
   ```

Open `http://127.0.0.1:5000` in your browser. Log in as the editor to add species and posts.

## Notes

- Uploaded images are stored in `static/uploads`.
- This is a minimal prototype: no user registration, single editor only, no pagination or image processing.

## Deploying with Cloudflare Workers

This repository includes a small Cloudflare Worker at `worker/index.js` that can proxy requests to your Flask origin. This is useful if you want Cloudflare to sit in front of your app for caching, DDoS protection, and routing.

1. Install Wrangler (Cloudflare CLI) and login:

```bash
npm install -g wrangler
wrangler login
```

2. Set `ORIGIN_URL` in `wrangler.jsonc` or as a secret/environment value to point to your Flask origin, e.g. `https://myserver.example`.

3. Publish the worker:

```bash
wrangler publish
```

4. (Optional) Configure a custom domain in the Cloudflare dashboard and point it to the Worker.

Notes:
- The Worker is a simple HTTP proxy. For uploads you may want to use a direct S3/R2 endpoint or signed URLs because Workers have request size limits.
- Use Cloudflare settings (SSL/TLS: Full (strict), Page Rules, Firewall) to secure and tune behavior.