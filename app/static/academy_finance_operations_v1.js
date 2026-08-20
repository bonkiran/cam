(() => {
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let scheduled=false;
  let loading=false;

  function route(){
    const raw=location.hash.replace(/^#/,'');
    const [page,query='']=raw.split('?');
    return {page:page||'dashboard',tab:new URLSearchParams(query).get('tab')||'overview'};
  }
  function esc(v=''){
    return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function money(cents){
    return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(cents||0)/100);
  }
  function rateMoney(cents,type){
    const value=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(cents||0)/100);
    return `${value}/${type==='session'?'session':'hr'}`;
  }
  async function api(url){
    const response=await fetch(url,{cache:'no-store'});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok)throw new Error(data?.detail||`Request failed (${response.status})`);
    return data;
  }
  function currentMonth(){
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit'}).formatToParts(new Date());
    const year=parts.find(p=>p.type==='year')?.value;
    const month=parts.find(p=>p.type==='month')?.value;
    return `${year}-${month}`;
  }
  function moneyCard(label,value,note){
    return `<div class="academy-owner-money-card"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;
  }
  async function enhanceDashboard(){
    const info=route();
    if(info.page!=='academy'||info.tab!=='overview')return;
    const outgoings=$('#academyWorkspace .academy-owner-outgoings');
    const grid=outgoings?$('.academy-owner-money-grid',outgoings):null;
    if(!grid||grid.dataset.financeOps==='1')return;
    try{
      const summary=await api(`/api/academy/finance/operations-summary?month=${encodeURIComponent(currentMonth())}`);
      grid.innerHTML=[
        moneyCard('Coach Salary Paid','—',`${Number(summary.coach_rates_configured||0)} coach rates configured · payroll next`),
        moneyCard('Facility Payments',money(summary.facility_payments_mtd_cents),`${Number(summary.facility_expense_count||0)} paid facility expenses`),
        moneyCard('Academy Expenses',money(summary.academy_expenses_mtd_cents),`${Number(summary.academy_expense_count||0)} paid operating expenses`),
      ].join('');
      grid.dataset.financeOps='1';
    }catch(error){
      console.warn('Finance operations dashboard enhancement failed:',error);
    }
  }
  function rateRow(row){
    return `<div class="cam-finance-ops-row"><div><strong>${esc(row.coach_name||'Coach')}</strong><small>${esc(row.rate_type||'hourly')} · effective ${esc(row.effective_from||'—')}</small></div><b>${esc(rateMoney(row.rate_cents,row.rate_type))}</b></div>`;
  }
  function expenseRow(row){
    const label=row.expense_type==='facility'?(row.facility_name||row.vendor):row.vendor;
    return `<div class="cam-finance-ops-row"><div><strong>${esc(label||'Expense')}</strong><small>${esc(row.category||'Expense')} · ${esc(row.expense_date||'—')} · ${esc(row.payment_method||'')}</small></div><b>${esc(money(row.amount_cents))}</b></div>`;
  }
  async function enhanceFinance(){
    const info=route();
    if(info.page!=='academy'||info.tab!=='fees'||loading)return;
    const content=$('#academyWorkspace .academy-content');
    if(!content||$('#camFinanceOperations',content))return;
    loading=true;
    try{
      const month=currentMonth();
      const [summary,rates,expenses]=await Promise.all([
        api(`/api/academy/finance/operations-summary?month=${encodeURIComponent(month)}`),
        api('/api/academy/coach-rates?status=active'),
        api(`/api/academy/expenses?month=${encodeURIComponent(month)}`),
      ]);
      if(route().tab!=='fees'||!content.isConnected)return;
      const academyExpenses=expenses.filter(row=>row.expense_type==='academy');
      const facilityExpenses=expenses.filter(row=>row.expense_type==='facility');
      const section=document.createElement('section');
      section.id='camFinanceOperations';
      section.className='cam-finance-ops';
      section.innerHTML=`<div class="cam-finance-ops-summary">
          ${moneyCard('Coach Rates',String(Number(summary.coach_rates_configured||0)),'Active coach compensation rates')}
          ${moneyCard('Academy Expenses',money(summary.academy_expenses_mtd_cents),`${Number(summary.academy_expense_count||0)} paid this month`)}
          ${moneyCard('Facility Expenses',money(summary.facility_payments_mtd_cents),`${Number(summary.facility_expense_count||0)} paid this month`)}
        </div>
        <div class="cam-finance-ops-grid">
          <article class="panel"><div class="panel-head"><div><h2>Coach Rates</h2><p>Current compensation rates used for future automated payroll calculation.</p></div></div><div class="cam-finance-ops-list">${rates.length?rates.map(rateRow).join(''):'<div class="academy-dash-empty">No coach rates configured.</div>'}</div></article>
          <article class="panel"><div class="panel-head"><div><h2>Academy Expenses</h2><p>Operating expenses for ${esc(month)}.</p></div></div><div class="cam-finance-ops-list">${academyExpenses.length?academyExpenses.map(expenseRow).join(''):'<div class="academy-dash-empty">No academy expenses this month.</div>'}</div></article>
          <article class="panel"><div class="panel-head"><div><h2>Facility Expenses</h2><p>Ground, net and facility payments for ${esc(month)}.</p></div></div><div class="cam-finance-ops-list">${facilityExpenses.length?facilityExpenses.map(expenseRow).join(''):'<div class="academy-dash-empty">No facility expenses this month.</div>'}</div></article>
        </div>`;
      content.appendChild(section);
    }catch(error){
      console.warn('Finance operations UI enhancement failed:',error);
    }finally{
      loading=false;
    }
  }
  async function apply(){
    scheduled=false;
    await enhanceDashboard();
    await enhanceFinance();
  }
  function schedule(){
    if(scheduled)return;
    scheduled=true;
    setTimeout(apply,40);
  }
  window.addEventListener('hashchange',schedule);
  window.addEventListener('academy-payments-updated',schedule);
  document.addEventListener('DOMContentLoaded',schedule);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  schedule();
})();
