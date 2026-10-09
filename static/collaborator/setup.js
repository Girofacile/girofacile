/* Invitation tokens and passwords stay in this page's memory and request bodies. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  let token=new URLSearchParams(location.hash.slice(1)).get('token') || '';
  // Remove the bearer secret before any request; it never belongs in history or storage.
  history.replaceState(null,'',location.pathname+location.search);
  let passwordContext=[], busy=false, ready=false;
  const controller=window.GiroFacilePasswordStrength.attach({
    inputId:'invitePassword',meterId:'invitePasswordMeter',confirmInputId:'inviteConfirmPassword',
    buttonId:'inviteSubmit',context:()=>passwordContext
  });
  const invalidMessage='Invito non valido, scaduto o già utilizzato. Richiedi un nuovo invito al titolare della tua azienda.';
  function refresh(){
    if(controller) controller.refresh();
    if(busy || !ready) el('inviteSubmit').disabled=true;
  }
  el('invitePassword').addEventListener('input',refresh);
  el('inviteConfirmPassword').addEventListener('input',refresh);
  async function request(path,payload){
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
      credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer',body:JSON.stringify(payload)});
    let data={};try{data=await response.json();}catch{}
    if(!response.ok){
      const error=new Error(typeof data.detail==='string'?data.detail:(response.status===422?'Controlla i campi della password e riprova.':'Servizio non disponibile. Riprova più tardi.'));
      error.status=response.status;throw error;
    }
    return data;
  }
  function terminal(message,retry){
    ready=false;el('inviteLoading').hidden=true;el('inviteForm').hidden=true;
    el('inviteErrorState').hidden=false;el('inviteError').textContent=message;
    el('inviteRetry').hidden=!retry;refresh();
  }
  async function initialize(){
    if(busy) return;
    if(!/^[A-Za-z0-9_-]{32,128}$/.test(token)){terminal(invalidMessage,false);return;}
    busy=true;ready=false;el('inviteLoading').hidden=false;
    el('inviteErrorState').hidden=true;el('inviteForm').hidden=true;
    refresh();
    try{
      const data=await request('/api/collaborator-invitations/info',{token});
      el('inviteName').textContent=data.full_name || 'Collaboratore';
      el('inviteCompany').textContent=data.company_name || '';
      el('inviteEmail').value=data.email || '';
      passwordContext=Array.isArray(data.password_context)?data.password_context:[data.full_name || '',data.email || '',data.company_name || ''];
      ready=true;el('inviteLoading').hidden=true;el('inviteForm').hidden=false;
    }catch(error){
      terminal(error.status===400?invalidMessage:'Non è stato possibile verificare l’invito. Riprova tra poco.',error.status!==400);
    }finally{busy=false;refresh();}
  }
  async function accept(event){
    event.preventDefault();
    if(busy || !ready) return;
    const password=el('invitePassword').value, confirmation=el('inviteConfirmPassword').value;
    el('inviteFormError').textContent='';
    const assessment=window.GiroFacilePasswordStrength.assess(password,passwordContext);
    if(!assessment.acceptable){el('inviteFormError').textContent=assessment.message;return;}
    if(password!==confirmation){el('inviteFormError').textContent='Le password non coincidono.';return;}
    busy=true;refresh();el('inviteSubmit').textContent='Attivazione…';
    try{
      await request('/api/collaborator-invitations/accept',{token,password,confirm_password:confirmation});
      token='';ready=false;
      el('invitePassword').value='';el('inviteConfirmPassword').value='';
      el('inviteForm').hidden=true;el('inviteSuccess').hidden=false;
      el('inviteLogin').focus();
    }catch(error){
      if(error.status===400){
        el('invitePassword').value='';el('inviteConfirmPassword').value='';
        terminal(invalidMessage,false);
      }else{
        // A password validation or temporary failure keeps the form available for retry.
        el('inviteFormError').textContent=error.status
          ?error.message:'Non è stato possibile completare l’attivazione. Riprova tra poco.';
      }
    }finally{busy=false;el('inviteSubmit').textContent='Imposta la password';refresh();}
  }
  el('inviteRetry').addEventListener('click',initialize);
  el('inviteForm').addEventListener('submit',accept);
  initialize();
})();
