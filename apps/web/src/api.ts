const API=import.meta.env.VITE_API_URL||"";
function csrf(){return document.cookie.split("; ").find(x=>x.startsWith("agentforge_csrf="))?.split("=").slice(1).join("=")||""}
export async function apiFetch(input:RequestInfo|URL,init:RequestInit={}){const headers=new Headers(init.headers||{});if(init.method&&!["GET","HEAD","OPTIONS"].includes(init.method.toUpperCase()))headers.set("X-CSRF-Token",decodeURIComponent(csrf()));return fetch(input,{...init,headers,credentials:"same-origin"})}
export {API};
