(() => {
  const SESSION_KEY='cam-academy-session-v1';
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  let rendering=false;
  let generation=0;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }
  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function token(){return sessionStorage.getItem(SESSION_KEY)||'';}
  function saveToken(value){if(value)sessionStorage.setItem(SESSION_KEY,value);else sessionStorage.removeItem(SESSION_KEY);}
  function money(cents){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(cents||0)/100);}
  function fmtDate(value){if(!value)return '—';const d=new Date(`${value}T12:00:00`);return Number.isNaN(d.getTime())?value:d.toLocaleDateString();}
  function notify(message){if(typeof window.toast==='function')window.toast(message);else console.log(message);}
  async function request(url,options={}){
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token()&&!headers.Authorization)headers.Authorization=`Bearer ${token()}`;
    const response=await fetch(url,{cache:'no-store',...options,headers});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok){
      const detail=typeof data?.detail==='string'?data.detail:(data?.detail?JSON.stringify(data.detail):`Request failed (${response.status})`);
      const error=new Error(detail);error.status=response.status;throw error;
    }
    return data;
  }

  function ensureTab(){
    const tabs=qs('#academyWorkspace .academy-tabs');if(!tabs)return;
    let button=qs('[data-academy-parent-tab]',tabs);
    if(!button){
      button=document.createElement('button');button.type='button';button.dataset.academyParentTab='1';button.textContent='Parent Portal';
      button.onclick=()=>{location.hash='academy?tab=parent';};
      const access=qs('[data-academy-access-tab]',tabs);
      if(access)tabs.insertBefore(button,access);else tabs.appendChild(button);
    }
    if(route().page==='academy'&&route().tab==='parent')qsa('button',tabs).forEach(btn=>btn.classList.toggle('active',btn===button));else button.classList.remove('active');
  }

  function loginView(){
    return `<section class="academy-parent-shell"><section class="academy-section-head"><div><span class="academy-kicker">FAMILY SELF-SERVICE</span><h1>Parent Portal</h1><p>Sign in to view your linked children, invoices, payment methods, payments and receipts.</p></div></section><article class="panel academy-parent-login"><div><h2>Parent Sign In</h2><p>Your account must be linked to a guardian record by the Academy.</p></div><form id="academyParentLoginForm" class="academy-parent-form"><label><span>Email</span><input name="email" type="email" autocomplete="username" required></label><label><span>Password</span><input name="password" type="password" autocomplete="current-password" required></label><button type="submit" class="primary">Sign In</button></form></article></section>`;
  }

  function paymentMethodRows(methods){
    if(!methods.length)return `<div class="academy-parent-empty"><strong>No saved payment methods</strong><span>Add a CAM sandbox card for QA testing.</span></div>`;
    return methods.map(method=>`<div class="academy-parent-method" data-payment-method="${method.id}"><div class="academy-parent-card-mark">${esc(method.brand?.slice(0,1)||'C')}</div><div><strong>${esc(method.brand)} •••• ${esc(method.last4)}</strong><small>Expires ${String(method.exp_month).padStart(2,'0')}/${String(method.exp_year).slice(-2)}</small></div>${method.is_default?'<span class="academy-parent-pill good">Default</span>':`<button class="secondary" data-make-default="${method.id}">Make default</button>`}<button class="danger" data-remove-method="${method.id}">Remove</button></div>`).join('');
  }

  function invoiceRows(accounts,methods){
    const invoices=accounts.flatMap(account=>(account.invoices||[]).map(invoice=>({...invoice,account_name:account.account_name})));
    if(!invoices.length)return `<div class="academy-parent-empty"><strong>No invoices yet</strong><span>New Academy invoices will appear here.</span></div>`;
    const defaultMethod=methods.find(x=>x.is_default)||methods[0];
    return invoices.map(invoice=>{
      const balance=Number(invoice.balance_due_cents||0);
      return `<article class="academy-parent-invoice ${balance>0?'open':'paid'}" data-parent-invoice="${invoice.id}"><div><span class="academy-parent-pill ${balance>0?'due':'good'}">${esc(invoice.status)}</span><h3>${esc(invoice.invoice_number||`Invoice ${invoice.id}`)}</h3><p>${esc(invoice.account_name||'Family account')} · Due ${esc(fmtDate(invoice.due_date))}</p></div><div class="academy-parent-invoice-money"><small>Invoice total</small><strong>${money(invoice.total_cents)}</strong><span>${balance>0?`${money(balance)} remaining`:'Paid in full'}</span></div>${balance>0?`<button class="primary" data-pay-invoice="${invoice.id}" data-balance="${balance}" ${defaultMethod?'':'disabled'}>${defaultMethod?'Pay invoice':'Add card to pay'}</button>`:`<span class="academy-parent-paid-check">✓ Paid</span>`}</article>`;
    }).join('');
  }

  function paymentRows(accounts){
    const payments=accounts.flatMap(account=>(account.payments||[]).map(payment=>({...payment,account_name:account.account_name}))).sort((a,b)=>String(b.received_on||'').localeCompare(String(a.received_on||''))||Number(b.id)-Number(a.id));
    if(!payments.length)return `<div class="academy-parent-empty"><strong>No payments yet</strong><span>Receipts will appear after successful payments.</span></div>`;
    return payments.map(payment=>`<div class="academy-parent-payment"><div><strong>${money(payment.amount_cents)}</strong><small>${esc(payment.account_name||'Family account')} · ${esc(fmtDate(payment.received_on))}</small></div><span class="academy-parent-pill good">${esc(payment.status)}</span><button class="secondary" data-view-receipt="${payment.id}">${esc(payment.receipt_number||'Receipt')}</button></div>`).join('');
  }

  function portalView(summary){
    const accounts=summary.accounts||[];const methods=summary.payment_methods||[];const players=summary.players||[];
    const totalBalance=accounts.reduce((sum,a)=>sum+Number(a.balance_cents||0),0);
    const openInvoices=accounts.flatMap(a=>a.invoices||[]).filter(i=>Number(i.balance_due_cents||0)>0).length;
    const receipts=accounts.reduce((sum,a)=>sum+(a.payments||[]).length,0);
    return `<section class="academy-parent-shell"><section class="academy-section-head academy-parent-head"><div><span class="academy-kicker">FAMILY SELF-SERVICE · BILLING</span><h1>Parent Portal</h1><p>Manage your family's Academy billing without exposing full card details to CAM.</p></div><div class="academy-parent-session"><span>Signed in as</span><strong>${esc(summary.user.display_name)}</strong><small>Parent</small><button id="academyParentLogout" class="secondary">Sign Out</button></div></section>
      <section class="academy-parent-stats"><article><span>Family balance</span><strong>${money(totalBalance)}</strong><small>${openInvoices} open invoice${openInvoices===1?'':'s'}</small></article><article><span>Linked children</span><strong>${players.length}</strong><small>${players.map(x=>esc(x.name)).join(', ')||'No linked players'}</small></article><article><span>Payment methods</span><strong>${methods.length}</strong><small>${methods.length?'Masked/tokenized only':'Add a sandbox method'}</small></article><article><span>Receipts</span><strong>${receipts}</strong><small>Successful payments</small></article></section>
      <div id="academyParentEditor"></div>
      <section class="academy-parent-grid"><article class="panel"><div class="panel-head"><div><h2>Invoices</h2><p>Pay the full balance or a partial amount using a saved test method.</p></div></div><div class="academy-parent-invoices">${invoiceRows(accounts,methods)}</div></article>
      <aside class="academy-parent-side"><article class="panel"><div class="panel-head"><div><h2>Payment Methods</h2><p>${summary.payment_mode==='sandbox'?'CAM QA sandbox is active. Test cards only.':'Card entry is disabled until a payment provider is configured.'}</p></div>${summary.payment_mode==='sandbox'?'<button id="academyAddSandboxCard" class="primary">＋ Add Test Card</button>':''}</div><div class="academy-parent-methods">${paymentMethodRows(methods)}</div></article>
      <article class="panel"><div class="panel-head"><div><h2>Children</h2><p>Billing access is limited to guardian-linked family records.</p></div></div><div class="academy-parent-children">${players.map(player=>`<div><strong>${esc(player.name)}</strong><span>${esc(player.status||'active')}</span></div>`).join('')||'<div class="academy-parent-empty"><strong>No linked children</strong></div>'}</div></article></aside></section>
      <article class="panel academy-parent-history"><div class="panel-head"><div><h2>Payments & Receipts</h2><p>Successful payments are posted to the Academy ledger and receive a receipt number.</p></div></div>${paymentRows(accounts)}</article></section>`;
  }

  function cardForm(){
    return `<form id="academySandboxCardForm" class="panel academy-parent-editor"><div class="academy-parent-editor-head"><div><span class="academy-kicker">QA SANDBOX</span><h2>Add Test Card</h2><p>Only CAM-approved sandbox numbers are accepted. Never enter a real card.</p></div><button type="button" class="secondary" data-parent-close-editor>Cancel</button></div><div class="academy-parent-card-warning"><strong>Recommended success card:</strong> 4242 4242 4242 4242 · expiry 12/34 · CVC 123</div><div class="academy-parent-form-grid"><label class="wide"><span>Test card number</span><input name="card_number" inputmode="numeric" autocomplete="off" placeholder="4242 4242 4242 4242" required></label><label><span>Expiry month</span><input name="exp_month" type="number" min="1" max="12" value="12" required></label><label><span>Expiry year</span><input name="exp_year" type="number" min="2026" max="2100" value="2034" required></label><label><span>Sandbox CVC</span><input name="cvc" inputmode="numeric" minlength="3" maxlength="4" autocomplete="off" value="123" required></label><label class="check"><input name="make_default" type="checkbox" checked><span>Make default</span></label></div><div class="academy-form-actions"><span id="academyParentCardStatus"></span><button class="primary" type="submit">Save Test Card</button></div></form>`;
  }

  function payForm(invoiceId,balance,methods){
    const defaultMethod=methods.find(x=>x.is_default)||methods[0];
    return `<form id="academyParentPayForm" class="panel academy-parent-editor" data-invoice-id="${invoiceId}"><div class="academy-parent-editor-head"><div><span class="academy-kicker">INVOICE PAYMENT</span><h2>Pay Invoice</h2><p>Current balance: ${money(balance)}</p></div><button type="button" class="secondary" data-parent-close-editor>Cancel</button></div><div class="academy-parent-form-grid"><label class="wide"><span>Payment method</span><select name="payment_method_id" required>${methods.map(method=>`<option value="${method.id}" ${method.id===defaultMethod?.id?'selected':''}>${esc(method.brand)} •••• ${esc(method.last4)}${method.is_default?' · Default':''}</option>`).join('')}</select></label><label><span>Amount (USD)</span><input name="amount" type="number" min="0.01" max="${(balance/100).toFixed(2)}" step="0.01" value="${(balance/100).toFixed(2)}" required></label></div><div class="academy-form-actions"><span id="academyParentPayStatus"></span><button class="primary" type="submit">Pay ${money(balance)}</button></div></form>`;
  }

  function receiptView(receipt){
    const allocations=receipt.allocations||[];
    return `<article class="panel academy-parent-editor academy-parent-receipt"><div class="academy-parent-editor-head"><div><span class="academy-kicker">PAYMENT RECEIPT</span><h2>${esc(receipt.receipt_number||'Receipt')}</h2><p>${esc(fmtDate(receipt.received_on))}</p></div><button type="button" class="secondary" data-parent-close-editor>Close</button></div><div class="academy-parent-receipt-total"><span>Payment received</span><strong>${money(receipt.amount_cents)}</strong></div><div class="academy-parent-receipt-lines">${allocations.map(row=>`<div><span>${esc(row.invoice_number||`Invoice ${row.invoice_id}`)}${row.player_name?` · ${esc(row.player_name)}`:''}</span><strong>${money(Number(row.amount_cents||0)-Number(row.refunded_cents||0))}</strong></div>`).join('')}</div></article>`;
  }

  async function rerender(){await renderParent(true);}

  function wirePortal(summary){
    const editor=qs('#academyParentEditor');
    qs('#academyParentLogout')?.addEventListener('click',async()=>{try{await request('/api/auth/logout',{method:'POST'});}catch{}saveToken('');notify('Signed out.');await rerender();});
    qs('#academyAddSandboxCard')?.addEventListener('click',()=>{editor.innerHTML=cardForm();wireEditor(summary);editor.scrollIntoView({behavior:'smooth',block:'start'});});
    qsa('[data-make-default]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await request(`/api/academy/parent/payment-methods/${button.dataset.makeDefault}/default`,{method:'PUT'});notify('Default payment method updated.');await rerender();}catch(error){notify(error.message);button.disabled=false;}});
    qsa('[data-remove-method]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await request(`/api/academy/parent/payment-methods/${button.dataset.removeMethod}`,{method:'DELETE'});notify('Payment method removed.');await rerender();}catch(error){notify(error.message);button.disabled=false;}});
    qsa('[data-pay-invoice]').forEach(button=>button.onclick=()=>{editor.innerHTML=payForm(Number(button.dataset.payInvoice),Number(button.dataset.balance),summary.payment_methods||[]);wireEditor(summary);editor.scrollIntoView({behavior:'smooth',block:'start'});});
    qsa('[data-view-receipt]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const receipt=await request(`/api/academy/parent/receipts/${button.dataset.viewReceipt}`);editor.innerHTML=receiptView(receipt);wireEditor(summary);editor.scrollIntoView({behavior:'smooth',block:'start'});}catch(error){notify(error.message);}finally{button.disabled=false;}});
  }

  function wireEditor(summary){
    const editor=qs('#academyParentEditor');qsa('[data-parent-close-editor]',editor).forEach(button=>button.onclick=()=>{editor.innerHTML='';});
    const card=qs('#academySandboxCardForm',editor);if(card)card.onsubmit=async event=>{event.preventDefault();const fd=new FormData(card);const button=qs('button[type="submit"]',card);const status=qs('#academyParentCardStatus',card);button.disabled=true;status.textContent='Saving…';try{await request('/api/academy/parent/payment-methods/sandbox',{method:'POST',body:JSON.stringify({card_number:fd.get('card_number'),exp_month:Number(fd.get('exp_month')),exp_year:Number(fd.get('exp_year')),cvc:fd.get('cvc'),make_default:fd.get('make_default')==='on'})});notify('Test payment method saved.');await rerender();}catch(error){status.textContent=error.message;button.disabled=false;}};
    const pay=qs('#academyParentPayForm',editor);if(pay)pay.onsubmit=async event=>{event.preventDefault();const fd=new FormData(pay);const amount=Math.round(Number(fd.get('amount'))*100);const button=qs('button[type="submit"]',pay);const status=qs('#academyParentPayStatus',pay);button.disabled=true;status.textContent='Processing…';try{const result=await request(`/api/academy/parent/invoices/${pay.dataset.invoiceId}/pay`,{method:'POST',body:JSON.stringify({payment_method_id:Number(fd.get('payment_method_id')),amount_cents:amount})});notify(`Payment received · ${result.payment.receipt_number}`);await rerender();}catch(error){status.textContent=error.message;button.disabled=false;}};
  }

  function wireLogin(){
    const form=qs('#academyParentLoginForm');if(!form)return;
    form.onsubmit=async event=>{event.preventDefault();const fd=new FormData(form);const button=qs('button[type="submit"]',form);button.disabled=true;try{const result=await request('/api/auth/login',{method:'POST',body:JSON.stringify({email:fd.get('email'),password:fd.get('password')})});if(result.user?.role!=='parent'){try{await request('/api/auth/logout',{method:'POST',headers:{Authorization:`Bearer ${result.token}`}});}catch{}throw new Error('This portal requires a parent account.');}saveToken(result.token);notify('Signed in to Parent Portal.');await rerender();}catch(error){notify(error.message);button.disabled=false;}};
  }

  async function renderParent(force=false){
    if(rendering)return;if(route().page!=='academy'||route().tab!=='parent')return;
    const content=qs('#academyWorkspace .academy-content');if(!content)return;
    const myGeneration=++generation;rendering=true;content.dataset.academyParentOwned='1';
    if(force||!content.dataset.parentPortalRendered)content.innerHTML='<div class="academy-parent-loading">Loading Parent Portal…</div>';
    try{
      if(!token()){content.innerHTML=loginView();content.dataset.parentPortalRendered='1';wireLogin();return;}
      let me;try{me=await request('/api/auth/me');}catch(error){if(error.status===401){saveToken('');content.innerHTML=loginView();content.dataset.parentPortalRendered='1';wireLogin();return;}throw error;}
      if(me.role!=='parent'){content.innerHTML=`<section class="academy-parent-shell"><article class="panel academy-parent-login"><h2>Parent account required</h2><p>Signed in as ${esc(me.display_name)} (${esc(me.role)}). Sign out from Access & Roles or use a linked parent account.</p></article></section>`;content.dataset.parentPortalRendered='1';return;}
      const summary=await request('/api/academy/parent/billing');if(myGeneration!==generation)return;content.innerHTML=portalView(summary);content.dataset.parentPortalRendered='1';wirePortal(summary);
    }catch(error){content.innerHTML=`<div class="academy-parent-empty"><strong>Could not load Parent Portal</strong><span>${esc(error.message)}</span></div>`;content.dataset.parentPortalRendered='1';}
    finally{rendering=false;}
  }

  function apply(){
    if(route().page!=='academy')return;ensureTab();
    if(route().tab==='parent')renderParent();
  }
  window.addEventListener('hashchange',()=>{const content=qs('#academyWorkspace .academy-content');if(content){delete content.dataset.parentPortalRendered;}setTimeout(apply,0);});
  const observer=new MutationObserver(()=>{if(route().page!=='academy')return;const content=qs('#academyWorkspace .academy-content');if(route().tab==='parent'&&content&&!content.dataset.academyParentOwned)setTimeout(apply,0);else ensureTab();});
  observer.observe(document.body,{childList:true,subtree:true});
  setTimeout(apply,0);
})();
