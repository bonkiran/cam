(() => {
  let scheduled=false;

  function route(){
    const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }
  function lockParentPayment(){
    if(route().page!=='cam'||route().tab!=='parent')return;
    const invoiceHeading=document.querySelector('.cam-parent-invoices')?.closest('.panel')?.querySelector('.panel-head p');
    if(invoiceHeading)invoiceHeading.textContent='Invoices must be paid in full using a saved payment method.';
    const form=document.querySelector('#camParentPayForm');
    if(!form||form.dataset.fullPaymentLocked==='1')return;
    const input=form.querySelector('[name="amount"]');
    if(input){
      input.readOnly=true;
      input.setAttribute('aria-readonly','true');
      input.classList.add('cam-full-balance-input');
      const label=input.closest('label')?.querySelector('span');if(label)label.textContent='Full balance (USD)';
      const exact=input.value;
      input.addEventListener('change',()=>{input.value=exact;});
      input.addEventListener('input',()=>{if(input.value!==exact)input.value=exact;});
    }
    form.dataset.fullPaymentLocked='1';
  }
  function apply(){scheduled=false;lockParentPayment();}
  function schedule(){if(scheduled)return;scheduled=true;setTimeout(apply,20);}
  window.addEventListener('hashchange',schedule);document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});schedule();
})();