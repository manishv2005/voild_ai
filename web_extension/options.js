(function(){
  const api = typeof chrome !== 'undefined' ? chrome : browser;
  const input = document.getElementById('serverBase');
  const btn = document.getElementById('save');
  const status = document.getElementById('status');

  api.storage.sync.get({ serverBase: 'http://localhost:8000' }, (res)=>{
    input.value = res.serverBase;
  });

  btn.addEventListener('click', ()=>{
    const val = input.value.trim().replace(/\/$/, '');
    if (!val){ status.textContent = 'Enter a valid URL'; return; }
    api.storage.sync.set({ serverBase: val }, ()=>{
      status.textContent = 'Saved';
      setTimeout(()=> status.textContent='', 1200);
    });
  });
})();
