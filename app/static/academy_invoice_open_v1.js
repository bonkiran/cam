(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let scheduled=false;
  let enhancing=false;

  function tab(){
    const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');
    if(page!=='academy')return null;return new URLSearchParams(query).get('tab')||'overview';
  }
  function esc(v=''){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
  function money(cents){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(cents||0)/100);}
  async function json(url){const res=await fetch(url,{cache:'no-store'});let data=null;try{data=await res.json();}catch{}if(!res.ok)throw new Error(data?.detail||`Request failed (${res.status})`);return data;}
  function notify(message){if(typeof window.toast==='function')window.toast(message);else console.log(message);}

  function detailHtml(invoice){
    const items=invoice.items||[];
    return `<article class="panel academy-invoice-detail"><div class="academy-form-title"><div><span class="academy-kicker">INVOICE DETAIL</span><h2>${esc(invoice.invoice_number||`Invoice ${invoice.id}`)}</h2><p>${esc(invoice.account_name||'Family account')} · Issued ${esc(invoice.issue_date)} · Due ${esc(invoice.due_date)}</p></div><button type="button" class="secondary" data-close-invoice-detail>Close</button></div>
      <div class="academy-invoice-detail-status"><span class="academy-program-status ${esc(invoice.status)}">${esc(invoice.status)}</span><strong>Balance ${money(invoice.balance_due_cents)}</strong></div>
      <div class="academy-invoice-detail-items">${items.length?items.map(item=>`<div><div><strong>${esc(item.description)}</strong><small>Qty ${Number(item.quantity||1)} · ${money(item.unit_amount_cents)} each</small></div><span>${money(item.line_total_cents)}</span></div>`).join(''):'<div><span>No invoice items found.</span></div>'}</div>
      <div class="academy-invoice-detail-totals"><div><span>Subtotal</span><strong>${money(invoice.subtotal_cents)}</strong></div><div><span>Discount</span><strong>${money(invoice.discount_cents)}</strong></div><div><span>Invoice total</span><strong>${money(invoice.total_cents)}</strong></div><div><span>Paid</span><strong>${money(invoice.amount_paid_cents)}</strong></div><div><span>Credit applied</span><strong>${money(invoice.credit_applied_cents)}</strong></div><div class="balance"><span>Balance due</span><strong>${money(invoice.balance_due_cents)}</strong></div></div>
    </article>`;
  }
  async function openInvoice(id,button){
    const old=button.textContent;button.disabled=true;button.textContent='Opening…';
    try{
      const invoice=await json(`/api/academy/invoices/${id}`);
      const editor=$('#feeEditor');if(!editor)throw new Error('Invoice detail workspace is unavailable');
      editor.innerHTML=detailHtml(invoice);
      $('[data-close-invoice-detail]',editor).onclick=()=>editor.innerHTML='';
      editor.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(error){notify(error.message);}
    finally{button.disabled=false;button.textContent=old;}
  }
  async function enhance(){
    scheduled=false;if(enhancing||tab()!=='fees')return;
    const rows=$$('.academy-invoice-row');if(!rows.length)return;
    const pending=rows.filter(row=>row.dataset.invoiceOpenEnhanced!=='1');if(!pending.length)return;
    enhancing=true;
    try{
      const invoices=await json('/api/academy/invoices');
      const byNumber=new Map(invoices.map(invoice=>[String(invoice.invoice_number),invoice]));
      pending.forEach(row=>{
        const number=$(':scope > div:first-child > strong',row)?.textContent?.trim();
        const invoice=byNumber.get(String(number||''));if(!invoice)return;
        const status=$(':scope > .academy-program-status',row);
        const actions=document.createElement('div');actions.className='academy-invoice-actions';
        if(status)actions.appendChild(status);
        const open=document.createElement('button');open.type='button';open.className='secondary';open.textContent='Open';open.dataset.openInvoice=String(invoice.id);
        open.onclick=()=>openInvoice(Number(invoice.id),open);
        actions.appendChild(open);row.appendChild(actions);row.dataset.invoiceOpenEnhanced='1';
      });
    }catch(error){console.warn('Invoice detail controls unavailable',error);}
    finally{enhancing=false;}
  }
  function schedule(){if(scheduled)return;scheduled=true;setTimeout(enhance,40);}
  window.addEventListener('hashchange',schedule);window.addEventListener('academy-payments-updated',schedule);document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(()=>{if(tab()==='fees')schedule();}).observe(document.documentElement,{childList:true,subtree:true});schedule();
})();