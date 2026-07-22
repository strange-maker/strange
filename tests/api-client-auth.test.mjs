import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_API_BASE_URL="https://api.example.test";

const values=new Map();
globalThis.sessionStorage={
  getItem:key=>values.get(key) ?? null,
  setItem:(key,value)=>values.set(key,String(value)),
  removeItem:key=>values.delete(key),
};
globalThis.window=new EventTarget();

const client=await import(new URL(`../app/api-client.ts?test=${Date.now()}`,import.meta.url));

function tokens(access_token="old-access",refresh_token="old-refresh-token-that-is-long-enough-for-the-api") {
  return {access_token,refresh_token,user:{id:"1",email:"admin@example.com",full_name:"Admin",role:"admin",is_active:true}};
}

test("concurrent 401 responses share one refresh request",async()=>{
  values.clear(); let refreshCalls=0;
  globalThis.fetch=async(url,init={})=>{
    if (url.endsWith("/api/auth/login")) return Response.json(tokens());
    if (url.endsWith("/api/auth/refresh")) {
      refreshCalls += 1;
      await new Promise(resolve=>setTimeout(resolve,10));
      return Response.json(tokens("new-access","new-refresh-token-that-is-long-enough-for-the-api"));
    }
    const authorization=new Headers(init.headers).get("Authorization");
    return authorization === "Bearer new-access" ? Response.json({url}) : Response.json({detail:"expired"},{status:401});
  };

  await client.login("admin@example.com","password");
  const results=await Promise.all(["/one","/two","/three","/four"].map(path=>client.api(path)));
  assert.equal(refreshCalls,1);
  assert.equal(results.length,4);
  assert.ok(results.every(result=>result.url.startsWith("https://api.example.test/")));
});

test("failed refresh clears the session and emits the expiration event",async()=>{
  values.clear(); let expiredEvents=0;
  window.addEventListener(client.AUTH_EXPIRED_EVENT,()=>{expiredEvents += 1},{once:true});
  globalThis.fetch=async(url)=>{
    if (url.endsWith("/api/auth/login")) return Response.json(tokens());
    return Response.json({detail:"expired"},{status:401});
  };

  await client.login("admin@example.com","password");
  await assert.rejects(()=>client.api("/protected"),/登录已失效，请重新登录/);
  assert.equal(expiredEvents,1);
  assert.equal(client.hasSession(),false);
});

test("logout always clears the local session even when the API is unreachable",async()=>{
  values.clear();
  globalThis.fetch=async(url)=>{
    if (url.endsWith("/api/auth/login")) return Response.json(tokens());
    throw new Error("network unavailable");
  };
  await client.login("admin@example.com","password");
  await client.logout();
  assert.equal(client.hasSession(),false);
});
