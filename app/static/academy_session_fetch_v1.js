(() => {
  const SESSION_KEY='cam-academy-session-v1';
  const nativeFetch=window.fetch.bind(window);

  window.fetch=async function academySessionFetch(input,init={}){
    let url;
    try{
      url=new URL(typeof input==='string'?input:input.url,window.location.href);
    }catch{
      return nativeFetch(input,init);
    }

    if(url.origin!==window.location.origin||!url.pathname.startsWith('/api/academy/')){
      return nativeFetch(input,init);
    }

    const headers=new Headers(init.headers||(typeof input!=='string'&&input.headers)||undefined);
    const token=sessionStorage.getItem(SESSION_KEY)||'';
    if(token&&!headers.has('Authorization')&&!headers.has('X-CAM-Session')){
      headers.set('Authorization',`Bearer ${token}`);
    }

    const response=await nativeFetch(input,{...init,headers});
    if(response.status===401){
      window.dispatchEvent(new CustomEvent('cam:academy-auth-required',{detail:{path:url.pathname}}));
    }
    return response;
  };
})();
