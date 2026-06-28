const ALLOWED_PROXY_ROUTES = new Map([
  ["GET /health", "/health"],
  ["POST /payments/webhook", "/payments/webhook"],
  ["POST /mpesa/c2b", "/mpesa/c2b"],
  ["POST /mpesa/c2b/validation", "/mpesa/c2b/validation"],
  ["POST /mpesa/c2b/confirmation", "/mpesa/c2b/confirmation"],
  ["POST /mpesa/stk/callback", "/mpesa/stk/callback"],
]);

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: JSON_HEADERS,
  });
}

function getOriginBaseUrl(env) {
  const origin = env.ORIGIN_BASE_URL || "https://mazao-ai.fly.dev";
  return origin.replace(/\/+$/, "");
}

async function proxyToFly(request, env, upstreamPath) {
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${getOriginBaseUrl(env)}${upstreamPath}`);
  upstreamUrl.search = incomingUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-mazao-edge", "cloudflare-workers");
  headers.set("x-forwarded-host", incomingUrl.host);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const upstreamRequest = new Request(upstreamUrl.toString(), {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: "manual",
  });

  try {
    return await fetch(upstreamRequest);
  } catch (error) {
    return jsonResponse(
      {
        status: "origin_unavailable",
        origin: getOriginBaseUrl(env),
        error: error.message,
      },
      502,
    );
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const routeKey = `${request.method} ${url.pathname}`;

    if (url.pathname === "/" && request.method === "GET") {
      return jsonResponse({
        service: env.SERVICE_NAME || "mazao-edge-worker",
        status: "ok",
        mode: "cloudflare_edge_to_fly_origin",
        origin: getOriginBaseUrl(env),
        production_note:
          "Fly remains the Python bot and scheduler origin during the safe migration phase.",
      });
    }

    const upstreamPath = ALLOWED_PROXY_ROUTES.get(routeKey);
    if (!upstreamPath) {
      return jsonResponse(
        {
          status: "not_found",
          route: routeKey,
          allowed_routes: [...ALLOWED_PROXY_ROUTES.keys()],
        },
        404,
      );
    }

    return proxyToFly(request, env, upstreamPath);
  },
};
