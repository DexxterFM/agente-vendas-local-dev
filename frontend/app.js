const conversations = [
  { id: 1, company: 'Clínica Harmonia ABA', handle: '@clinica.harmoniaaba', message: 'Sim! A gente trabalha com avaliação...', time: '16:24', status: 'qualified', stage: 'Qualificação', avatar: '♡', score: 82 },
  { id: 2, company: 'Instituto Crescer Kids', handle: '@crescerkids', message: 'Vocês atendem convênio também?', time: '15:57', status: 'waiting', stage: 'Aguardando', avatar: '✕', score: 76 },
  { id: 3, company: 'Espaço Terapêutico Viver', handle: '@espacoviver.terapias', message: 'Perfeito! Pode me enviar os valores?', time: '14:43', status: 'qualified', stage: 'Solução', avatar: '❧', score: 68 },
  { id: 4, company: 'FonoKids Desenvolvimento', handle: '@fonokids.desenv', message: 'Quais são os próximos passos?', time: '11:28', status: 'followup', stage: 'Follow-up', avatar: '◌', score: 61 },
  { id: 5, company: 'Movimento & Saber', handle: '@movimentoesaber', message: 'Entendi, obrigada! Vou conversar...', time: 'Ontem, 18:20', status: 'answered', stage: 'Respondida', avatar: '●', score: 58 }
];

const leads = [
  ['Clínica Harmonia ABA', '@clinica.harmoniaaba', 'Clínica (TEA)', 'Qualificação', 82, 'Hoje, 16:24', 'Enviar proposta'],
  ['Instituto Crescer Kids', '@crescerkids', 'Desenv. infantil', 'Aguardando', 76, 'Hoje, 15:57', 'Responder DM'],
  ['Espaço Terapêutico Viver', '@espacoviver.terapias', 'Terapias integradas', 'Solução', 68, 'Hoje, 14:43', 'Apresentar solução'],
  ['FonoKids Desenvolvimento', '@fonokids.desenv', 'Fonoaudiologia', 'Follow-up', 61, 'Hoje, 11:28', 'Follow-up (amanhã)'],
  ['Movimento & Saber', '@movimentoesaber', 'Psicomotricidade', 'Respondida', 58, 'Ontem, 18:20', 'Manter nutrir (3 dias)']
];

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[char]);

function showToast(message) {
  const toast = $('#toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('show'), 2200);
}

function renderConversations(filter = 'all', query = '') {
  const target = $('.conversation-list');
  if (!target) return;
  const normalized = query.trim().toLowerCase();
  const visible = conversations.filter((item) => {
    const matchesFilter = filter === 'all' || item.status === filter;
    const haystack = `${item.company} ${item.handle} ${item.message}`.toLowerCase();
    return matchesFilter && (!normalized || haystack.includes(normalized));
  });
  target.innerHTML = visible.length ? visible.map((item, index) => `
    <button class="conversation-item ${index === 0 ? 'selected' : ''}" data-conversation-id="${item.id}">
      <span class="company-avatar">${item.avatar}</span>
      <span class="conversation-copy"><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.message)}</small><em class="status-pill ${item.status}">${escapeHtml(item.stage)}</em></span>
      <time>${escapeHtml(item.time)}</time>
    </button>`).join('') : '<div class="empty-state">Nenhuma conversa encontrada.</div>';
  target.querySelectorAll('[data-conversation-id]').forEach((button) => button.addEventListener('click', () => selectConversation(Number(button.dataset.conversationId))));
}

function selectConversation(id) {
  const item = conversations.find((conversation) => conversation.id === id);
  if (!item) return;
  document.querySelectorAll('.conversation-item').forEach((button) => button.classList.toggle('selected', Number(button.dataset.conversationId) === id));
  $('#chat-company').textContent = item.company;
  $('#chat-handle').textContent = `${item.handle} · ativo agora`;
  $('#profile-company').textContent = item.company;
  $('#chat-body').innerHTML = `<div class="bubble out">Boa tarde! Vi o trabalho de vocês e gostei muito da proposta da clínica 😊<time>16:08 ✓✓</time></div><div class="bubble in">Boa tarde! Que bom que gostou! Como posso te ajudar?<time>16:15</time></div><div class="bubble out">Lindo o trabalho de vocês! Queria entender melhor os planos de atendimento e a disponibilidade de horários para avaliação.<time>16:24 ✓✓</time></div>`;
  $('.hot-badge').textContent = `${item.score >= 75 ? '🔥 Lead quente' : '◈ Lead em qualificação'} · score ${item.score}`;
  showToast(`Conversa de ${item.company} selecionada`);
}

function renderLeads() {
  const body = $('#lead-table');
  if (!body) return;
  body.innerHTML = leads.map((lead) => `<tr><td><strong>${escapeHtml(lead[0])}</strong></td><td>${escapeHtml(lead[1])}</td><td>${escapeHtml(lead[2])}</td><td><span class="status-pill">${escapeHtml(lead[3])}</span></td><td><b class="score">${lead[4]}</b></td><td>${escapeHtml(lead[5])}</td><td>${escapeHtml(lead[6])}</td></tr>`).join('');
}

function wireActions() {
  $('#browser-pane-btn')?.addEventListener('click', async () => {
    try {
      const opened = await window.sales?.browserPane('open');
      if (opened?.open) { $('#browser-toolbar').hidden = false; $('#browser-address').value = opened.url || $('#browser-address').value; showToast('Navegador interno aberto — sessão persistente do agente'); }
    } catch (error) { showToast(error.message || 'Não foi possível abrir o navegador interno'); }
  });
  document.querySelectorAll('[data-browser-action]').forEach((button) => button.addEventListener('click', async () => {
    try { const action=button.dataset.browserAction; const result=await window.sales?.browserPane(action); if(action==='close'||action==='hide') { $('#browser-toolbar').hidden=true; showToast('Painel do agente restaurado'); } else if(result?.url) $('#browser-address').value=result.url; } catch (error) { showToast(error.message || 'Falha no navegador interno'); }
  }));
  $('#browser-go')?.addEventListener('click', async () => { try { const result=await window.sales?.browserPane('navigate',$('#browser-address').value); if(result?.url) $('#browser-address').value=result.url; } catch (error) { showToast(error.message || 'URL inválida'); } });
  $('#browser-address')?.addEventListener('keydown', (event) => { if(event.key==='Enter') $('#browser-go')?.click(); });
  document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', async () => {
    try { await window.sales?.browserPane('hide'); } catch {}
    $('#browser-toolbar').hidden = true;
    document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    $('#page-title').textContent = button.textContent.trim().replace(/\s+\d+$/, '');
    const isConversation = button.dataset.view === 'conversations';
    $('#view-conversations').classList.toggle('active-view', isConversation);
    $('#view-placeholder').classList.toggle('active', !isConversation);
    $('#placeholder-title').textContent = button.textContent.trim().replace(/\s+\d+$/, '');
    showToast(`Visão ${button.textContent.trim()} carregada`);
  }));

  document.querySelectorAll('.filter').forEach((button) => button.addEventListener('click', () => {
    document.querySelectorAll('.filter').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    renderConversations(button.dataset.filter, $('#search-input').value);
  }));

  $('#search-input')?.addEventListener('input', (event) => {
    const activeFilter = $('.filter.active')?.dataset.filter || 'all';
    renderConversations(activeFilter, event.target.value);
  });

  $('#generate-btn')?.addEventListener('click', () => {
    $('#draft-text').textContent = 'Perfeito! Com esse contexto consigo recomendar o melhor plano, explicar as condições e já conferir os próximos horários disponíveis para uma avaliação inicial. Posso seguir por aí? 😊';
    showToast('Resposta sugerida atualizada pelo agente local');
  });
  $('#edit-btn')?.addEventListener('click', () => { $('#draft-text').contentEditable = $('#draft-text').contentEditable !== 'true'; $('#draft-text').focus(); showToast('Rascunho pronto para edição'); });
  $('#copy-btn')?.addEventListener('click', async () => { await navigator.clipboard?.writeText($('#draft-text').textContent || ''); showToast('Resposta copiada para a área de transferência'); });
  $('#queue-btn')?.addEventListener('click', () => showToast('Resposta enviada para a fila de aprovação'));
  $('#pause-btn')?.addEventListener('click', () => showToast('Conversa pausada — nenhuma ação automática será enviada'));
  $('#followup-btn')?.addEventListener('click', () => showToast('Follow-up sugerido para amanhã às 10:00'));
}

renderConversations();
renderLeads();
selectConversation(1);
wireActions();

if ('serviceWorker' in navigator && window.location.protocol !== 'file:') {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}
