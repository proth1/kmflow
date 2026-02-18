/**
 * KMFlow Presentation Auth Worker
 *
 * Server-side OTP authentication for KMFlow presentation using Descope.
 * Validates JWT tokens before serving content from Cloudflare Pages.
 */

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

// Official KPMG logo SVG path data (white version for dark backgrounds)
const KPMG_LOGO_PATH = 'M62.742.201v16.002l-.204.17-.204.168-.196.177-.187.177-.179.177-.178.185-.17.186-.17.185V.201h-17.89v14.57h-1.48V.2h-17.89v14.594h-1.48V.201H4.624v16.635L.056 31.919H4.07l2.016-6.677h.579L10 31.919h4.849l-3.233-6.677h7.333l-2.033 6.677h4.381l2.008-6.66h.97v-.017H34.04l-1.94 6.66h4.424l1.88-6.66h1.99l.052 6.66h3.709l4.262-6.66h2.79l-1.446 6.66h4.355l1.42-6.66h2.519l-.017.379.009.388.017.37.034.372.025.177.026.177.034.177.034.177.042.177.043.169.05.168.052.169.06.169.059.16.068.16.068.152.077.16.076.152.085.143.085.152.094.143.102.135.102.143.11.127.111.135.111.126.128.127.127.118.162.134.161.135.17.127.18.118.178.118.179.11.187.092.195.101.187.085.196.084.196.076.204.076.204.067.204.06.204.058.205.05.408.094.417.067.408.06.408.05.4.033.392.017.382.017h.366l.494-.008.493-.008.502-.025.502-.025.502-.043.501-.042.502-.05.502-.06.51-.067.511-.076.51-.084.51-.084.511-.093.51-.101.511-.101.519-.118 1.514-6.046h4.968V.202h-17.89zM6.282 24.618l.026-.093.06.093zm15.585-8.971l-.255.852-2.382 7.84-.094.279H11.31l-.604-1.282 8.43-8.54h-5.418l-6.593 7.04 2.135-7.04H5.262V.833h16.605v14.813zm4.62 6.627l-.128.008-.12.008-.127.008H25.644l-.145.008h-.136l-1.063-.008.493-1.804.23-.894.562-2.1h.365l.179-.007h.995l.502.008.46.016.204.008.195.017.187.026.17.025.154.025.144.042.136.043.12.05.102.05.093.068.085.068.068.084.043.068.034.067.034.076.025.084.017.093.01.093V18.714l-.01.119-.008.118-.025.135-.026.134-.076.287-.094.32-.093.27-.103.262-.11.244-.12.228-.059.1-.06.102-.068.101-.076.093-.077.093-.076.084-.085.084-.086.076-.093.068-.094.076-.102.059-.11.067-.111.06-.12.05-.118.05-.128.042-.136.051-.144.034-.154.033-.153.034-.17.025-.17.026-.179.017-.187.017zm12.096 2.344l1.744-6.155.068 6.155h-1.812zm2.654-9.848h-4.151l-2.859 9.848h-4.406l.204-.085.204-.084.196-.084.196-.093.187-.093.178-.11.179-.1.17-.11.17-.118.162-.118.153-.118.153-.135.145-.126.136-.144.136-.135.128-.151.127-.144.12-.16.11-.152.11-.168.102-.169.094-.169.094-.177.085-.185.085-.186.076-.185.068-.194.069-.202.05-.203.06-.202.043-.22.042-.21.06-.337.05-.32.035-.304.025-.287.01-.286-.01-.262-.008-.261-.034-.245-.034-.227-.06-.228-.059-.21-.085-.203-.094-.194-.102-.194-.119-.177-.136-.169-.11-.118-.111-.118-.12-.1-.127-.094-.136-.092-.136-.085-.145-.075-.144-.068-.153-.067-.153-.051-.162-.05-.162-.051-.17-.042-.17-.034-.17-.034-.179-.025-.366-.05-.365-.026-.375-.025-.382-.008h-4.824V.834h16.605v13.937zm10.089 9.848h-2.493l3.777-5.902zm9.28-9.57l-.008 3.415-.213.295-.195.304-.196.303-.179.304-.17.303-.17.312-.145.304-.144.303-.136.295-.12.304-.119.295-.102.287-.093.286-.085.278-.077.27-.068.27-.043.177-.042.186-.043.177-.034.185-.034.177-.025.177-.026.177-.017.186h-2.441l2.084-9.823-7.026-.008-6.287 9.831h-.46V.834h16.614v14.215zm9.58 13.591l-.35.06-.357.05-.357.05-.349.043-.348.033-.35.026-.34.017h-.561l-.221-.008-.213-.017-.212-.026-.205-.033-.195-.034-.196-.042-.187-.05-.179-.06-.178-.059-.17-.076-.162-.076-.162-.092-.153-.093-.145-.101-.136-.101-.136-.118-.119-.127-.119-.126-.11-.144-.103-.143-.093-.16-.085-.16-.085-.169-.068-.177-.06-.194-.051-.194-.051-.202-.034-.21-.026-.22-.017-.228-.009-.236h7.742l-.851 3.398zm9.816-4.021h-4.185l.689-2.749h-8.388l-.689 2.749h-4.057v-.565l.05-.236.043-.236.051-.253.051-.253.077-.278.076-.279.085-.278.094-.27.102-.27.11-.27.12-.26.119-.262.136-.261.136-.245.145-.253.161-.236.162-.236.161-.228.18-.219.186-.21.196-.203.196-.185.212-.186.213-.177.221-.16.238-.152.238-.135.247-.126.255-.118.264-.101.272-.085.281-.067.29-.06.297-.041.306-.026.315-.008.247.008.246.017.247.034.238.05.12.034.11.034.11.034.103.05.102.042.102.06.093.058.094.06.085.075.085.076.077.076.076.093.068.084.06.101.051.11.051.11.043.117.034.127.025.126.026.144.009.143v.312l-.017.169h5.002l.076-.346.068-.396.034-.211.017-.228.017-.227v-.236l-.008-.245-.025-.253-.026-.118-.017-.126-.034-.127-.034-.126-.042-.135-.043-.127-.05-.126-.06-.127-.06-.126-.077-.127-.076-.126-.085-.126-.102-.135-.11-.127-.112-.126-.119-.118-.127-.118-.136-.11-.136-.101-.145-.101-.153-.101-.153-.085-.162-.084-.17-.084-.17-.076-.179-.076-.187-.068-.187-.067-.187-.06-.204-.05-.196-.05-.213-.051-.212-.042-.213-.042-.221-.034-.23-.025-.468-.051-.476-.042-.502-.017-.51-.008-.383.008-.4.008-.417.025-.434.034-.45.05-.46.06-.468.075-.476.102-.238.05-.247.06-.238.067-.247.067-.247.076-.246.084-.247.085-.238.092-.247.102-.247.11-.238.109-.247.118-.238.126-.238.135-.238.135-.238.152V.833h16.63v23.784z';

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
    ${email ? `<p>Signed in as: <span class="email">${email}</span></p>` : ''}
    <div class="allowed">
      <p>Access is restricted to:</p>
      <p><strong>@kpmg.com</strong> or <strong>proth1@gmail.com</strong></p>
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

async function validateDescopeJWT(
  token: string
): Promise<{ valid: boolean; reason?: string; payload?: Record<string, unknown> }> {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      return { valid: false, reason: 'Invalid token format' };
    }

    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const payloadJson = atob(payloadB64);
    const payload = JSON.parse(payloadJson) as Record<string, unknown>;

    const exp = payload.exp as number | undefined;
    if (exp && exp < Date.now() / 1000) {
      return { valid: false, reason: 'Token expired' };
    }

    const iss = payload.iss as string | undefined;
    if (!iss || !iss.includes('descope')) {
      return { valid: false, reason: 'Invalid issuer' };
    }

    return { valid: true, payload };
  } catch {
    return { valid: false, reason: 'Parse error' };
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
      return redirectToLoginWithError(url, `Access denied for ${email}. Only @kpmg.com or proth1@gmail.com emails are allowed.`, redirect);
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
      height: 36px;
      margin-bottom: 16px;
    }
    .product-name {
      font-family: 'Open Sans Condensed', sans-serif;
      font-size: 28px;
      font-weight: 700;
      color: #00338D;
      letter-spacing: 1px;
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
      <svg viewBox="0.056 0.2 80.576 32.073" xmlns="http://www.w3.org/2000/svg">
        <path d="${KPMG_LOGO_PATH}" fill="#00338D"/>
      </svg>
      <div class="product-name">KMFlow</div>
      <div class="product-tagline">AI-Powered Process Intelligence</div>
    </div>
    <p class="subtitle">Sign in to access the KMFlow platform presentation</p>

    ${error ? `<div class="error">${error}</div>` : ''}

    <div id="email-view" class="${step === 'email' ? 'active' : ''}">
      <form action="/auth/send-otp" method="POST">
        <input type="hidden" name="redirect" value="${redirect}">
        <div class="form-group">
          <label for="email">Email Address</label>
          <input type="email" id="email" name="email" required placeholder="you@company.com" autofocus>
        </div>
        <button type="submit" class="btn">Send Verification Code</button>
      </form>
      <div class="access-info">
        <strong>Authorized access only.</strong> This presentation is restricted to KPMG and authorized personnel.
      </div>
    </div>

    <div id="verify-view" class="${step === 'verify' ? 'active' : ''}">
      <div class="info-box">
        We sent a 6-digit code to<br>
        <span class="email">${pendingEmail}</span>
      </div>
      <form action="/auth/verify-otp" method="POST">
        <input type="hidden" name="redirect" value="${redirect}">
        <div class="form-group">
          <label for="code">Verification Code</label>
          <input type="text" id="code" name="code" class="otp-input" required
                 pattern="[0-9]{6}" maxlength="6" inputmode="numeric" autocomplete="one-time-code"
                 placeholder="000000" autofocus>
        </div>
        <button type="submit" class="btn">Verify &amp; Sign In</button>
      </form>
      <form action="/auth/send-otp" method="POST">
        <input type="hidden" name="redirect" value="${redirect}">
        <input type="hidden" name="email" value="${pendingEmail}">
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
