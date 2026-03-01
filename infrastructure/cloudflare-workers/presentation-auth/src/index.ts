/**
 * KMFlow Presentation Auth Worker
 *
 * Server-side OTP authentication for KMFlow presentation using Descope.
 * Validates JWT tokens before serving content from Cloudflare Pages.
 */

import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose';

interface Env {
  DESCOPE_PROJECT_ID: string;
  PAGES_URL: string;
  WORKER_DOMAIN: string;
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
}

// Allowed email addresses and domains
const ALLOWED_EMAILS = ['proth1@gmail.com', 'drj.infinity@gmail.com'];
const ALLOWED_DOMAINS = ['kpmg.com'];

// Descope session cookie names
const SESSION_COOKIE = 'DS';
const REFRESH_COOKIE = 'DSR';
const PENDING_EMAIL_COOKIE = 'PENDING_EMAIL';
const LOGIN_PATH = '/auth/login';

// KMFlow logo SVG markup
const KMFLOW_LOGO_SVG = `<svg viewBox="0 0 120 36" xmlns="http://www.w3.org/2000/svg">
  <text x="0" y="28" font-family="'Open Sans Condensed', Arial, sans-serif" font-size="32" font-weight="700" fill="#00338D" letter-spacing="1">KMFlow</text>
</svg>`;

function escapeHtml(unsafe: string): string {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Handle login page
    if (url.pathname === LOGIN_PATH) {
      return renderLoginPage(env, url, request);
    }

    // Handle OTP send
    if (url.pathname === '/auth/send-otp' && request.method === 'POST') {
      return handleSendOTP(request, env, url);
    }

    // Handle OTP verification
    if (url.pathname === '/auth/verify-otp' && request.method === 'POST') {
      return handleVerifyOTP(request, env, url);
    }

    // Handle logout
    if (url.pathname === '/auth/logout') {
      return handleLogout(url);
    }

    // Check for valid session
    const sessionToken = getSessionToken(request);
    const refreshToken = getRefreshToken(request);

    if (!sessionToken && !refreshToken) {
      return redirectToLogin(url);
    }

    // Validate JWT
    let validation = sessionToken ? await validateDescopeJWT(sessionToken) : { valid: false, reason: 'No session token' };

    // If session expired but we have refresh token, try server-side refresh
    if (!validation.valid && refreshToken) {
      const refreshResult = await refreshSessionServerSide(refreshToken, env);

      if (refreshResult.success && refreshResult.sessionJwt) {
        validation = await validateDescopeJWT(refreshResult.sessionJwt);

        if (validation.valid) {
          const email = validation.payload?.email as string | undefined;
          if (!email || !isEmailAuthorized(email)) {
            return renderUnauthorizedPage(email);
          }
          return proxyToPagesWithNewSession(request, env, url, refreshResult.sessionJwt, refreshResult.refreshJwt);
        }
      }

      return redirectToLogin(url);
    }

    if (!validation.valid) {
      return redirectToLogin(url);
    }

    // Check email authorization
    const email = validation.payload?.email as string | undefined;
    if (!email || !isEmailAuthorized(email)) {
      return renderUnauthorizedPage(email);
    }

    // IMPORTANT: Do NOT add redirects to specific .html filenames here.
    // Pages serves index.html at / automatically. A hardcoded redirect
    // to /kmflow-platform-presentation.html caused a production incident
    // (2026-02-17) where users were silently served stale content for hours.

    // Proxy to Pages (serves index.html at / automatically)
    return proxyToPages(request, env, url);
  },
};

function isEmailAuthorized(email: string): boolean {
  const lowerEmail = email.toLowerCase();

  if (ALLOWED_EMAILS.includes(lowerEmail)) {
    return true;
  }

  const domain = lowerEmail.split('@')[1];
  if (domain && ALLOWED_DOMAINS.includes(domain)) {
    return true;
  }

  return false;
}

function renderUnauthorizedPage(email: string | undefined): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Access Denied - KMFlow</title>
  <link href="https://fonts.googleapis.com/css2?family=Open+Sans+Condensed:wght@300;700&family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Open Sans', Arial, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      background: linear-gradient(135deg, #00338D 0%, #005EB8 100%);
    }
    .container {
      background: white;
      padding: 48px 40px;
      border-radius: 8px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      max-width: 480px;
      width: 100%;
      margin: 20px;
      text-align: center;
    }
    .icon {
      width: 64px;
      height: 64px;
      background: #fee2e2;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 24px;
    }
    .icon svg { width: 32px; height: 32px; color: #dc2626; }
    h1 { font-family: 'Open Sans Condensed', sans-serif; font-size: 28px; color: #00338D; margin-bottom: 12px; }
    p { color: #666666; margin-bottom: 8px; line-height: 1.6; }
    .email { font-family: monospace; background: #f5f5f5; padding: 4px 8px; border-radius: 4px; }
    .allowed { margin-top: 24px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-size: 14px; }
    .logout-btn {
      display: inline-block;
      margin-top: 24px;
      padding: 12px 24px;
      background: #00338D;
      color: white;
      text-decoration: none;
      border-radius: 4px;
      font-weight: 600;
      transition: background 0.2s;
    }
    .logout-btn:hover { background: #005EB8; }
  </style>
</head>
<body>
  <div class="container">
    <div class="icon">
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
      </svg>
    </div>
    <h1>Access Denied</h1>
    <p>You have authenticated successfully, but your email is not authorized to view this content.</p>
    ${email ? `<p>Signed in as: <span class="email">${escapeHtml(email)}</span></p>` : ''}
    <div class="allowed">
      <p>Access is restricted to:</p>
      <p>Authorized email addresses only</p>
    </div>
    <a href="/auth/logout" class="logout-btn">Sign Out &amp; Try Another Account</a>
  </div>
</body>
</html>`;

  return new Response(html, {
    status: 403,
    headers: { 'Content-Type': 'text/html;charset=UTF-8' },
  });
}

function getSessionToken(request: Request): string | null {
  const cookie = request.headers.get('Cookie') || '';
  const match = cookie.match(new RegExp(`${SESSION_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}

function getRefreshToken(request: Request): string | null {
  const cookie = request.headers.get('Cookie') || '';
  const match = cookie.match(new RegExp(`${REFRESH_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}

async function refreshSessionServerSide(
  refreshToken: string,
  env: Env
): Promise<{ success: boolean; sessionJwt?: string; refreshJwt?: string }> {
  try {
    const response = await fetch('https://api.descope.com/v1/auth/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.DESCOPE_PROJECT_ID}`,
      },
      body: JSON.stringify({ refreshJwt: refreshToken }),
    });

    if (!response.ok) {
      return { success: false };
    }

    const data = await response.json() as {
      sessionJwt?: string;
      refreshJwt?: string;
    };

    return {
      success: true,
      sessionJwt: data.sessionJwt,
      refreshJwt: data.refreshJwt,
    };
  } catch {
    return { success: false };
  }
}

async function proxyToPagesWithNewSession(
  request: Request,
  env: Env,
  url: URL,
  sessionJwt: string,
  refreshJwt?: string
): Promise<Response> {
  const pagesUrl = new URL(url.pathname + url.search, env.PAGES_URL);

  const headers = new Headers(request.headers);
  if (env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
    headers.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
    headers.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
  }

  const response = await fetch(pagesUrl.toString(), {
    method: request.method,
    headers: headers,
  });

  const newHeaders = new Headers(response.headers);
  newHeaders.append('Set-Cookie', `${SESSION_COOKIE}=${sessionJwt}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=28800`);

  if (refreshJwt) {
    newHeaders.append('Set-Cookie', `${REFRESH_COOKIE}=${refreshJwt}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
}

function redirectToLogin(originalUrl: URL): Response {
  const loginUrl = new URL(LOGIN_PATH, originalUrl.origin);
  loginUrl.searchParams.set('redirect', originalUrl.pathname + originalUrl.search);
  return Response.redirect(loginUrl.toString(), 302);
}

// JWKS endpoint for Descope JWT signature verification
const DESCOPE_JWKS_URL = 'https://api.descope.com/P39ERvEl6A8ec0DKtrKBvzM4Ue5V/.well-known/jwks.json';
const JWKS = createRemoteJWKSet(new URL(DESCOPE_JWKS_URL));

async function validateDescopeJWT(
  token: string
): Promise<{ valid: boolean; reason?: string; payload?: Record<string, unknown> }> {
  try {
    // jose v6 requires string | string[] for issuer (no callback)
    // Descope issuer format: https://api.descope.com/v1/apps/<projectId>
    const { payload } = await jwtVerify(token, JWKS, {
      issuer: 'https://api.descope.com/v1/apps/P39ERvEl6A8ec0DKtrKBvzM4Ue5V',
    });

    return { valid: true, payload: payload as unknown as Record<string, unknown> };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return { valid: false, reason: message };
  }
}

async function proxyToPages(request: Request, env: Env, url: URL): Promise<Response> {
  const pagesUrl = new URL(url.pathname + url.search, env.PAGES_URL);

  const headers = new Headers(request.headers);
  if (env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
    headers.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
    headers.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
  }

  const response = await fetch(pagesUrl.toString(), {
    method: request.method,
    headers: headers,
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

function handleLogout(url: URL): Response {
  const loginUrl = new URL(LOGIN_PATH, url.origin);

  return new Response(null, {
    status: 302,
    headers: {
      Location: loginUrl.toString(),
      'Set-Cookie': [
        `${SESSION_COOKIE}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT`,
        `${REFRESH_COOKIE}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT`,
      ].join(', '),
    },
  });
}

async function handleSendOTP(request: Request, env: Env, url: URL): Promise<Response> {
  try {
    const formData = await request.formData();
    const email = formData.get('email') as string;
    const redirect = formData.get('redirect') as string || '/';

    if (!email) {
      return redirectToLoginWithError(url, 'Email is required', redirect);
    }

    if (!isEmailAuthorized(email)) {
      return redirectToLoginWithError(url, `Access denied for ${email}. Only authorized email addresses are allowed.`, redirect);
    }

    const response = await fetch(`https://api.descope.com/v1/auth/otp/signup-in/email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.DESCOPE_PROJECT_ID}`,
      },
      body: JSON.stringify({
        loginId: email,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('Descope OTP error:', errorData);
      return redirectToLoginWithError(url, 'Failed to send verification code. Please try again.', redirect);
    }

    const loginUrl = new URL(LOGIN_PATH, env.WORKER_DOMAIN || url.origin);
    loginUrl.searchParams.set('step', 'verify');
    loginUrl.searchParams.set('redirect', redirect);

    const headers = new Headers();
    headers.set('Location', loginUrl.toString());
    headers.append('Set-Cookie', `${PENDING_EMAIL_COOKIE}=${encodeURIComponent(email)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=600`);

    return new Response(null, { status: 302, headers });
  } catch (error) {
    console.error('OTP send error:', error);
    return redirectToLoginWithError(url, 'An error occurred. Please try again.', '/');
  }
}

async function handleVerifyOTP(request: Request, env: Env, url: URL): Promise<Response> {
  try {
    const formData = await request.formData();
    const code = formData.get('code') as string;
    const redirect = formData.get('redirect') as string || '/';

    const cookie = request.headers.get('Cookie') || '';
    const emailMatch = cookie.match(new RegExp(`${PENDING_EMAIL_COOKIE}=([^;]+)`));
    const email = emailMatch ? decodeURIComponent(emailMatch[1]) : null;

    if (!email) {
      return redirectToLoginWithError(url, 'Session expired. Please start over.', redirect);
    }

    if (!code || code.length !== 6) {
      return redirectToLoginWithError(url, 'Please enter the 6-digit code from your email.', redirect, 'verify');
    }

    const response = await fetch(`https://api.descope.com/v1/auth/otp/verify/email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.DESCOPE_PROJECT_ID}`,
      },
      body: JSON.stringify({
        loginId: email,
        code: code,
      }),
    });

    if (!response.ok) {
      return redirectToLoginWithError(url, 'Invalid or expired code. Please try again.', redirect, 'verify');
    }

    const data = await response.json() as {
      sessionJwt?: string;
      refreshJwt?: string;
      user?: { email?: string };
    };

    const verifiedEmail = data.user?.email || email;
    if (!isEmailAuthorized(verifiedEmail)) {
      return renderUnauthorizedPage(verifiedEmail);
    }

    const headers = new Headers();
    headers.set('Location', redirect);

    headers.append('Set-Cookie', `${PENDING_EMAIL_COOKIE}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT`);

    if (data.sessionJwt) {
      headers.append('Set-Cookie', `${SESSION_COOKIE}=${data.sessionJwt}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=28800`);
    }
    if (data.refreshJwt) {
      headers.append('Set-Cookie', `${REFRESH_COOKIE}=${data.refreshJwt}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`);
    }

    return new Response(null, { status: 302, headers });
  } catch (error) {
    console.error('OTP verify error:', error);
    return redirectToLoginWithError(url, 'Verification failed. Please try again.', '/');
  }
}

function redirectToLoginWithError(url: URL, error: string, redirect: string, step?: string): Response {
  const loginUrl = new URL(LOGIN_PATH, url.origin);
  loginUrl.searchParams.set('error', error);
  loginUrl.searchParams.set('redirect', redirect);
  if (step) {
    loginUrl.searchParams.set('step', step);
  }
  return Response.redirect(loginUrl.toString(), 302);
}

/**
 * Render the KMFlow-branded login page with OTP authentication
 */
function renderLoginPage(env: Env, url: URL, request: Request): Response {
  const redirect = url.searchParams.get('redirect') || '/';
  const error = url.searchParams.get('error') || '';
  const step = url.searchParams.get('step') || 'email';

  const cookie = request.headers.get('Cookie') || '';
  const emailMatch = cookie.match(new RegExp(`${PENDING_EMAIL_COOKIE}=([^;]+)`));
  const pendingEmail = emailMatch ? decodeURIComponent(emailMatch[1]) : '';

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign In - KMFlow Platform</title>
  <link href="https://fonts.googleapis.com/css2?family=Open+Sans+Condensed:wght@300;700&family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Open Sans', Arial, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      background: linear-gradient(135deg, #001D48 0%, #00338D 50%, #005EB8 100%);
    }
    .login-container {
      background: white;
      padding: 48px 40px;
      border-radius: 8px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      max-width: 440px;
      width: 100%;
      margin: 20px;
    }
    .logo {
      text-align: center;
      margin-bottom: 32px;
    }
    .logo svg {
      height: 44px;
      margin-bottom: 12px;
    }
    .product-tagline {
      font-size: 13px;
      color: #005EB8;
      font-weight: 600;
      letter-spacing: 0.5px;
      margin-top: 4px;
    }
    .subtitle {
      text-align: center;
      color: #666666;
      font-size: 14px;
      margin-bottom: 32px;
    }
    .form-group { margin-bottom: 20px; }
    label {
      display: block;
      font-size: 14px;
      font-weight: 600;
      color: #333333;
      margin-bottom: 8px;
    }
    input[type="email"], input[type="text"] {
      width: 100%;
      padding: 14px 16px;
      border: 2px solid #e0e0e0;
      border-radius: 4px;
      font-size: 16px;
      font-family: 'Open Sans', Arial, sans-serif;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    input[type="email"]:focus, input[type="text"]:focus {
      outline: none;
      border-color: #00338D;
      box-shadow: 0 0 0 3px rgba(0, 51, 141, 0.1);
    }
    .otp-input {
      text-align: center;
      font-size: 24px;
      font-weight: 600;
      letter-spacing: 8px;
      font-family: 'Courier New', monospace;
    }
    .btn {
      width: 100%;
      padding: 14px 24px;
      background: #00338D;
      color: white;
      border: none;
      border-radius: 4px;
      font-size: 16px;
      font-weight: 600;
      font-family: 'Open Sans', Arial, sans-serif;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover { background: #005EB8; }
    .btn:disabled { background: #94a3b8; cursor: not-allowed; }
    .btn-secondary {
      background: transparent;
      color: #00338D;
      border: 2px solid #00338D;
      margin-top: 12px;
    }
    .btn-secondary:hover { background: #f0f4f8; }
    .error {
      background: #fef2f2;
      border: 1px solid #fecaca;
      color: #dc2626;
      padding: 14px;
      border-radius: 4px;
      font-size: 14px;
      margin-bottom: 20px;
    }
    .info-box {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      color: #1e40af;
      padding: 16px;
      border-radius: 4px;
      text-align: center;
      margin-bottom: 20px;
    }
    .info-box .email {
      font-weight: 600;
      font-family: monospace;
      background: #dbeafe;
      padding: 2px 8px;
      border-radius: 4px;
    }
    .footer {
      text-align: center;
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid #e0e0e0;
    }
    .footer p { color: #94a3b8; font-size: 12px; }
    .footer a { color: #00338D; text-decoration: none; }
    #email-view, #verify-view { display: none; }
    #email-view.active, #verify-view.active { display: block; }
    .access-info {
      background: #f5f5f5;
      border-radius: 4px;
      padding: 16px;
      margin-top: 24px;
      font-size: 13px;
      color: #666666;
    }
    .access-info strong { color: #00338D; }
  </style>
</head>
<body>
  <div class="login-container">
    <div class="logo">
      ${KMFLOW_LOGO_SVG}
      <div class="product-tagline">AI-Powered Process Intelligence</div>
    </div>
    <p class="subtitle">Sign in to access the KMFlow platform presentation</p>

    ${error ? `<div class="error">${escapeHtml(error)}</div>` : ''}

    <div id="email-view" class="${step === 'email' ? 'active' : ''}">
      <form action="/auth/send-otp" method="POST">
        <input type="hidden" name="redirect" value="${escapeHtml(redirect)}">
        <div class="form-group">
          <label for="email">Email Address</label>
          <input type="email" id="email" name="email" required placeholder="you@company.com" autofocus>
        </div>
        <button type="submit" class="btn">Send Verification Code</button>
      </form>
      <div class="access-info">
        <strong>Authorized access only.</strong> This presentation is restricted to authorized personnel.
      </div>
    </div>

    <div id="verify-view" class="${step === 'verify' ? 'active' : ''}">
      <div class="info-box">
        We sent a 6-digit code to<br>
        <span class="email">${escapeHtml(pendingEmail)}</span>
      </div>
      <form action="/auth/verify-otp" method="POST">
        <input type="hidden" name="redirect" value="${escapeHtml(redirect)}">
        <div class="form-group">
          <label for="code">Verification Code</label>
          <input type="text" id="code" name="code" class="otp-input" required
                 pattern="[0-9]{6}" maxlength="6" inputmode="numeric" autocomplete="one-time-code"
                 placeholder="000000" autofocus>
        </div>
        <button type="submit" class="btn">Verify &amp; Sign In</button>
      </form>
      <form action="/auth/send-otp" method="POST">
        <input type="hidden" name="redirect" value="${escapeHtml(redirect)}">
        <input type="hidden" name="email" value="${escapeHtml(pendingEmail)}">
        <button type="submit" class="btn btn-secondary">Resend Code</button>
      </form>
      <a href="${LOGIN_PATH}?redirect=${encodeURIComponent(redirect)}" class="btn btn-secondary" style="display: block; text-align: center; text-decoration: none;">
        Use Different Email
      </a>
    </div>

    <div class="footer">
      <p>Protected by <a href="https://descope.com" target="_blank">Descope</a></p>
      <p style="margin-top: 8px;">&copy; 2026 KMFlow Platform</p>
    </div>
  </div>

  <script>
    const codeInput = document.getElementById('code');
    if (codeInput) {
      codeInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^0-9]/g, '');
        if (this.value.length === 6) {
          this.form.submit();
        }
      });
    }
  </script>
</body>
</html>`;

  return new Response(html, {
    headers: {
      'Content-Type': 'text/html;charset=UTF-8',
      'Cache-Control': 'no-store',
    },
  });
}
